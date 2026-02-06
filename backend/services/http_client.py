"""
Shared HTTP Client Pool

Provides a persistent pool of httpx.AsyncClient instances with connection keep-alive,
retry logic with exponential backoff, and graceful shutdown.

Usage:
    from services.http_client import get_client, fetch_with_retry

    # Get a persistent client (created once, reused across calls)
    client = get_client("coingecko", timeout=30.0)
    response = await client.get("https://api.coingecko.com/api/v3/ping")

    # With automatic retry on transient failures
    response = await fetch_with_retry(client, "GET", "https://api.coingecko.com/api/v3/simple/price", params={...})
"""

import httpx
import asyncio
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

# Connection pool limits shared by all clients
_default_limits = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10,
    keepalive_expiry=300
)

# Registry of named clients
_clients: Dict[str, httpx.AsyncClient] = {}


def get_client(
    name: str,
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None
) -> httpx.AsyncClient:
    """
    Return (or create) a persistent httpx.AsyncClient for the given name.

    Args:
        name: Unique name for this client (e.g. "coingecko", "blockfrost").
        timeout: Default request timeout in seconds.
        headers: Optional default headers applied to every request from this client.

    Returns:
        A long-lived httpx.AsyncClient instance.
    """
    if name not in _clients:
        _clients[name] = httpx.AsyncClient(
            timeout=timeout,
            limits=_default_limits,
            headers=headers or {},
        )
        logger.debug(f"Created HTTP client '{name}' (timeout={timeout}s)")
    return _clients[name]


async def fetch_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    retry_statuses: Optional[Set[int]] = None,
    **kwargs
) -> httpx.Response:
    """
    Make an HTTP request with automatic retry and exponential backoff.

    Args:
        client: The httpx.AsyncClient to use.
        method: HTTP method (GET, POST, etc.).
        url: Target URL.
        max_retries: Maximum number of retry attempts.
        backoff_base: Base delay in seconds (doubles each retry).
        retry_statuses: HTTP status codes that trigger a retry.
            Defaults to {429, 500, 502, 503, 504}.
        **kwargs: Additional keyword arguments passed to client.request().

    Returns:
        The httpx.Response from the successful (or final) attempt.

    Raises:
        The last exception if all retries are exhausted.
    """
    if retry_statuses is None:
        retry_statuses = {429, 500, 502, 503, 504}

    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)

            if response.status_code not in retry_statuses or attempt == max_retries:
                return response

            # Retryable status code - back off and try again
            delay = backoff_base * (2 ** attempt)
            logger.warning(
                f"HTTP {response.status_code} from {url} (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                httpx.PoolTimeout, httpx.ConnectTimeout) as exc:
            last_exc = exc
            if attempt == max_retries:
                raise

            delay = backoff_base * (2 ** attempt)
            logger.warning(
                f"HTTP error {type(exc).__name__} for {url} (attempt {attempt + 1}/{max_retries + 1}), "
                f"retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    if last_exc:
        raise last_exc
    raise RuntimeError("fetch_with_retry: unexpected state")


async def close_all():
    """
    Close all persistent HTTP clients.

    Call this during application shutdown to release connections cleanly.
    """
    client_names = list(_clients.keys())
    for name in client_names:
        try:
            await _clients[name].aclose()
            logger.debug(f"Closed HTTP client '{name}'")
        except Exception as e:
            logger.warning(f"Error closing HTTP client '{name}': {e}")
    _clients.clear()
    logger.info(f"Closed {len(client_names)} HTTP client(s)")
