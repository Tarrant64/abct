"""
Backup and Restore Router

Provides endpoints for backing up and restoring ABCT configurations.
Allows users to export all their settings, wallets, and custom data to a JSON file,
and import it back on a fresh installation or after data loss.

Security:
- API keys are included in backups (with warnings)
- Option to exclude sensitive data available
- Import validates file format and version compatibility
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db
from routers.auth import verify_session

router = APIRouter(prefix="/backup", tags=["backup"])

# Version for backup file format - increment if format changes
BACKUP_FORMAT_VERSION = "1.0.0"
ABCT_VERSION = "0.10.0"  # Current ABCT version

# Tables to include in backup
BACKUP_TABLES = {
    "wallets": {
        "description": "All wallet addresses and labels",
        "sensitive": False,
        "required": True
    },
    "api_settings": {
        "description": "API keys and configuration",
        "sensitive": True,
        "required": False
    },
    "security_settings": {
        "description": "SSL/HTTPS configuration",
        "sensitive": True,  # Contains cert paths
        "required": False
    },
    "custom_tokens": {
        "description": "Manually added custom tokens",
        "sensitive": False,
        "required": False
    },
    "token_metadata": {
        "description": "Token metadata and tracking settings",
        "sensitive": False,
        "required": False
    },
    "nft_scheduler_collections": {
        "description": "NFT collections being tracked",
        "sensitive": False,
        "required": False
    },
    "api_rate_limits": {
        "description": "Custom API rate limits",
        "sensitive": False,
        "required": False
    }
}


class BackupOptions(BaseModel):
    include_api_keys: bool = True
    include_security_settings: bool = False
    include_custom_tokens: bool = True
    include_nft_collections: bool = True


class ImportOptions(BaseModel):
    mode: str = "merge"  # "merge" or "replace"
    skip_api_keys: bool = False
    skip_security_settings: bool = True  # Skip by default for security
    backup_data: str  # JSON string of backup file


class PreviewResponse(BaseModel):
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    summary: Dict[str, Any] = {}
    compatible: bool = True


@router.post("/export", dependencies=[Depends(verify_session)])
async def export_backup(options: BackupOptions):
    """
    Export all user configurations to a JSON backup file.

    Options:
    - include_api_keys: Include API keys (default: true, shows warning)
    - include_security_settings: Include SSL/cert settings (default: false)
    - include_custom_tokens: Include custom tokens (default: true)
    - include_nft_collections: Include NFT scheduler collections (default: true)

    Returns a JSON backup file ready for download.
    """
    try:
        db = await get_db()
        backup = {
            "format_version": BACKUP_FORMAT_VERSION,
            "abct_version": ABCT_VERSION,
            "export_date": datetime.now().isoformat(),
            "export_timestamp": int(datetime.now().timestamp()),
            "options": options.dict(),
            "data": {},
            "warnings": []
        }

        # Export each table based on options
        for table_name, table_info in BACKUP_TABLES.items():
            # Check if we should include this table
            if table_name == "api_settings" and not options.include_api_keys:
                continue
            if table_name == "security_settings" and not options.include_security_settings:
                continue
            if table_name == "custom_tokens" and not options.include_custom_tokens:
                continue
            if table_name == "nft_scheduler_collections" and not options.include_nft_collections:
                continue

            # Fetch data from table
            cursor = await db.execute(f"SELECT * FROM {table_name}")
            rows = await cursor.fetchall()

            # Convert to list of dicts
            if rows:
                columns = [description[0] for description in cursor.description]
                backup["data"][table_name] = [
                    dict(zip(columns, row)) for row in rows
                ]
            else:
                backup["data"][table_name] = []

        await db.close()

        # Add warnings for sensitive data
        if options.include_api_keys and backup["data"].get("api_settings"):
            api_count = len([s for s in backup["data"]["api_settings"] if s.get("api_key")])
            if api_count > 0:
                backup["warnings"].append(
                    f"This backup contains {api_count} API key(s). Store this file securely and never share it publicly."
                )

        if options.include_security_settings and backup["data"].get("security_settings"):
            backup["warnings"].append(
                "This backup contains SSL/certificate configuration. Certificate files are NOT included - only paths are saved."
            )

        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"abct-backup-{timestamp}.json"

        # Return as downloadable JSON file
        json_content = json.dumps(backup, indent=2, default=str)

        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/preview", dependencies=[Depends(verify_session)])
async def preview_import(options: ImportOptions) -> PreviewResponse:
    """
    Preview what will be imported from a backup file (dry-run).

    Validates the backup file format, checks version compatibility,
    and shows what data will be imported without making any changes.

    Returns:
    - valid: Whether the backup file is valid
    - errors: List of validation errors
    - warnings: List of warnings about the import
    - summary: Summary of what will be imported
    - compatible: Whether the backup version is compatible
    """
    errors = []
    warnings = []
    summary = {}

    try:
        # Parse backup JSON
        try:
            backup = json.loads(options.backup_data)
        except json.JSONDecodeError as e:
            return PreviewResponse(
                valid=False,
                errors=[f"Invalid JSON format: {str(e)}"],
                summary={},
                compatible=False
            )

        # Validate backup structure
        required_fields = ["format_version", "abct_version", "export_date", "data"]
        for field in required_fields:
            if field not in backup:
                errors.append(f"Missing required field: {field}")

        if errors:
            return PreviewResponse(
                valid=False,
                errors=errors,
                summary={},
                compatible=False
            )

        # Check version compatibility
        backup_format_version = backup.get("format_version", "0.0.0")
        backup_abct_version = backup.get("abct_version", "unknown")

        # For now, accept all 1.x.x format versions
        if not backup_format_version.startswith("1."):
            warnings.append(
                f"Backup format version {backup_format_version} may not be fully compatible with current format {BACKUP_FORMAT_VERSION}"
            )

        summary["backup_info"] = {
            "format_version": backup_format_version,
            "abct_version": backup_abct_version,
            "export_date": backup.get("export_date"),
            "age_days": (datetime.now() - datetime.fromisoformat(backup.get("export_date"))).days if backup.get("export_date") else "unknown"
        }

        # Analyze data to be imported
        data = backup.get("data", {})
        summary["tables"] = {}

        for table_name, table_info in BACKUP_TABLES.items():
            if table_name not in data:
                continue

            table_data = data[table_name]
            count = len(table_data)

            # Skip based on import options
            if table_name == "api_settings" and options.skip_api_keys:
                summary["tables"][table_name] = {
                    "count": count,
                    "action": "skip",
                    "reason": "Excluded by import options"
                }
                continue

            if table_name == "security_settings" and options.skip_security_settings:
                summary["tables"][table_name] = {
                    "count": count,
                    "action": "skip",
                    "reason": "Excluded by import options (recommended)"
                }
                continue

            if count > 0:
                summary["tables"][table_name] = {
                    "count": count,
                    "action": options.mode,
                    "description": table_info["description"],
                    "sensitive": table_info["sensitive"]
                }

                # Add specific warnings
                if table_name == "api_settings" and table_info["sensitive"]:
                    api_keys = [s for s in table_data if s.get("api_key")]
                    if api_keys:
                        warnings.append(f"This backup contains {len(api_keys)} API key(s)")

                if table_name == "wallets":
                    warnings.append(f"Will {options.mode} {count} wallet(s)")

                if table_name == "custom_tokens":
                    warnings.append(f"Will {options.mode} {count} custom token(s)")

        # Check for existing data that will be affected
        if options.mode == "replace":
            warnings.append("REPLACE mode will delete ALL existing data before importing!")
            warnings.append("This includes all wallets, settings, and configurations.")
        else:
            warnings.append("MERGE mode will keep existing data and add/update from backup")
            warnings.append("Conflicts will be resolved by updating existing records")

        # Count warnings from backup
        if backup.get("warnings"):
            for warning in backup["warnings"]:
                warnings.append(f"From backup: {warning}")

        return PreviewResponse(
            valid=True,
            errors=errors,
            warnings=warnings,
            summary=summary,
            compatible=True
        )

    except Exception as e:
        return PreviewResponse(
            valid=False,
            errors=[f"Preview failed: {str(e)}"],
            summary={},
            compatible=False
        )


@router.post("/import", dependencies=[Depends(verify_session)])
async def import_backup(options: ImportOptions):
    """
    Import configurations from a backup file.

    Options:
    - mode: "merge" (add/update, keep existing) or "replace" (delete all, then import)
    - skip_api_keys: Don't import API keys (default: false)
    - skip_security_settings: Don't import security settings (default: true)
    - backup_data: JSON string of the backup file

    CAUTION: "replace" mode will delete ALL existing data first!

    Returns summary of what was imported.
    """
    try:
        # First run preview to validate
        preview = await preview_import(options)
        if not preview.valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid backup file: {', '.join(preview.errors)}"
            )

        # Parse backup
        backup = json.loads(options.backup_data)
        data = backup.get("data", {})

        db = await get_db()
        import_summary = {
            "started_at": datetime.now().isoformat(),
            "mode": options.mode,
            "tables_processed": {},
            "warnings": []
        }

        try:
            # If replace mode, clear all tables first
            if options.mode == "replace":
                import_summary["warnings"].append("REPLACE mode: Clearing all existing data...")
                for table_name in BACKUP_TABLES.keys():
                    await db.execute(f"DELETE FROM {table_name}")
                await db.commit()

            # Import each table
            for table_name in BACKUP_TABLES.keys():
                if table_name not in data or not data[table_name]:
                    continue

                # Skip based on options
                if table_name == "api_settings" and options.skip_api_keys:
                    import_summary["tables_processed"][table_name] = {
                        "status": "skipped",
                        "reason": "Excluded by import options"
                    }
                    continue

                if table_name == "security_settings" and options.skip_security_settings:
                    import_summary["tables_processed"][table_name] = {
                        "status": "skipped",
                        "reason": "Excluded by import options"
                    }
                    continue

                table_data = data[table_name]
                imported_count = 0
                updated_count = 0
                skipped_count = 0

                for row in table_data:
                    try:
                        # Get column names and values
                        columns = list(row.keys())
                        values = list(row.values())

                        # Remove auto-increment IDs for most tables (let DB generate new ones)
                        # Exception: security_settings uses id=1 as singleton
                        if table_name != "security_settings" and "id" in columns:
                            id_index = columns.index("id")
                            columns.pop(id_index)
                            values.pop(id_index)

                        # Build INSERT OR REPLACE query for merge mode
                        placeholders = ",".join(["?" for _ in values])
                        columns_str = ",".join(columns)

                        if options.mode == "merge":
                            # Use INSERT OR REPLACE to handle conflicts
                            query = f"INSERT OR REPLACE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                        else:
                            # Replace mode: just insert (tables already cleared)
                            query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

                        await db.execute(query, values)
                        imported_count += 1

                    except Exception as e:
                        skipped_count += 1
                        import_summary["warnings"].append(
                            f"Failed to import row in {table_name}: {str(e)}"
                        )

                await db.commit()

                import_summary["tables_processed"][table_name] = {
                    "status": "success",
                    "imported": imported_count,
                    "skipped": skipped_count,
                    "total": len(table_data)
                }

            import_summary["completed_at"] = datetime.now().isoformat()
            import_summary["success"] = True

            await db.close()
            return import_summary

        except Exception as e:
            await db.rollback()
            await db.close()
            raise HTTPException(
                status_code=500,
                detail=f"Import failed during database operations: {str(e)}"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/info")
async def get_backup_info():
    """
    Get information about what can be backed up and current data status.

    Returns statistics about each table that can be backed up.
    """
    try:
        db = await get_db()
        info = {
            "backup_format_version": BACKUP_FORMAT_VERSION,
            "abct_version": ABCT_VERSION,
            "tables": {}
        }

        for table_name, table_info in BACKUP_TABLES.items():
            try:
                cursor = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
                count = (await cursor.fetchone())[0]

                info["tables"][table_name] = {
                    "description": table_info["description"],
                    "sensitive": table_info["sensitive"],
                    "required": table_info["required"],
                    "record_count": count,
                    "has_data": count > 0
                }
            except Exception as e:
                info["tables"][table_name] = {
                    "description": table_info["description"],
                    "sensitive": table_info["sensitive"],
                    "required": table_info["required"],
                    "record_count": 0,
                    "has_data": False,
                    "error": str(e)
                }

        await db.close()
        return info

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get backup info: {str(e)}")


@router.get("/export-env", dependencies=[Depends(verify_session)])
async def export_env_file():
    """
    Export .env file contents for backup.

    SECURITY WARNING: This contains ALL API keys in plain text!
    - Only download this on trusted devices
    - Never share this file
    - Store securely (encrypted storage recommended)
    - Delete from downloads folder after importing to new server

    Returns a text file with .env contents.
    """
    try:
        # Find .env file (in project root, parent of backend directory)
        env_path = Path(__file__).parent.parent.parent / ".env"

        if not env_path.exists():
            raise HTTPException(
                status_code=404,
                detail=".env file not found. API keys may be set via environment variables instead."
            )

        # Read .env file
        with open(env_path, 'r') as f:
            env_content = f.read()

        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        filename = f"abct-env-{timestamp}.txt"

        # Add warning header to the file
        warning_header = f"""# ============================================================
