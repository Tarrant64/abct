"""
Localhost Middleware - Localhost-only enforcement for ABCT

Provides functionality to restrict endpoints to localhost access only:
- Supports IPv4 (127.0.0.1)
- Supports IPv6 (::1)
- Supports hostname (localhost)
- Useful for development or sensitive operations

Usage:
    from middleware.localhost import require_localhost

    @router.post("/endpoint", dependencies=[Depends(require_localhost)])
    async def localhost_only_endpoint():
        ...
"""

from fastapi import Request, HTTPException, Depends


def is_localhost(request: Request) -> bool:
    """
    Check if the request is coming from localhost.

    Supports:
        - IPv4: 127.0.0.1
        - IPv6: ::1
        - Hostname: localhost

    Args:
        request: FastAPI Request object

    Returns:
        True if request is from localhost, False otherwise
    """
    # Get client host from request
    client_host = request.client.host if request.client else None

    if not client_host:
        return False

    # Normalize the host string
    client_host = client_host.lower().strip()

    # Check for localhost patterns
    localhost_patterns = [
        '127.0.0.1',
        'localhost',
        '::1',           # IPv6 localhost
        '0:0:0:0:0:0:0:1'  # Expanded IPv6 localhost
    ]

    # Also check for 127.0.0.0/8 range (127.0.0.0 - 127.255.255.255)
    if client_host.startswith('127.'):
        return True

    return client_host in localhost_patterns


async def require_localhost(request: Request) -> str:
    """
    Dependency that requires the request to come from localhost.

    This can be used to restrict sensitive endpoints to local access only:
        @router.post("/endpoint", dependencies=[Depends(require_localhost)])
        async def localhost_only_endpoint():
            ...

    Args:
        request: FastAPI Request object

    Returns:
        Client host string if request is from localhost

    Raises:
        HTTPException: 403 Forbidden if request is not from localhost
    """
    if not is_localhost(request):
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only accessible from localhost"
        )

    return request.client.host


async def optional_localhost(request: Request) -> bool:
    """
    Optional localhost check that doesn't raise an exception.

    Returns True if from localhost, False otherwise.
    Useful for conditional logic based on request origin.

    Args:
        request: FastAPI Request object

    Returns:
        True if request is from localhost, False otherwise
    """
    return is_localhost(request)
