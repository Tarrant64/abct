"""
Request Size Limit Middleware

Prevents DoS attacks via large request bodies by enforcing configurable size limits.

Configuration:
    - ABCT_MAX_BODY_SIZE: Maximum request body size in bytes (default: 10MB)
    - ABCT_MAX_UPLOAD_SIZE: Maximum upload size in bytes (default: 5MB)

Usage:
    from middleware import RequestSizeLimitMiddleware

    app.add_middleware(RequestSizeLimitMiddleware)
"""

import os
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.datastructures import Headers
import logging

logger = logging.getLogger(__name__)

# Default limits (in bytes)
DEFAULT_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB for regular requests
DEFAULT_MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB for file uploads

# Environment variable configuration
MAX_BODY_SIZE = int(os.getenv("ABCT_MAX_BODY_SIZE", DEFAULT_MAX_BODY_SIZE))
MAX_UPLOAD_SIZE = int(os.getenv("ABCT_MAX_UPLOAD_SIZE", DEFAULT_MAX_UPLOAD_SIZE))

# Paths that accept file uploads
UPLOAD_PATHS = [
    "/security/certificate/upload",
]


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request body size limits.

    Checks Content-Length header before processing the request.
    Returns 413 Payload Too Large if the request exceeds configured limits.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and check size limits.

        Args:
            request: The incoming HTTP request
            call_next: The next middleware or endpoint handler

        Returns:
            Response from the next handler or 413 error
        """
        # Skip size check for GET, HEAD, OPTIONS (no body)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        # Get Content-Length header
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                content_length = int(content_length)
            except ValueError:
                logger.warning(f"Invalid Content-Length header: {content_length}")
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Invalid Content-Length header",
                        "error_code": "INVALID_CONTENT_LENGTH"
                    }
                )

            # Determine which limit to apply
            path = request.url.path
            is_upload = any(upload_path in path for upload_path in UPLOAD_PATHS)

            max_size = MAX_UPLOAD_SIZE if is_upload else MAX_BODY_SIZE
            limit_type = "upload" if is_upload else "request"

            # Check if request exceeds limit
            if content_length > max_size:
                logger.warning(
                    f"Request to {path} exceeds {limit_type} size limit: "
                    f"{content_length} bytes > {max_size} bytes"
                )

                # Format size for human readability
                def format_bytes(size):
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if size < 1024.0:
                            return f"{size:.1f}{unit}"
                        size /= 1024.0
                    return f"{size:.1f}TB"

                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"Request body too large. Maximum {limit_type} size is {format_bytes(max_size)}",
                        "error_code": "REQUEST_TOO_LARGE",
                        "max_size_bytes": max_size,
                        "received_size_bytes": content_length,
                        "limit_type": limit_type
                    }
                )

        # Process request
        return await call_next(request)


def get_size_limits():
    """
    Get current size limit configuration.

    Returns:
        dict: Current size limits in bytes and formatted strings
    """
    def format_bytes(size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f}{unit}"
            size /= 1024.0
        return f"{size:.1f}TB"

    return {
        "max_body_size": {
            "bytes": MAX_BODY_SIZE,
            "formatted": format_bytes(MAX_BODY_SIZE)
        },
        "max_upload_size": {
            "bytes": MAX_UPLOAD_SIZE,
            "formatted": format_bytes(MAX_UPLOAD_SIZE)
        },
        "upload_paths": UPLOAD_PATHS
    }
