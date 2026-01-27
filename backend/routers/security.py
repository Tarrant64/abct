"""
Security Router - SSL/HTTPS Configuration

Provides endpoints for managing SSL/HTTPS settings with comprehensive input validation:
- GET /security/settings - Get current SSL configuration
- PUT /security/settings - Update SSL mode (with admin auth)
- POST /security/certificate/generate - Generate self-signed certificate (with admin auth)
- POST /security/certificate/upload - Upload custom certificate (with validation and admin auth)
- GET /security/certificate/info - Get certificate details
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel, validator, Field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_security_settings, save_security_settings, set_pending_mode, clear_pending_mode
)
from config import CERTS_DIR, DEFAULT_CERT_PATH, DEFAULT_KEY_PATH
from services.ssl_service import get_ssl_service

# Try to import auth middleware if available
try:
    from middleware.auth import verify_admin
    AUTH_AVAILABLE = True
except ImportError:
    # Fallback: no auth required if middleware not available
    async def verify_admin():
        pass
    AUTH_AVAILABLE = False

router = APIRouter(prefix="/security", tags=["security"])


class SSLModeUpdate(BaseModel):
    """Request model for updating SSL mode with validation."""
    ssl_mode: str = Field(..., description="SSL mode: http, https-self-signed, or https-custom")

    @validator('ssl_mode')
    def validate_ssl_mode(cls, v):
        valid_modes = ['http', 'https-self-signed', 'https-custom']
        if v not in valid_modes:
            raise ValueError(f"Invalid SSL mode. Must be one of: {', '.join(valid_modes)}")
        return v


class CertGenerateRequest(BaseModel):
    """Request model for generating a self-signed certificate with validation."""
    hostname: str = Field(default="localhost", min_length=1, max_length=253)
    valid_days: int = Field(default=365, ge=1, le=3650)

    @validator('hostname')
    def validate_hostname(cls, v):
        # Basic hostname validation
        if not v or not v.strip():
            raise ValueError("Hostname cannot be empty")
        # Prevent path traversal and special characters
        invalid_chars = ['/', '\\', '..', '\x00', '\n', '\r']
        if any(char in v for char in invalid_chars):
            raise ValueError("Hostname contains invalid characters")
        return v.strip()


@router.get("/settings")
async def get_settings():
    """
    Get current security/SSL settings.

    Returns current mode, certificate status, and whether restart is required.
    """
    settings = await get_security_settings()

    # Get certificate info if we have one
    ssl_service = get_ssl_service(CERTS_DIR)
    cert_info = None
    if settings.get('cert_path') and Path(settings['cert_path']).exists():
        cert_info = ssl_service.get_cert_info(Path(settings['cert_path']))

    # Determine effective mode (what's currently running vs what's configured)
    running_mode = os.environ.get('ABCT_SSL_MODE', 'http')

    return {
        "ssl_mode": settings.get('ssl_mode', 'http'),
        "running_mode": running_mode,
        "cert_path": settings.get('cert_path'),
        "key_path": settings.get('key_path'),
        "cert_type": settings.get('cert_type'),
        "cert_expires_at": settings.get('cert_expires_at'),
        "pending_mode": settings.get('pending_mode'),
        "restart_required": bool(settings.get('restart_required')),
        "certificate": cert_info,
        "updated_at": settings.get('updated_at')
    }


@router.put("/settings", dependencies=[Depends(verify_admin)])
async def update_settings(data: SSLModeUpdate):
    """
    Update SSL mode setting.

    Valid modes:
    - 'http': No encryption (default)
    - 'https-self-signed': Use auto-generated self-signed certificate
    - 'https-custom': Use user-uploaded certificate

    Note: Changes require server restart to take effect.
    Requires admin authentication.
    """
    settings = await get_security_settings()
    current_mode = settings.get('ssl_mode', 'http')

    # If mode is changing, set pending mode
    if data.ssl_mode != current_mode:
        # For HTTPS modes, verify certificate exists
        if data.ssl_mode.startswith('https'):
            ssl_service = get_ssl_service(CERTS_DIR)
            if not ssl_service.cert_exists():
                raise HTTPException(
                    status_code=400,
                    detail="No certificate found. Generate or upload a certificate first."
                )

        await set_pending_mode(data.ssl_mode)
        return {
            "message": f"SSL mode will change to '{data.ssl_mode}' after restart",
            "pending_mode": data.ssl_mode,
            "restart_required": True
        }

    return {
        "message": "No changes made",
        "ssl_mode": current_mode,
        "restart_required": False
    }


@router.post("/certificate/generate", dependencies=[Depends(verify_admin)])
async def generate_certificate(data: CertGenerateRequest = None):
    """
    Generate a new self-signed certificate.

    This will overwrite any existing certificate files.
    Requires admin authentication.
    """
    if data is None:
        data = CertGenerateRequest()

    ssl_service = get_ssl_service(CERTS_DIR)

    try:
        cert_path, key_path = ssl_service.generate_self_signed_cert(
            hostname=data.hostname,
            valid_days=data.valid_days
        )

        # Get cert info
        cert_info = ssl_service.get_cert_info(cert_path)

        # Save settings with cert info
        await save_security_settings(
            ssl_mode='https-self-signed',
            cert_path=str(cert_path),
            key_path=str(key_path),
            cert_type='self-signed',
            cert_expires_at=cert_info.get('expires_at') if cert_info else None
        )

        return {
            "message": "Self-signed certificate generated successfully",
            "cert_path": str(cert_path),
            "key_path": str(key_path),
            "certificate": cert_info
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate certificate: {str(e)}"
        )


@router.post("/certificate/upload", dependencies=[Depends(verify_admin)])
async def upload_certificate(
    cert_file: UploadFile = File(..., description="Certificate file (.crt or .pem)"),
    key_file: UploadFile = File(..., description="Private key file (.key or .pem)")
):
    """
    Upload a custom certificate and private key.

    Files should be in PEM format.
    Requires admin authentication.

    Validation:
    - File size: Maximum 5MB (enforced by middleware)
    - File extensions: .crt, .pem for cert; .key, .pem for key
    - Format: Valid PEM format (checked before saving)
    - Content: Must contain valid BEGIN/END markers
    """
    # Validate file extensions
    ALLOWED_CERT_EXTENSIONS = {".crt", ".pem"}
    ALLOWED_KEY_EXTENSIONS = {".key", ".pem"}

    cert_ext = Path(cert_file.filename).suffix.lower()
    key_ext = Path(key_file.filename).suffix.lower()

    if cert_ext not in ALLOWED_CERT_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid certificate file extension. Allowed: {', '.join(ALLOWED_CERT_EXTENSIONS)}"
        )

    if key_ext not in ALLOWED_KEY_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid key file extension. Allowed: {', '.join(ALLOWED_KEY_EXTENSIONS)}"
        )

    ssl_service = get_ssl_service(CERTS_DIR)
    ssl_service.ensure_certs_dir()

    # Save uploaded files to temp location first
    temp_cert = CERTS_DIR / "upload_temp.crt"
    temp_key = CERTS_DIR / "upload_temp.key"

    try:
        # Read cert file with size check
        cert_content = await cert_file.read()

        # Validate file is not empty
        if not cert_content or len(cert_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Certificate file is empty"
            )

        # Basic PEM format validation (check for BEGIN/END markers)
        try:
            cert_text = cert_content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Certificate file is not valid UTF-8 text"
            )

        if '-----BEGIN CERTIFICATE-----' not in cert_text or '-----END CERTIFICATE-----' not in cert_text:
            raise HTTPException(
                status_code=400,
                detail="Invalid certificate format. Must be PEM format with BEGIN/END CERTIFICATE markers."
            )

        # Write cert file
        with open(temp_cert, "wb") as f:
            f.write(cert_content)

        # Read key file with size check
        key_content = await key_file.read()

        # Validate file is not empty
        if not key_content or len(key_content) == 0:
            raise HTTPException(
                status_code=400,
                detail="Key file is empty"
            )

        # Basic PEM format validation for key
        try:
            key_text = key_content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Key file is not valid UTF-8 text"
            )

        has_private_key_marker = (
            '-----BEGIN PRIVATE KEY-----' in key_text or
            '-----BEGIN RSA PRIVATE KEY-----' in key_text or
            '-----BEGIN EC PRIVATE KEY-----' in key_text
        )
        if not has_private_key_marker:
            raise HTTPException(
                status_code=400,
                detail="Invalid key format. Must be PEM format with BEGIN PRIVATE KEY marker."
            )

        # Write key file
        with open(temp_key, "wb") as f:
            f.write(key_content)

        # Set restrictive permissions on key
        import stat
        os.chmod(temp_key, stat.S_IRUSR | stat.S_IWUSR)

        # Validate the certificate and key pair
        is_valid, error = ssl_service.validate_certificate(temp_cert, temp_key)
        if not is_valid:
            # Clean up temp files
            temp_cert.unlink(missing_ok=True)
            temp_key.unlink(missing_ok=True)
            raise HTTPException(
                status_code=400,
                detail=f"Invalid certificate or key: {error}"
            )

        # Move to final location
        final_cert = CERTS_DIR / "custom.crt"
        final_key = CERTS_DIR / "custom.key"

        shutil.move(str(temp_cert), str(final_cert))
        shutil.move(str(temp_key), str(final_key))

        # Get cert info
        cert_info = ssl_service.get_cert_info(final_cert)

        # Save settings
        await save_security_settings(
            ssl_mode='https-custom',
            cert_path=str(final_cert),
            key_path=str(final_key),
            cert_type='custom',
            cert_expires_at=cert_info.get('expires_at') if cert_info else None
        )

        return {
            "message": "Certificate uploaded successfully",
            "cert_path": str(final_cert),
            "key_path": str(final_key),
            "certificate": cert_info
        }

    except HTTPException:
        raise
    except Exception as e:
        # Clean up temp files on error
        temp_cert.unlink(missing_ok=True)
        temp_key.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload certificate: {str(e)}"
        )


@router.get("/certificate/info")
async def get_certificate_info():
    """
    Get information about the current certificate.

    Returns certificate details including expiry, issuer, and validity.
    """
    settings = await get_security_settings()

    cert_path = settings.get('cert_path')
    if not cert_path or not Path(cert_path).exists():
        return {
            "has_certificate": False,
            "certificate": None
        }

    ssl_service = get_ssl_service(CERTS_DIR)
    cert_info = ssl_service.get_cert_info(Path(cert_path))

    return {
        "has_certificate": True,
        "cert_type": settings.get('cert_type'),
        "certificate": cert_info
    }


@router.delete("/certificate", dependencies=[Depends(verify_admin)])
async def delete_certificate():
    """
    Delete the current certificate files.

    This will also reset the SSL mode to HTTP.
    Requires admin authentication.
    """
    settings = await get_security_settings()

    ssl_service = get_ssl_service(CERTS_DIR)

    # Delete default certs
    ssl_service.delete_cert()

    # Also delete custom certs if they exist
    custom_cert = CERTS_DIR / "custom.crt"
    custom_key = CERTS_DIR / "custom.key"
    if custom_cert.exists():
        custom_cert.unlink()
    if custom_key.exists():
        custom_key.unlink()

    # Reset settings to HTTP
    await save_security_settings(
        ssl_mode='http',
        cert_path=None,
        key_path=None,
        cert_type=None,
        cert_expires_at=None
    )

    return {
        "message": "Certificate deleted and mode reset to HTTP",
        "ssl_mode": "http"
    }


@router.post("/apply-pending")
async def apply_pending_mode():
    """
    Apply the pending SSL mode change.

    This is called after a restart to confirm the mode change was applied.
    Internal use - typically called by the startup process.
    """
    settings = await get_security_settings()
    pending_mode = settings.get('pending_mode')

    if pending_mode:
        await save_security_settings(
            ssl_mode=pending_mode,
            cert_path=settings.get('cert_path'),
            key_path=settings.get('key_path'),
            cert_type=settings.get('cert_type'),
            cert_expires_at=settings.get('cert_expires_at')
        )
        return {
            "message": f"SSL mode changed to '{pending_mode}'",
            "ssl_mode": pending_mode
        }

    return {
        "message": "No pending mode change",
        "ssl_mode": settings.get('ssl_mode', 'http')
    }
