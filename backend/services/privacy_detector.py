"""
Privacy Detector - Detects usage of privacy protocols on EVM chains.

Checks if a wallet address has interacted with known privacy contracts
such as Railgun on Ethereum, Polygon, BSC, and Arbitrum.

Uses Etherscan API (already configured in ABCT) to check transaction history.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Railgun privacy protocol contract addresses per chain
RAILGUN_CONTRACTS = {
    'ethereum': '0xfa7093cdd9ee6932b4eb2c9e1cde7ce00b1fa4b9',
    'polygon': '0x19b620929f97b7b990801496c3b361ca5def8c71',
    'bsc': '0x590162bf4b50f6576a459b75309ee21d92178a10',
    'arbitrum': '0x9f5c17d0e67e2e2503bfe11b82b3df38d3afdec4',
}


class PrivacyDetector:
    """
    Detects privacy protocol usage on EVM chains.

    Checks if a wallet address has interacted with known privacy contracts
    (Railgun) using Etherscan API that ABCT already has configured.
    """

    async def detect_ethereum_privacy_usage(self, address: str, etherscan_service) -> dict:
        """
        Check if an Ethereum address has interacted with Railgun or other privacy protocols.
        Uses Etherscan API to check transaction history.

        Args:
            address: Ethereum wallet address (0x...)
            etherscan_service: Configured EtherscanService instance

        Returns:
            Dict with privacy analysis results.
        """
        error_result = {
            'address': address,
            'blockchain': 'ethereum',
            'privacy_score': 0,
            'railgun_tx_count': 0,
            'protocol_interactions': [],
            'has_privacy_usage': False,
            'recommendation': 'No privacy protocol usage detected.'
        }

        try:
            configured = await etherscan_service.is_configured()
            if not configured:
                return {**error_result, 'error': 'Etherscan API not configured'}
        except Exception:
            return {**error_result, 'error': 'Could not check Etherscan configuration'}

        try:
            transactions = await etherscan_service.get_transactions('ethereum', address, limit=1000)
        except Exception as e:
            logger.warning(f"PrivacyDetector: failed to fetch transactions for {address[:10]}...: {e}")
            return {**error_result, 'error': 'Could not fetch transaction history'}

        if not transactions:
            return error_result

        railgun_contract = RAILGUN_CONTRACTS.get('ethereum', '').lower()
        railgun_tx_count = 0

        for tx in transactions:
            to_addr = (tx.get('to') or '').lower()
            from_addr = (tx.get('from') or '').lower()
            if railgun_contract and (to_addr == railgun_contract or from_addr == railgun_contract):
                railgun_tx_count += 1

        protocol_interactions = []
        if railgun_tx_count > 0:
            protocol_interactions.append('railgun')

        has_privacy_usage = len(protocol_interactions) > 0

        # Score: 0=none, 50=some use, 100=heavy use (10+ txs)
        if railgun_tx_count == 0:
            privacy_score = 0
            recommendation = 'No privacy protocol usage detected. Consider using Railgun for transaction privacy.'
        elif railgun_tx_count < 10:
            privacy_score = 50
            recommendation = f'Some Railgun usage detected ({railgun_tx_count} transactions). Good start for privacy.'
        else:
            privacy_score = 100
            recommendation = f'Heavy Railgun usage ({railgun_tx_count} transactions). Excellent transaction privacy.'

        return {
            'address': address,
            'blockchain': 'ethereum',
            'privacy_score': privacy_score,
            'railgun_tx_count': railgun_tx_count,
            'protocol_interactions': protocol_interactions,
            'has_privacy_usage': has_privacy_usage,
            'recommendation': recommendation
        }

    async def detect_evm_privacy_usage(self, address: str, blockchain: str, etherscan_service) -> dict:
        """
        Check privacy protocol usage on any supported EVM chain.

        Args:
            address: EVM wallet address (0x...)
            blockchain: Chain name ('ethereum', 'polygon', 'arbitrum', 'bsc')
            etherscan_service: Configured EtherscanService instance

        Returns:
            Dict with privacy analysis results.
        """
        error_result = {
            'address': address,
            'blockchain': blockchain,
            'privacy_score': 0,
            'railgun_tx_count': 0,
            'protocol_interactions': [],
            'has_privacy_usage': False,
            'recommendation': 'No privacy protocol usage detected.'
        }

        if blockchain not in RAILGUN_CONTRACTS:
            return error_result

        try:
            configured = await etherscan_service.is_configured()
            if not configured:
                return {**error_result, 'error': 'Etherscan API not configured'}
        except Exception:
            return {**error_result, 'error': 'Could not check Etherscan configuration'}

        # Only ethereum, polygon, arbitrum are supported by EtherscanService
        supported_chains = {'ethereum', 'polygon', 'arbitrum'}
        query_chain = blockchain if blockchain in supported_chains else 'ethereum'

        try:
            transactions = await etherscan_service.get_transactions(query_chain, address, limit=1000)
        except Exception as e:
            logger.warning(f"PrivacyDetector: failed to fetch {blockchain} transactions for {address[:10]}...: {e}")
            return {**error_result, 'error': 'Could not fetch transaction history'}

        if not transactions:
            return error_result

        railgun_contract = RAILGUN_CONTRACTS.get(blockchain, '').lower()
        railgun_tx_count = 0

        for tx in transactions:
            to_addr = (tx.get('to') or '').lower()
            from_addr = (tx.get('from') or '').lower()
            if railgun_contract and (to_addr == railgun_contract or from_addr == railgun_contract):
                railgun_tx_count += 1

        protocol_interactions = []
        if railgun_tx_count > 0:
            protocol_interactions.append('railgun')

        has_privacy_usage = len(protocol_interactions) > 0

        if railgun_tx_count == 0:
            privacy_score = 0
            recommendation = 'No privacy protocol usage detected.'
        elif railgun_tx_count < 10:
            privacy_score = 50
            recommendation = f'Some Railgun usage detected ({railgun_tx_count} transactions).'
        else:
            privacy_score = 100
            recommendation = f'Heavy Railgun usage ({railgun_tx_count} transactions). Excellent transaction privacy.'

        return {
            'address': address,
            'blockchain': blockchain,
            'privacy_score': privacy_score,
            'railgun_tx_count': railgun_tx_count,
            'protocol_interactions': protocol_interactions,
            'has_privacy_usage': has_privacy_usage,
            'recommendation': recommendation
        }


# Singleton instance
privacy_detector = PrivacyDetector()
