"""
API Health Check Service

Central test runner for validating API keys on save, on startup, and on demand.
Each API has a registered test type:
  - "header": GET url with key in a specific header
  - "query": GET url with {key} substituted in query string
  - "url": GET url with {key} substituted in the URL path
  - "json_rpc": POST a JSON-RPC request with key in the URL
  - "service": Delegate to an exchange service's test_connection() method
"""

import logging
from datetime import datetime
from services.http_client import get_client
from config import BLOCKFROST_BASE_URL, BLOCKFROST_EXTERNAL_URL

logger = logging.getLogger(__name__)

# Registry: api_id -> (test_type, *args)
# Entries not listed here will get "configured, not tested" status.
API_HEALTH_TESTS = {
    # Header-based: ("header", url, header_name)
    "blockfrost":    ("header", f"{BLOCKFROST_BASE_URL}/health", "project_id"),
    "taptools":      ("header", "https://openapi.taptools.io/api/v1/token/mcap", "x-api-key"),
    "moralis":       ("header", "https://deep-index.moralis.io/api/v2.2/web3/version", "X-API-Key"),
    "coinmarketcap": ("header", "https://pro-api.coinmarketcap.com/v1/key/info", "X-CMC_PRO_API_KEY"),
    "nmkr":          ("header", "https://studio-api.nmkr.io/v2/GetCounts", "Authorization"),
    "coingecko":     ("header", "https://pro-api.coingecko.com/api/v3/ping", "x-cg-pro-api-key"),
    "charli3":       ("header", "https://api.charli3.io/api/v1/tokens?page=1&pageSize=1", "x-api-key"),
    "maestro":       ("header", "https://mainnet.gomaestro-api.org/v1/ecosystem", "api-key"),
    "logostream":    ("header", "https://api.logostream.dev/v1/logo/crypto/BTC", "X-API-Key"),
    "alphavantage":  ("query", "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL&apikey={key}"),

    # Query-param: ("query", url_with_{key}_placeholder)
    "etherscan":     ("query", "https://api.etherscan.io/v2/api?chainid=1&module=stats&action=ethprice&apikey={key}"),
    "helius":        ("query", "https://api.helius.xyz/v0/addresses/11111111111111111111111111111111/balances?api-key={key}"),

    # URL-embedded key + JSON-RPC: ("json_rpc", url_with_{key}_placeholder)
    "alchemy":       ("json_rpc", "https://eth-mainnet.g.alchemy.com/v2/{key}"),
    "ankr":          ("json_rpc", "https://rpc.ankr.com/multichain/{key}"),

    # Exchange services: ("service", module_attr_name)
    "binance":       ("service", "binance_service"),
    "binance_us":    ("service", "binance_us_service"),
    "coinbase":      ("service", "coinbase_service"),
    "okx":           ("service", "okx_service"),
    "bitget":        ("service", "bitget_service"),
    "gate":          ("service", "gate_service"),
    "kucoin":        ("service", "kucoin_service"),
}


async def run_api_test(api_id: str, api_key: str = None,
                       api_secret: str = None, api_passphrase: str = None) -> dict:
    """Run a connectivity test for a single API.

    Args:
        api_id: The API identifier (e.g. "blockfrost", "binance")
        api_key: API key to test. If None, loads from DB via get_effective_api_key.
        api_secret: API secret (for exchanges)
        api_passphrase: API passphrase (for exchanges)

    Returns:
        dict with keys: success (bool), message (str), tested (bool), status_code (int|None)
    """
    if api_id not in API_HEALTH_TESTS:
        return {"success": True, "tested": False,
                "message": "Configured (no test available)", "status_code": None}

    # If no key provided, load from DB
    if api_key is None:
        from routers.settings import get_effective_api_key
        api_key = await get_effective_api_key(api_id)
        if not api_key:
            return {"success": False, "tested": True,
                    "message": "No API key configured", "status_code": None}

        # Also load secret/passphrase from DB if needed
        if api_secret is None or api_passphrase is None:
            from database import get_api_setting
            setting = await get_api_setting(api_id)
            if setting:
                if api_secret is None:
                    api_secret = setting.get("api_secret")
                if api_passphrase is None:
                    api_passphrase = setting.get("api_passphrase")

    test_config = API_HEALTH_TESTS[api_id]
    test_type = test_config[0]

    try:
        if test_type == "header":
            return await _test_header(api_id, api_key, test_config)
        elif test_type == "query":
            return await _test_query(api_id, api_key, test_config)
        elif test_type == "json_rpc":
            return await _test_json_rpc(api_id, api_key, test_config)
        elif test_type == "service":
            return await _test_service(api_id, api_key, api_secret, api_passphrase, test_config)
        else:
            return {"success": False, "tested": False,
                    "message": f"Unknown test type: {test_type}", "status_code": None}
    except Exception as e:
        logger.warning(f"API health test failed for {api_id}: {e}")
        return {"success": False, "tested": True,
                "message": str(e), "status_code": None}


async def _test_header(api_id: str, api_key: str, config: tuple) -> dict:
    """Test API with key in a request header."""
    _, url, header_name = config
    client = get_client("api_health_test", timeout=15.0)

    # Special case: NMKR expects "Bearer <key>" format
    header_value = api_key
    if api_id == "nmkr":
        if not api_key.startswith("Bearer "):
            header_value = f"Bearer {api_key}"

    response = await client.get(url, headers={header_name: header_value}, timeout=10.0)
    status = response.status_code
    success = status < 400

    # Add source info for Blockfrost (internal RYO vs external)
    extra = {}
    if api_id == "blockfrost":
        is_self_hosted = BLOCKFROST_BASE_URL != BLOCKFROST_EXTERNAL_URL
        extra["source"] = "self-hosted (RYO)" if is_self_hosted else "external"
        extra["endpoint"] = BLOCKFROST_BASE_URL

    if success:
        msg = "Connected successfully"
        if extra.get("source"):
            msg += f" ({extra['source']})"
        return {"success": True, "tested": True,
                "message": msg, "status_code": status, **extra}
    else:
        return {"success": False, "tested": True,
                "message": f"HTTP {status}", "status_code": status, **extra}