# ABCT API Keys - HIGHLY SENSITIVE
# ============================================================
#
# ⚠️  WARNING: This file contains ALL your API keys in plain text!
#
# Security Guidelines:
# - NEVER commit this file to version control
# - NEVER share this file with anyone
# - Store in encrypted storage or password manager
# - Delete from downloads folder after use
# - Use secure transfer methods only (SSH, encrypted USB)
#
# Exported: {datetime.now().isoformat()}
# Source: {env_path}
#
# ============================================================

{env_content}
"""

        return Response(
            content=warning_header,
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "X-Content-Type-Options": "nosniff"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export .env file: {str(e)}")


@router.post("/import-env", dependencies=[Depends(verify_session)])
async def import_env_file(env_content: str):
    """
    Import .env file contents (preview only - doesn't write to disk).

    For security, this endpoint only validates and previews the .env content.
    To actually use these keys, you must:
    1. Manually copy the .env file to the server
    2. Restart the application to load new environment variables

    Returns: Preview of what would be imported and instructions.
    """
    try:
        # Parse .env content
        lines = env_content.strip().split('\n')
        api_keys = {}

        for line in lines:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                # Only track API key variables
                if 'API_KEY' in key or 'COINBASE' in key or 'NFT' in key or 'ABCT' in key:
                    # Mask the value for preview
                    if value:
                        masked_value = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
                        api_keys[key] = {
                            'has_value': bool(value),
                            'preview': masked_value,
                            'length': len(value)
                        }
                    else:
                        api_keys[key] = {
                            'has_value': False,
                            'preview': '(empty)',
                            'length': 0
                        }

        return {
            "valid": True,
            "api_keys_found": len(api_keys),
            "preview": api_keys,
            "instructions": [
                "This is a preview only - keys are NOT imported yet.",
                "To use these API keys:",
                "1. Save the .env file to your server (project root directory)",
                "2. For Docker: Pass keys as environment variables when starting container",
                "3. For local: Restart the backend server to load new .env file",
                "4. Verify keys are loaded: Check /settings/api-status endpoint"
            ],
            "warnings": [
                "Never store .env files in version control",
                "Delete the .env backup file after importing",
                "API keys in environment variables override .env file"
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse .env content: {str(e)}")
