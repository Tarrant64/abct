"""
Token Approval Security Checker

Fetches ERC-20 token approvals (allowances) for EVM wallets via the Moralis
Token Approvals API and computes per-approval risk scores.

Read-only analysis — users are linked to revoke.cash to take action.
"""

import logging
import time
from datetime import datetime
from typing import Optional, List, Dict

from services.http_client import get_client

logger = logging.getLogger(__name__)

MORALIS_API_BASE = "https://deep-index.moralis.io/api/v2.2"

# Blockchain → Moralis chain parameter
CHAIN_MAP = {
    'ethereum': 'eth',
    'polygon': 'polygon',
    'bsc': 'bsc',
    'arbitrum': 'arbitrum',
    'base': 'base',
    'avalanche': 'avalanche',
    'optimism': 'optimism',
}

# Blockchain → revoke.cash chainId
CHAIN_IDS = {
    'ethereum': 1,
    'polygon': 137,
    'bsc': 56,
    'arbitrum': 42161,
    'base': 8453,
    'avalanche': 43114,
    'optimism': 10,
}

# 2^128 threshold — approvals at or above this are "unlimited"
UNLIMITED_THRESHOLD = 2 ** 128


class ApprovalChecker:
    """Fetches token approvals from Moralis and scores their risk."""

    async def fetch_approvals(self, address: str, blockchain: str, api_key: str) -> Dict:
        """
        Fetch token approvals for an address on a given chain via Moralis.

        Args:
            address: EVM wallet address (0x...)
            blockchain: Internal chain name (e.g. 'ethereum', 'polygon')
            api_key: Moralis API key

        Returns:
            Dict with 'approvals' list and 'summary' risk summary.
        """
        moralis_chain = CHAIN_MAP.get(blockchain)
        if not moralis_chain:
            return {'approvals': [], 'summary': self._empty_summary(), 'error': f'Chain {blockchain} not supported'}

        headers = {
            "Accept": "application/json",
            "X-API-Key": api_key,
        }

        try:
            client = get_client("moralis", timeout=30.0)
            response = await client.get(
                f"{MORALIS_API_BASE}/wallets/{address}/approvals",
                params={"chain": moralis_chain},
                headers=headers,
            )

            if response.status_code == 401:
                return {'approvals': [], 'summary': self._empty_summary(), 'error': 'Moralis API key invalid or unauthorized'}
            if response.status_code == 429:
                return {'approvals': [], 'summary': self._empty_summary(), 'error': 'Moralis rate limit exceeded — try again later'}
            if response.status_code != 200:
                return {'approvals': [], 'summary': self._empty_summary(), 'error': f'Moralis API returned HTTP {response.status_code}'}

            data = response.json()
            raw_approvals = data if isinstance(data, list) else data.get('result', [])
            processed = self._process_approvals(raw_approvals, blockchain)
            summary = self._compute_risk_summary(processed)

            return {
                'approvals': processed,
                'summary': summary,
                'revoke_url': self.get_revoke_cash_url(address, blockchain),
            }

        except Exception as e:
            logger.error(f"ApprovalChecker: error fetching approvals for {address[:10]}... on {blockchain}: {e}")
            return {'approvals': [], 'summary': self._empty_summary(), 'error': str(e)}

    def _process_approvals(self, raw_approvals: List[Dict], blockchain: str) -> List[Dict]:
        """Extract and score each approval from Moralis response."""
        processed = []
        now = time.time()

        for item in raw_approvals:
            token = item.get('token', {}) or {}
            spender = item.get('spender', {}) or {}

            # Parse the approved value
            value_raw = item.get('value') or item.get('allowance') or '0'
            try:
                value_int = int(value_raw)
            except (ValueError, TypeError):
                value_int = 0

            is_unlimited = value_int >= UNLIMITED_THRESHOLD

            # Token decimals for display
            decimals = int(token.get('decimals') or 18)
            if is_unlimited:
                human_value = 'Unlimited'
            elif value_int > 0:
                human_value = f"{value_int / (10 ** decimals):,.4f}"
            else:
                human_value = '0'

            # USD exposure (Moralis may include value_at_risk or usd_at_risk)
            usd_at_risk = float(item.get('value_at_risk') or item.get('usd_at_risk') or 0)

            # Approval age in days
            block_timestamp = item.get('block_timestamp') or item.get('last_updated_at') or ''
            age_days = 0
            if block_timestamp:
                try:
                    if 'T' in str(block_timestamp):
                        ts = datetime.fromisoformat(str(block_timestamp).replace('Z', '+00:00')).timestamp()
                    else:
                        ts = float(block_timestamp)
                    age_days = int((now - ts) / 86400)
                except (ValueError, TypeError):
                    age_days = 0

            # Spender entity label (known protocol vs unknown)
            entity_label = spender.get('entity') or spender.get('entity_label') or spender.get('name') or ''

            risk_score = self._score_single_approval(
                is_unlimited=is_unlimited,
                usd_at_risk=usd_at_risk,
                age_days=age_days,
                has_entity_label=bool(entity_label),
            )

            if risk_score >= 70:
                risk_level = 'high'
            elif risk_score >= 40:
                risk_level = 'medium'
            else:
                risk_level = 'low'

            processed.append({
                'token_name': token.get('name') or 'Unknown Token',
                'token_symbol': token.get('symbol') or '???',
                'token_address': token.get('address') or item.get('token_address') or '',
                'spender_address': spender.get('address') or item.get('spender') or '',
                'spender_label': entity_label or 'Unknown',
                'is_unlimited': is_unlimited,
                'human_value': human_value,
                'usd_at_risk': usd_at_risk,
                'age_days': age_days,
                'risk_score': risk_score,
                'risk_level': risk_level,
                'blockchain': blockchain,
            })

        # Sort by risk score descending (highest risk first)
        processed.sort(key=lambda a: a['risk_score'], reverse=True)
        return processed

    def _score_single_approval(
        self,
        is_unlimited: bool,
        usd_at_risk: float,
        age_days: int,
        has_entity_label: bool,
    ) -> int:
        """
        Risk score for a single approval (0-100, higher = riskier).

        Factors:
            Unlimited approval          +40
            Finite but >$1000 exposure   +20
            Age >365 days               +30
            Age >180 days               +20
            Age >90 days                +10
            Unknown spender             +15
            USD exposure >$10,000       +20
            USD exposure >$1,000        +10
            Known protocol (label)      -10
        """
        score = 0

        if is_unlimited:
            score += 40
        elif usd_at_risk > 1000:
            score += 20

        if age_days > 365:
            score += 30
        elif age_days > 180:
            score += 20
        elif age_days > 90:
            score += 10

        if not has_entity_label:
            score += 15

        if usd_at_risk > 10000:
            score += 20
        elif usd_at_risk > 1000:
            score += 10

        if has_entity_label:
            score -= 10

        return max(0, min(100, score))

    def _compute_risk_summary(self, approvals: List[Dict]) -> Dict:
        """Aggregate risk across all approvals for a wallet."""
        if not approvals:
            return self._empty_summary()

        high = sum(1 for a in approvals if a['risk_level'] == 'high')
        medium = sum(1 for a in approvals if a['risk_level'] == 'medium')
        low = sum(1 for a in approvals if a['risk_level'] == 'low')
        unlimited = sum(1 for a in approvals if a['is_unlimited'])
        total_usd = sum(a['usd_at_risk'] for a in approvals)

        if high > 0:
            recommendation = (
                f'{high} high-risk approval(s) found. '
                'Review and revoke any approvals you no longer need on revoke.cash.'
            )
        elif medium > 0:
            recommendation = (
                f'{medium} medium-risk approval(s) found. '
                'Consider revoking old or unlimited approvals.'
            )
        else:
            recommendation = 'All approvals are low-risk. Good hygiene!'

        return {
            'total': len(approvals),
            'high': high,
            'medium': medium,
            'low': low,
            'unlimited': unlimited,
            'total_usd_at_risk': round(total_usd, 2),
            'recommendation': recommendation,
        }

    def _empty_summary(self) -> Dict:
        return {
            'total': 0,
            'high': 0,
            'medium': 0,
            'low': 0,
            'unlimited': 0,
            'total_usd_at_risk': 0,
            'recommendation': 'No approvals found.',
        }

    def get_revoke_cash_url(self, address: str, blockchain: str) -> str:
        """Build a revoke.cash URL for the given address and chain."""
        chain_id = CHAIN_IDS.get(blockchain, 1)
        return f"https://revoke.cash/address/{address}?chainId={chain_id}"


# Singleton instance
approval_checker = ApprovalChecker()