async def _test_query(api_id: str, api_key: str, config: tuple) -> dict:
    """Test API with key substituted into URL query string."""
    _, url_template = config
    url = url_template.replace("{key}", api_key)
    client = get_client("api_health_test", timeout=15.0)

    response = await client.get(url, timeout=10.0)
    status = response.status_code
    success = status < 400

    # Some APIs return 200 but indicate error in body (e.g., etherscan)
    if success and api_id == "etherscan":
        try:
            data = response.json()
            if data.get("status") == "0" and "Invalid API Key" in data.get("result", ""):
                return {"success": False, "tested": True,
                        "message": "Invalid API key", "status_code": status}
        except Exception:
            pass

    if success:
        return {"success": True, "tested": True,
                "message": "Connected successfully", "status_code": status}
    else:
        return {"success": False, "tested": True,
                "message": f"HTTP {status}", "status_code": status}


async def _test_json_rpc(api_id: str, api_key: str, config: tuple) -> dict:
    """Test API with key in URL via JSON-RPC POST (e.g., Alchemy)."""
    _, url_template = config
    url = url_template.replace("{key}", api_key)
    client = get_client("api_health_test", timeout=15.0)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_blockNumber",
        "params": []
    }
    response = await client.post(url, json=payload, timeout=10.0)
    status = response.status_code
    success = status < 400

    if success:
        try:
            data = response.json()
            if "error" in data:
                return {"success": False, "tested": True,
                        "message": data["error"].get("message", "RPC error"),
                        "status_code": status}
        except Exception:
            pass
        return {"success": True, "tested": True,
                "message": "Connected successfully", "status_code": status}
    else:
        return {"success": False, "tested": True,
                "message": f"HTTP {status}", "status_code": status}


async def _test_service(api_id: str, api_key: str, api_secret: str,
                        api_passphrase: str, config: tuple) -> dict:
    """Test exchange service by delegating to its test_connection() method."""
    _, service_attr = config

    # Import the service singleton dynamically
    service = _get_exchange_service(service_attr)
    if service is None:
        return {"success": False, "tested": True,
                "message": f"Service {service_attr} not found", "status_code": None}

    # Temporarily set credentials if provided (for test-on-save before service picks up new keys)
    original_key = getattr(service, 'api_key', None)
    original_secret = getattr(service, 'api_secret', None)
    original_passphrase = getattr(service, 'api_passphrase', None)

    try:
        if api_key:
            service.api_key = api_key
        if api_secret:
            service.api_secret = api_secret
        if api_passphrase:
            service.api_passphrase = api_passphrase

        result = await service.test_connection()
        return {
            "success": result.get("success", False),
            "tested": True,
            "message": result.get("message", "Unknown"),
            "status_code": None
        }
    finally:
        # Restore original credentials
        if original_key is not None:
            service.api_key = original_key
        if original_secret is not None:
            service.api_secret = original_secret
        if original_passphrase is not None:
            service.api_passphrase = original_passphrase


def _get_exchange_service(service_attr: str):
    """Import and return an exchange service singleton by attribute name."""
    service_map = {
        "binance_service": ("services.binance_service", "binance_service"),
        "binance_us_service": ("services.binance_us_service", "binance_us_service"),
        "coinbase_service": ("services.coinbase", "coinbase_service"),
        "okx_service": ("services.okx_service", "okx_service"),
        "bitget_service": ("services.bitget_service", "bitget_service"),
        "gate_service": ("services.gate_service", "gate_service"),
        "kucoin_service": ("services.kucoin_service", "kucoin_service"),
    }

    if service_attr not in service_map:
        return None

    module_path, attr_name = service_map[service_attr]
    try:
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr_name, None)
    except ImportError as e:
        logger.warning(f"Could not import {module_path}: {e}")
        return None


async def run_startup_health_checks():
    """Run health checks for all enabled APIs on startup.

    Results are stored in DB but APIs are NOT auto-disabled
    (startup failures may be transient network issues).
    """
    from database import get_all_api_settings, get_all_users, update_api_health

    users = await get_all_users()
    non_demo = [u for u in users if not u.get('is_demo', False)]

    for user in non_demo:
        user_id = user['id']
        settings = await get_all_api_settings(user_id=user_id)
        enabled_apis = [s for s in settings if s.get('enabled') and s.get('api_key')]

        if not enabled_apis:
            continue

        results = {}
        for setting in enabled_apis:
            api_name = setting['api_name']
            try:
                result = await run_api_test(
                    api_name,
                    api_key=setting.get('api_key'),
                    api_secret=setting.get('api_secret'),
                    api_passphrase=setting.get('api_passphrase')
                )
                await update_api_health(api_name, user_id, result)

                if result.get("tested"):
                    status_str = "OK" if result["success"] else f"FAIL ({result.get('message', '?')})"
                else:
                    status_str = "no test"
                results[api_name] = status_str
            except Exception as e:
                results[api_name] = f"ERROR ({e})"
                logger.warning(f"Health check error for {api_name}: {e}")

        # Log summary for this user
        summary = ", ".join(f"{k}={v}" for k, v in results.items())
        logger.info(f"API health (user {user_id}): {summary}")
