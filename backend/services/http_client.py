"""
Shared HTTP Client Pool

Provides a persistent pool of httpx.AsyncClient instances with connection keep-alive,
retry logic with exponential backoff, and graceful shutdown.

Usage:
    from services.http_client import get_client, fetch_with_retry, blockfrost_fetch

    # Get a persistent client (created once, reused across calls)
    client = get_client("coingecko", timeout=30.0)
    response = await client.get("https://api.coingecko.com/api/v3/ping")

    # With automatic retry on transient failures
    response = await fetch_with_retry(client, "GET", "https://api.coingecko.com/api/v3/simple/price", params={...})

    # Blockfrost with automatic RYO -> external fallback
    response = await blockfrost_fetch("/addresses/{address}", headers={"project_id": key})
"""

import httpx
import asyncio
import logging
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)

# httpx logs one INFO line per request including the full URL — which leaks
# tokened image URLs and API-key query strings into the logs and drowns the
# useful lines. Warnings and errors still come through.
logging.getLogger("httpx").setLevel(logging.WARNING)

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


_FALLBACK_STATUSES = {500, 502, 503, 504}


async def blockfrost_fetch(
    path: str,
    *,
    method: str = "GET",
    timeout: float = 30.0,
    **kwargs,
) -> httpx.Response:
    """
    Make a Blockfrost API request with automatic fallback from internal RYO
    to external Blockfrost.io.

    Tries BLOCKFROST_BASE_URL first. On connection error, timeout, or 5xx,
    retries the same request against BLOCKFROST_EXTERNAL_URL.

    Args:
        path: API path (e.g. "/addresses/{addr}"). Must start with "/".
        method: HTTP method (default GET).
        timeout: Request timeout in seconds.
        **kwargs: Additional keyword arguments passed to client.request()
            (headers, params, json, etc.).

    Returns:
        httpx.Response from whichever endpoint succeeded (or the last failure).
    """
    from config import BLOCKFROST_BASE_URL, BLOCKFROST_EXTERNAL_URL

    client = get_client("blockfrost", timeout=timeout)
    primary_url = f"{BLOCKFROST_BASE_URL}{path}"

    # Try primary (internal RYO)
    try:
        response = await client.request(method, primary_url, timeout=timeout, **kwargs)
        if response.status_code not in _FALLBACK_STATUSES:
            return response
        # 5xx from primary — fall through to external
        logger.warning(
            f"Blockfrost primary returned {response.status_code} for {path}, "
            f"falling back to external"
        )
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
            httpx.PoolTimeout, httpx.ConnectTimeout) as exc:
        logger.warning(
            f"Blockfrost primary {type(exc).__name__} for {path}, "
            f"falling back to external"
        )

    # If primary == external, no point retrying the same URL
    if BLOCKFROST_BASE_URL == BLOCKFROST_EXTERNAL_URL:
        # Re-raise or return the failed response
        # Try once more with retry logic
        return await client.request(method, primary_url, timeout=timeout, **kwargs)

    # Try external fallback
    external_url = f"{BLOCKFROST_EXTERNAL_URL}{path}"
    return await client.request(method, external_url, timeout=timeout, **kwargs)


async def close_all():
    """
    Close all persistent HTTP clients.

    Call this during application shutdown to release connections cleanly.
    Each client gets a 2-second timeout to prevent blocking shutdown.
    """
    client_names = list(_clients.keys())
    for name in client_names:
        try:
            await asyncio.wait_for(_clients[name].aclose(), timeout=2.0)
            logger.debug(f"Closed HTTP client '{name}'")
        except asyncio.TimeoutError:
            logger.warning(f"Timeout closing HTTP client '{name}', skipping")
        except Exception as e:
            logger.warning(f"Error closing HTTP client '{name}': {e}")
    _clients.clear()
    logger.info(f"Closed {len(client_names)} HTTP client(s)")
