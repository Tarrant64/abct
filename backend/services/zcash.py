import httpx
import re
from typing import Optional
import logging

import sys
sys.path.insert(0, str(__file__).rsplit('/', 2)[0])
from services.http_client import get_client

logger = logging.getLogger(__name__)

# Blockchair ZCash API base URL (free, no key required)
BLOCKCHAIR_ZEC_BASE_URL = "https://api.blockchair.com/zcash"

# Valid ZCash transparent address prefixes:
#   t1 - Transparent P2PKH addresses (35 chars total)
#   t3 - Transparent P2SH addresses (35 chars total)
# Shielded addresses (z-prefixed) cannot be queried via public APIs.
_ZEC_TRANSPARENT_REGEX = re.compile(r'^t[13][a-km-zA-HJ-NP-Z1-9]{33}$')


class ZCashService:
    """
    Service for fetching ZCash wallet data using Blockchair API.
    Only transparent (t-) addresses are supported. Shielded (z-) addresses
    cannot be queried via public block explorers.
    """

    def __init__(self):
        self.base_url = BLOCKCHAIR_ZEC_BASE_URL

    def validate_address(self, address: str) -> bool:
        """
        Validate a ZCash transparent address format.
        Only t1 (P2PKH) and t3 (P2SH) addresses are supported.
        Shielded z-addresses are explicitly rejected.
        """
        if not address or not isinstance(address, str):
            return False

        # Reject shielded addresses with a clear message
        if address.startswith('z'):
            logger.warning(f"Shielded ZCash address not supported: {address[:20]}...")
            return False

        return bool(_ZEC_TRANSPARENT_REGEX.match(address))

    async def get_address_info(self, address: str) -> Optional[dict]:
        """
        Get address information including ZEC balance.
        Uses Blockchair's free API (no authentication required).

        Only transparent (t1/t3) addresses are supported.
        Shielded (z-) addresses cannot be queried.

        Args:
            address: ZCash transparent address (t1 or t3 prefix)

        Returns:
            Dict with balance data or None on failure.
        """
        if not self.validate_address(address):
            logger.error(f"Invalid ZCash transparent address format: {address[:20]}...")
            return None

        try:
            client = get_client("blockchair_zec", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/dashboards/address/{address}"
            )

            if response.status_code == 400:
                logger.error(f"Invalid ZCash address: {address}")
                return None

            if response.status_code == 429:
                logger.warning("Blockchair ZEC rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"Blockchair ZEC error: {response.status_code} - {response.text}")
                return None

            data = response.json()

            # Blockchair response structure:
            # {data: {<address>: {address: {balance: <satoshis>, ...}, transactions: [...]}}}
            address_data = data.get('data', {}).get(address, {})
            address_info = address_data.get('address', {})

            if not address_info:
                logger.error(f"No data returned for ZCash address: {address[:20]}...")
                return None

            # Balance is in satoshis (zatoshis: 1 ZEC = 100,000,000 zatoshis)
            balance_satoshis = address_info.get('balance', 0)

            # Convert to ZEC
            balance_zec = balance_satoshis / 100_000_000

            return {
                'address': address,
                'balance_zec': f"{balance_zec:.8f}",
                'balance_satoshis': str(balance_satoshis),
                'tx_count': address_info.get('transaction_count', 0),
                'source': 'blockchair'
            }

        except httpx.TimeoutException:
            logger.error(f"Blockchair ZEC timeout for address {address[:20]}...")
            return None
        except Exception as e:
            logger.error(f"Blockchair ZEC error: {e}")
            return None

    async def get_shielded_pool_stats(self) -> Optional[dict]:
        """
        Get ZCash network-wide shielded pool statistics.
        Uses Blockchair stats endpoint (no address required).
        Returns available shielded pool data from the Blockchair stats API.
        """
        try:
            client = get_client("blockchair_zec", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/stats"
            )

            if response.status_code == 429:
                logger.warning("Blockchair ZEC stats rate limit hit")
                return None

            if response.status_code != 200:
                logger.error(f"Blockchair ZEC stats error: {response.status_code}")
                return None

            data = response.json()
            stats = data.get('data', {})

            if not stats:
                return None

            # Extract available fields from Blockchair ZCash stats
            result = {
                'blockchain': 'zcash',
                'source': 'blockchair',
            }

            # Include fields that Blockchair provides
            for field in ('circulation', 'blocks', 'transactions', 'hashrate_24h',
                          'difficulty', 'market_price_usd', 'market_cap_usd'):
                if field in stats:
                    result[field] = stats[field]

            # Blockchair ZCash stats may not include a dedicated shielded_pool field
            # Include a note about the data source
            result['note'] = (
                'ZCash shielded pool data from Blockchair. '
                'Transparent address stats only — shielded pool totals are not publicly enumerable.'
            )

            return result

        except httpx.TimeoutException:
            logger.error("Blockchair ZEC stats timeout")
            return None
        except Exception as e:
            logger.error(f"Blockchair ZEC get_shielded_pool_stats error: {e}")
            return None

    async def get_privacy_score(self, address: str) -> dict:
        """
        Analyze a ZCash transparent address for privacy usage.
        Checks transaction history for shielding events (t->z transfers).
        Returns a privacy score (0-100) and recommendations.

        Args:
            address: ZCash transparent address (t1 or t3 prefix)

        Returns:
            Dict with privacy score and analysis.
        """
        default_result = {
            'address': address,
            'privacy_score': 0,
            'has_shielded': False,
            'shield_event_count': 0,
            'transparent_balance_zec': 0.0,
            'recommendation': 'Use shielded (z-address) transactions to improve privacy.',
            'blockchain': 'zcash'
        }

        if not self.validate_address(address):
            return {**default_result, 'error': 'Invalid ZCash transparent address'}

        try:
            client = get_client("blockchair_zec", timeout=30.0)
            response = await client.get(
                f"{self.base_url}/dashboards/address/{address}",
                params={'transaction_details': 'true'}
            )

            if response.status_code == 429:
                logger.warning("Blockchair ZEC rate limit hit during privacy score check")
                return {**default_result, 'error': 'Rate limited'}

            if response.status_code != 200:
                logger.error(f"Blockchair ZEC privacy score error: {response.status_code}")
                return default_result

            data = response.json()
            address_data = data.get('data', {}).get(address, {})
            address_info = address_data.get('address', {})

            if not address_info:
                return default_result

            # Balance in zatoshis
            balance_zatoshis = address_info.get('balance', 0)
            transparent_balance_zec = balance_zatoshis / 100_000_000

            # Analyze transactions for shielding events
            # A shielding event is when funds move from a transparent address to a shielded pool
            # Heuristic: transactions where output_count is lower than expected (funds went shielded)
            transactions = address_data.get('transactions', [])
            tx_count = len(transactions)
            shield_event_count = 0

            for tx in transactions:
                # Blockchair transaction data includes output_count_shielded or similar
                # Check for any indication of shielded outputs
                if isinstance(tx, dict):
                    shielded_out = tx.get('output_count_shielded', 0)
                    if shielded_out and int(shielded_out) > 0:
                        shield_event_count += 1

            has_shielded = shield_event_count > 0

            # Privacy score logic
            if not has_shielded or tx_count == 0:
                privacy_score = 0
                recommendation = (
                    'All activity is on the transparent chain. '
                    'Use a z-address (shielded) to send ZEC for strong privacy.'
                )
            elif shield_event_count >= tx_count * 0.5:
                privacy_score = 100
                recommendation = (
                    f'Excellent privacy! {shield_event_count} shielding transactions detected. '
                    'Most of your ZEC has been shielded.'
                )
            else:
                privacy_score = 50
                recommendation = (
                    f'Some privacy usage ({shield_event_count} shielding events out of {tx_count} transactions). '
                    'Consider shielding more of your ZEC holdings.'
                )

            return {
                'address': address,
                'privacy_score': privacy_score,
                'has_shielded': has_shielded,
                'shield_event_count': shield_event_count,
                'transparent_balance_zec': transparent_balance_zec,
                'recommendation': recommendation,
                'blockchain': 'zcash'
            }

        except httpx.TimeoutException:
            logger.error(f"Blockchair ZEC timeout for privacy score on {address[:20]}...")
            return default_result
        except Exception as e:
            logger.error(f"Blockchair ZEC get_privacy_score error: {e}")
            return default_result


# Singleton instance
zcash_service = ZCashService()
