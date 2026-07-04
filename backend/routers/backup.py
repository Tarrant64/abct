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
from pathlib import Path
from datetime import datetime
import json
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db, save_api_setting, _decrypt_value
from auth_utils import verify_session
from services.cardano import cardano_service, is_stake_address

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup", tags=["backup"])

# Version for backup file format - increment if format changes
BACKUP_FORMAT_VERSION = "1.0.0"
ABCT_VERSION = "1.0.0"  # Current ABCT version


async def optimize_cardano_wallets(wallets: List[Dict]) -> List[Dict]:
    """
    Optimize Cardano wallets for export by only including stake addresses.

    For Cardano payment addresses (addr1), queries the Cardano service to get
    the associated stake address and exports that instead. This reduces the number
    of wallets exported and allows the import to auto-discover payment addresses.

    For non-Cardano wallets, includes them as-is.
    """
    optimized = []
    seen_stake_addresses = set()
    cardano_payment_to_stake = {}  # Cache of payment -> stake lookups

    logger.info(f"Optimizing {len(wallets)} wallets for Cardano stake keys...")

    for wallet in wallets:
        blockchain = wallet.get('blockchain', '').lower()
        address = wallet.get('address', '')

        # Non-Cardano wallets: include as-is
        if blockchain != 'cardano':
            optimized.append(wallet)
            continue

        # Cardano stake address: include if not already seen
        if is_stake_address(address):
            if address not in seen_stake_addresses:
                seen_stake_addresses.add(address)
                optimized.append(wallet)
                logger.info(f"  ✓ Including stake address: {address[:20]}...")
            else:
                logger.info(f"  ⊘ Skipping duplicate stake address: {address[:20]}...")
            continue

        # Cardano payment address: get its stake address
        try:
            # Check cache first
            if address in cardano_payment_to_stake:
                stake_addr = cardano_payment_to_stake[address]
            else:
                stake_addr = await cardano_service.get_stake_address(address)
                cardano_payment_to_stake[address] = stake_addr

            if stake_addr and stake_addr not in seen_stake_addresses:
                # Create a new wallet entry with the stake address
                stake_wallet = wallet.copy()
                stake_wallet['address'] = stake_addr
                stake_wallet['label'] = wallet.get('label', '') or f"Stake key"
                optimized.append(stake_wallet)
                seen_stake_addresses.add(stake_addr)
                logger.info(f"  ✓ Replaced payment address {address[:20]}... with stake {stake_addr[:20]}...")
            elif stake_addr:
                logger.info(f"  ⊘ Skipping payment address {address[:20]}... (stake key already exported)")
            else:
                # No stake address found, include the payment address as-is
                optimized.append(wallet)
                logger.info(f"  ⚠ No stake address found for {address[:20]}..., including payment address")

        except Exception as e:
            logger.warning(f"  ⚠ Error getting stake address for {address[:20]}...: {e}")
            # On error, include the payment address as-is
            optimized.append(wallet)

    logger.info(f"Optimization complete: {len(wallets)} wallets → {len(optimized)} wallets ({len(wallets) - len(optimized)} removed)")

    return optimized

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
    optimize_cardano: bool = True  # Only export stake keys for Cardano, not payment addresses


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
                all_rows = [dict(zip(columns, row)) for row in rows]

                # Decrypt api_settings values for export (stored encrypted at rest)
                # Security note (Finding #7): API keys are exported in cleartext
                # so backups can be restored to a fresh instance. This endpoint is
                # authenticated and the backup file itself carries a warning banner.
                # Acceptable for the home-network use case, but users should store
                # backup files securely and never share them publicly.
                if table_name == "api_settings":
                    for row in all_rows:
                        for field in ('api_key', 'api_secret', 'api_passphrase'):
                            if row.get(field):
                                row[field] = _decrypt_value(row[field])

                # Special handling for wallets table with Cardano optimization
                if table_name == "wallets" and options.optimize_cardano:
                    backup["data"][table_name] = await optimize_cardano_wallets(all_rows)
                else:
                    backup["data"][table_name] = all_rows
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

        if options.optimize_cardano and backup["data"].get("wallets"):
            cardano_stake_count = len([w for w in backup["data"]["wallets"] if w.get('blockchain') == 'cardano' and is_stake_address(w.get('address', ''))])
            if cardano_stake_count > 0:
                backup["warnings"].append(
                    f"Cardano optimization enabled: {cardano_stake_count} stake address(es) exported. Payment addresses will be auto-discovered on import."
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


@router.post("/import")
async def import_backup(options: ImportOptions, user_id: int = Depends(verify_session)):
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

                # Special handling for wallets table - expand stake addresses
                if table_name == "wallets":
                    for row in table_data:
                        try:
                            address = row.get('address', '')
                            blockchain = row.get('blockchain', '').lower()
                            label = row.get('label', '')

                            # Cardano stake address: expand to payment addresses
                            if blockchain == 'cardano' and is_stake_address(address):
                                logger.info(f"Importing Cardano stake address: {address[:20]}...")
                                payment_addresses = await cardano_service.get_addresses_from_stake(address)

                                if not payment_addresses:
                                    logger.warning(f"  No payment addresses found for stake {address[:20]}...")
                                    skipped_count += 1
                                    import_summary["warnings"].append(
                                        f"Stake address {address[:20]}... has no associated payment addresses (inactive)"
                                    )
                                    continue

                                # Import each payment address
                                for pay_addr in payment_addresses:
                                    try:
                                        # Check if already exists
                                        check_cursor = await db.execute(
                                            "SELECT id FROM wallets WHERE user_id = ? AND address = ? AND blockchain = ?",
                                            (user_id, pay_addr, 'cardano')
                                        )
                                        existing = await check_cursor.fetchone()

                                        if existing:
                                            skipped_count += 1
                                            continue

                                        # Insert payment address
                                        await db.execute(
                                            "INSERT INTO wallets (user_id, address, blockchain, label, created_at, updated_at) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
                                            (user_id, pay_addr, 'cardano', label or f"From {address[:15]}...")
                                        )
                                        imported_count += 1

                                    except Exception as e:
                                        logger.error(f"  Failed to import payment address {pay_addr}: {e}")
                                        skipped_count += 1

                                logger.info(f"  ✓ Expanded stake address to {len(payment_addresses)} payment address(es)")
                                continue

                            # Regular wallet: import normally
                            # Check if already exists
                            check_cursor = await db.execute(
                                "SELECT id FROM wallets WHERE user_id = ? AND address = ? AND blockchain = ?",
                                (user_id, address, blockchain)
                            )
                            existing = await check_cursor.fetchone()

                            if existing:
                                skipped_count += 1
                                continue

                            # Insert wallet
                            await db.execute(
                                "INSERT INTO wallets (user_id, address, blockchain, label, created_at, updated_at) VALUES (?, ?, ?, ?, datetime('now'), datetime('now'))",
                                (user_id, address, blockchain, label)
                            )
                            imported_count += 1

                        except Exception as e:
                            skipped_count += 1
                            logger.error(f"Failed to import wallet: {str(e)} | Row: {row}")
                            import_summary["warnings"].append(
                                f"Failed to import wallet {row.get('address', 'unknown')}: {str(e)}"
                            )

                    await db.commit()

                else:
                    # Non-wallet tables: use generic import logic
                    # Get valid columns for this table
                    cursor = await db.execute(f"PRAGMA table_info({table_name})")
                    table_columns = [col[1] for col in await cursor.fetchall()]

                    for row in table_data:
                        try:
                            # Get column names and values, filtering to only valid columns
                            all_columns = list(row.keys())
                            filtered_columns = []
                            filtered_values = []

                            for col in all_columns:
                                if col in table_columns:
                                    filtered_columns.append(col)
                                    filtered_values.append(row[col])

                            columns = filtered_columns
                            values = filtered_values

                            # Remove auto-increment IDs for most tables (let DB generate new ones)
                            # Exception: security_settings uses id=1 as singleton
                            if table_name != "security_settings" and "id" in columns:
                                id_index = columns.index("id")
                                columns.pop(id_index)
                                values.pop(id_index)

                            # Override user_id for user-specific tables
                            # This ensures imported data belongs to the current user
                            user_tables = ["custom_tokens", "portfolio_history", "portfolio_snapshots"]
                            if table_name in user_tables and "user_id" in columns:
                                user_id_index = columns.index("user_id")
                                values[user_id_index] = user_id

                            # Build INSERT OR IGNORE query for merge mode (skip duplicates)
                            placeholders = ",".join(["?" for _ in values])
                            columns_str = ",".join(columns)

                            if options.mode == "merge":
                                # Use INSERT OR IGNORE to skip conflicts without errors
                                query = f"INSERT OR IGNORE INTO {table_name} ({columns_str}) VALUES ({placeholders})"
                            else:
                                # Replace mode: just insert (tables already cleared)
                                query = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"

                            cursor = await db.execute(query, values)
                            # Check if row was actually inserted (rowcount > 0)
                            if cursor.rowcount > 0:
                                imported_count += 1
                            else:
                                # Row was skipped due to conflict (already exists)
                                skipped_count += 1

                        except Exception as e:
                            skipped_count += 1
                            logger.error(f"Failed to import row in {table_name}: {str(e)} | Row: {row}")
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


@router.post("/import-env")
async def import_env_file(env_content: str, user_id: int = Depends(verify_session)):
    """
    Import API keys from .env file content into the database.

    Parses KEY=VALUE pairs, maps recognized environment variable names
    to api_name values used by APIKeyManager, and saves them via
    save_api_setting(). Exchange APIs group key + secret + passphrase.

    Returns: Summary of what was imported.
    """
    # Mapping from env var prefix to (api_name, role)
    # role is 'key', 'secret', or 'passphrase'
    ENV_VAR_MAP = {
        'BLOCKFROST_API_KEY': ('blockfrost', 'key'),
        'CEXPLORER_API_KEY': ('cexplorer', 'key'),
        'TAPTOOLS_API_KEY': ('taptools', 'key'),
        'ALCHEMY_API_KEY': ('alchemy', 'key'),
        'HELIUS_API_KEY': ('helius', 'key'),
        'MORALIS_API_KEY': ('moralis', 'key'),
        'ETHERSCAN_API_KEY': ('etherscan', 'key'),
        'CMC_API_KEY': ('coinmarketcap', 'key'),
        'GRAPH_API_KEY': ('graph', 'key'),
        'BEACONCHAIN_API_KEY': ('beaconchain', 'key'),
        'MAESTRO_API_KEY': ('maestro', 'key'),
        'CHARLI3_API_KEY': ('charli3', 'key'),
        # Exchange keys
        'BINANCE_API_KEY': ('binance', 'key'),
        'BINANCE_API_SECRET': ('binance', 'secret'),
        'BINANCE_US_API_KEY': ('binance_us', 'key'),
        'BINANCE_US_API_SECRET': ('binance_us', 'secret'),
        'OKX_API_KEY': ('okx', 'key'),
        'OKX_API_SECRET': ('okx', 'secret'),
        'OKX_API_PASSPHRASE': ('okx', 'passphrase'),
        'BITGET_API_KEY': ('bitget', 'key'),
        'BITGET_API_SECRET': ('bitget', 'secret'),
        'BITGET_API_PASSPHRASE': ('bitget', 'passphrase'),
        'GATE_API_KEY': ('gate', 'key'),
        'GATE_API_SECRET': ('gate', 'secret'),
        'KUCOIN_API_KEY': ('kucoin', 'key'),
        'KUCOIN_API_SECRET': ('kucoin', 'secret'),
        'KUCOIN_API_PASSPHRASE': ('kucoin', 'passphrase'),
    }

    try:
        # Parse all KEY=VALUE pairs from the content
        lines = env_content.strip().split('\n')
        parsed_vars = {}

        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    parsed_vars[key] = value

        # Group by api_name
        # Each entry: {api_name: {'key': ..., 'secret': ..., 'passphrase': ...}}
        grouped = {}
        for env_var, value in parsed_vars.items():
            if env_var in ENV_VAR_MAP:
                api_name, role = ENV_VAR_MAP[env_var]
                if api_name not in grouped:
                    grouped[api_name] = {}
                grouped[api_name][role] = value

        if not grouped:
            return {
                "success": False,
                "imported": 0,
                "skipped": 0,
                "errors": [],
                "message": "No recognized API keys found in the .env content."
            }

        # Save each API to the database
        imported = []
        skipped = []
        errors = []

        for api_name, parts in grouped.items():
            try:
                api_key = parts.get('key', '')
                if not api_key:
                    skipped.append(f"{api_name}: no key value found (only secret/passphrase)")
                    continue

                await save_api_setting(
                    api_name=api_name,
                    api_key=api_key,
                    enabled=True,
                    user_id=user_id,
                    api_secret=parts.get('secret'),
                    api_passphrase=parts.get('passphrase')
                )
                imported.append(api_name)
                logger.info(f"Imported API key for {api_name} from .env import")

            except Exception as e:
                errors.append(f"{api_name}: {str(e)}")
                logger.error(f"Failed to import API key for {api_name}: {e}")

        return {
            "success": True,
            "imported": len(imported),
            "skipped": len(skipped),
            "errors": errors,
            "imported_apis": imported,
            "skipped_apis": skipped,
            "message": f"Successfully imported {len(imported)} API key(s) into the database."
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse .env content: {str(e)}")
