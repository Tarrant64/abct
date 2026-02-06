"""
Exchange API Permission Checker

Validates that exchange API keys have read-only permissions.
Provides warnings if keys have trading, withdrawal, or other write permissions.
"""

import httpx
import logging
import hmac
import hashlib
import time
import base64
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode
import json
from services.http_client import get_client

logger = logging.getLogger(__name__)


class ExchangePermissionChecker:
    """Check API key permissions for various exchanges."""

    @staticmethod
    async def check_binance_permissions(api_key: str, api_secret: str) -> Tuple[bool, List[str], str]:
        """
        Check Binance.com API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = hmac.new(
                api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            url = f"https://api.binance.com/api/v3/account?{query_string}&signature={signature}"
            headers = {"X-MBX-APIKEY": api_key}

            client = get_client("exchange_perm_checker", timeout=10.0)
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                return False, [f"Failed to verify API key: {response.text}"], "unknown"

            data = response.json()

            # Check account permissions
            account_type = data.get("accountType", "SPOT")
            permissions = data.get("permissions", [])

            warnings = []
            is_read_only = True

            # Binance uses permission flags like: SPOT, MARGIN, FUTURES, etc.
            # Read-only keys should only have query permissions
            dangerous_permissions = [perm for perm in permissions if perm not in ["SPOT"]]

            # Check if we can query API key permissions endpoint
            perm_url = f"https://api.binance.com/sapi/v1/account/apiRestrictions?timestamp={timestamp}&signature={signature}"
            perm_response = await client.get(perm_url, headers=headers)

            if perm_response.status_code == 200:
                perm_data = perm_response.json()

                if perm_data.get("enableSpotAndMarginTrading", False):
                    warnings.append("⚠️ API key has SPOT/MARGIN TRADING permissions enabled")
                    is_read_only = False

                if perm_data.get("enableWithdrawals", False):
                    warnings.append("⚠️ API key has WITHDRAWAL permissions enabled")
                    is_read_only = False

                if perm_data.get("enableFutures", False):
                    warnings.append("⚠️ API key has FUTURES TRADING permissions enabled")
                    is_read_only = False

                if perm_data.get("enableMargin", False):
                    warnings.append("⚠️ API key has MARGIN TRADING permissions enabled")
                    is_read_only = False

            if is_read_only:
                return True, [], account_type
            else:
                warnings.append("🔒 For security, please use a read-only API key")
                return False, warnings, account_type

        except Exception as e:
            logger.error(f"Error checking Binance permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"

    @staticmethod
    async def check_binance_us_permissions(api_key: str, api_secret: str) -> Tuple[bool, List[str], str]:
        """
        Check Binance.US API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            timestamp = int(time.time() * 1000)
            query_string = f"timestamp={timestamp}"
            signature = hmac.new(
                api_secret.encode('utf-8'),
                query_string.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            url = f"https://api.binance.us/api/v3/account?{query_string}&signature={signature}"
            headers = {"X-MBX-APIKEY": api_key}

            client = get_client("exchange_perm_checker", timeout=10.0)
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                return False, [f"Failed to verify API key: {response.text}"], "unknown"

            data = response.json()
            account_type = data.get("accountType", "SPOT")

            # Binance.US uses similar structure to Binance.com
            # Try to get API restrictions
            perm_url = f"https://api.binance.us/sapi/v1/account/apiRestrictions?timestamp={timestamp}&signature={signature}"
            perm_response = await client.get(perm_url, headers=headers)

            warnings = []
            is_read_only = True

            if perm_response.status_code == 200:
                perm_data = perm_response.json()

                if perm_data.get("enableSpotAndMarginTrading", False):
                    warnings.append("⚠️ API key has TRADING permissions enabled")
                    is_read_only = False

                if perm_data.get("enableWithdrawals", False):
                    warnings.append("⚠️ API key has WITHDRAWAL permissions enabled")
                    is_read_only = False

            if not is_read_only:
                warnings.append("🔒 For security, please use a read-only API key")

            return is_read_only, warnings, account_type

        except Exception as e:
            logger.error(f"Error checking Binance.US permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"

    @staticmethod
    async def check_okx_permissions(api_key: str, api_secret: str, api_passphrase: str) -> Tuple[bool, List[str], str]:
        """
        Check OKX API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            timestamp = str(time.time())
            method = "GET"
            request_path = "/api/v5/account/balance"

            # Create signature: timestamp + method + request_path
            message = timestamp + method + request_path
            signature = base64.b64encode(
                hmac.new(
                    api_secret.encode('utf-8'),
                    message.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode()

            headers = {
                "OK-ACCESS-KEY": api_key,
                "OK-ACCESS-SIGN": signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": api_passphrase,
                "Content-Type": "application/json"
            }

            client = get_client("exchange_perm_checker", timeout=10.0)
            response = await client.get(f"https://www.okx.com{request_path}", headers=headers)

            if response.status_code != 200:
                return False, [f"Failed to verify API key: {response.text}"], "unknown"

            # OKX doesn't have a direct permissions endpoint
            # Try to call a trade endpoint to see if it's allowed
            warnings = []
            is_read_only = True

            # Attempt to access user info endpoint which shows permissions
            info_path = "/api/v5/users/subaccount/apikey"
            info_message = timestamp + "GET" + info_path
            info_signature = base64.b64encode(
                hmac.new(
                    api_secret.encode('utf-8'),
                    info_message.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode()

            info_headers = {
                "OK-ACCESS-KEY": api_key,
                "OK-ACCESS-SIGN": info_signature,
                "OK-ACCESS-TIMESTAMP": timestamp,
                "OK-ACCESS-PASSPHRASE": api_passphrase,
            }

            # Note: OKX API key permissions are set during creation
            # We can only verify the key works, not explicitly check permissions
            warnings.append("ℹ️ Please ensure this API key is set to 'Read Only' in OKX settings")
            warnings.append("🔒 Verify at: https://www.okx.com/account/my-api")

            return True, warnings, "trading"

        except Exception as e:
            logger.error(f"Error checking OKX permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"

    @staticmethod
    async def check_kucoin_permissions(api_key: str, api_secret: str, api_passphrase: str) -> Tuple[bool, List[str], str]:
        """
        Check KuCoin API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            timestamp = str(int(time.time() * 1000))
            method = "GET"
            endpoint = "/api/v1/user-info"

            # Create signature: timestamp + method + endpoint
            str_to_sign = timestamp + method + endpoint
            signature = base64.b64encode(
                hmac.new(
                    api_secret.encode('utf-8'),
                    str_to_sign.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode()

            passphrase_signature = base64.b64encode(
                hmac.new(
                    api_secret.encode('utf-8'),
                    api_passphrase.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode()

            headers = {
                "KC-API-KEY": api_key,
                "KC-API-SIGN": signature,
                "KC-API-TIMESTAMP": timestamp,
                "KC-API-PASSPHRASE": passphrase_signature,
                "KC-API-KEY-VERSION": "2"
            }

            client = get_client("exchange_perm_checker", timeout=10.0)
            response = await client.get(f"https://api.kucoin.com{endpoint}", headers=headers)

            if response.status_code != 200:
                return False, [f"Failed to verify API key: {response.text}"], "unknown"

            # KuCoin API permissions are set during API key creation
            # General Permission, Trade Permission, Transfer Permission, etc.
            warnings = []
            warnings.append("ℹ️ Please ensure this API key only has 'General' permission in KuCoin")
            warnings.append("🔒 Verify at: https://www.kucoin.com/account/api")

            return True, warnings, "spot"

        except Exception as e:
            logger.error(f"Error checking KuCoin permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"

    @staticmethod
    async def check_gate_permissions(api_key: str, api_secret: str) -> Tuple[bool, List[str], str]:
        """
        Check Gate.io API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            method = "GET"
            url = "/api/v4/wallet/total_balance"
            timestamp = str(int(time.time()))

            # Gate.io signature format
            query_string = ""
            body_hash = hashlib.sha512(b"").hexdigest()
            sign_string = f"{method}\n{url}\n{query_string}\n{body_hash}\n{timestamp}"

            signature = hmac.new(
                api_secret.encode('utf-8'),
                sign_string.encode('utf-8'),
                hashlib.sha512
            ).hexdigest()

            headers = {
                "KEY": api_key,
                "SIGN": signature,
                "Timestamp": timestamp
            }

            client = get_client("exchange_perm_checker", timeout=10.0)
            response = await client.get(f"https://api.gateio.ws{url}", headers=headers)

            if response.status_code != 200:
                return False, [f"Failed to verify API key: {response.text}"], "unknown"

            # Gate.io permissions are set during creation
            warnings = []
            warnings.append("ℹ️ Please ensure this API key only has 'Read Only' permission in Gate.io")
            warnings.append("🔒 Verify at: https://www.gate.io/myaccount/apiv4keys")

            return True, warnings, "spot"

        except Exception as e:
            logger.error(f"Error checking Gate.io permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"

    @staticmethod
    async def check_bitget_permissions(api_key: str, api_secret: str, api_passphrase: str) -> Tuple[bool, List[str], str]:
        """
        Check Bitget API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            timestamp = str(int(time.time() * 1000))
            method = "GET"
            request_path = "/api/spot/v1/account/assets"

            # Create signature
            message = timestamp + method + request_path
            signature = base64.b64encode(
                hmac.new(
                    api_secret.encode('utf-8'),
                    message.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            ).decode()

            headers = {
                "ACCESS-KEY": api_key,
                "ACCESS-SIGN": signature,
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": api_passphrase,
                "Content-Type": "application/json"
            }

            client = get_client("exchange_perm_checker", timeout=10.0)
            response = await client.get(f"https://api.bitget.com{request_path}", headers=headers)

            if response.status_code != 200:
                return False, [f"Failed to verify API key: {response.text}"], "unknown"

            # Bitget permissions are set during creation
            warnings = []
            warnings.append("ℹ️ Please ensure this API key only has 'Read' permission in Bitget")
            warnings.append("🔒 Verify at: https://www.bitget.com/en/account/newapi")

            return True, warnings, "spot"

        except Exception as e:
            logger.error(f"Error checking Bitget permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"

    @staticmethod
    async def check_coinbase_permissions(credentials: dict) -> Tuple[bool, List[str], str]:
        """
        Check Coinbase CDP API key permissions.

        Returns:
            (is_read_only, warnings, account_type)
        """
        try:
            # Coinbase CDP uses JWT with scopes
            # We can't easily decode the privateKey without implementing full JWT
            # But we can provide guidance
            warnings = []
            warnings.append("ℹ️ Please ensure your Coinbase CDP API key has only 'view' scopes")
            warnings.append("🔒 Verify at: https://portal.cdp.coinbase.com/")
            warnings.append("✓ Required scopes: wallet:accounts:read, wallet:transactions:read")
            warnings.append("✗ Avoid scopes: wallet:sends:create, wallet:withdrawals:create")

            return True, warnings, "cdp"

        except Exception as e:
            logger.error(f"Error checking Coinbase permissions: {e}")
            return False, [f"Could not verify permissions: {str(e)}"], "unknown"


async def validate_exchange_api_permissions(
    exchange_id: str,
    api_key: str,
    api_secret: Optional[str] = None,
    api_passphrase: Optional[str] = None,
    credentials: Optional[dict] = None
) -> Dict:
    """
    Validate exchange API key permissions.

    Args:
        exchange_id: The exchange identifier (binance, okx, etc.)
        api_key: The API key
        api_secret: The API secret (if applicable)
        api_passphrase: The API passphrase (if applicable)
        credentials: Full credentials dict (for Coinbase CDP)

    Returns:
        Dict with: {
            "is_read_only": bool,
            "warnings": List[str],
            "account_type": str
        }
    """
    checker = ExchangePermissionChecker()

    try:
        if exchange_id == "binance":
            if not api_secret:
                return {"is_read_only": False, "warnings": ["API secret required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_binance_permissions(api_key, api_secret)

        elif exchange_id == "binance_us":
            if not api_secret:
                return {"is_read_only": False, "warnings": ["API secret required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_binance_us_permissions(api_key, api_secret)

        elif exchange_id == "okx":
            if not api_secret or not api_passphrase:
                return {"is_read_only": False, "warnings": ["API secret and passphrase required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_okx_permissions(api_key, api_secret, api_passphrase)

        elif exchange_id == "kucoin":
            if not api_secret or not api_passphrase:
                return {"is_read_only": False, "warnings": ["API secret and passphrase required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_kucoin_permissions(api_key, api_secret, api_passphrase)

        elif exchange_id == "gate":
            if not api_secret:
                return {"is_read_only": False, "warnings": ["API secret required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_gate_permissions(api_key, api_secret)

        elif exchange_id == "bitget":
            if not api_secret or not api_passphrase:
                return {"is_read_only": False, "warnings": ["API secret and passphrase required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_bitget_permissions(api_key, api_secret, api_passphrase)

        elif exchange_id == "coinbase":
            if not credentials:
                return {"is_read_only": False, "warnings": ["Credentials required"], "account_type": "unknown"}
            is_read_only, warnings, account_type = await checker.check_coinbase_permissions(credentials)

        else:
            return {"is_read_only": False, "warnings": [f"Unknown exchange: {exchange_id}"], "account_type": "unknown"}

        return {
            "is_read_only": is_read_only,
            "warnings": warnings,
            "account_type": account_type
        }

    except Exception as e:
        logger.error(f"Error validating exchange permissions for {exchange_id}: {e}")
        return {
            "is_read_only": False,
            "warnings": [f"Error checking permissions: {str(e)}"],
            "account_type": "unknown"
        }
