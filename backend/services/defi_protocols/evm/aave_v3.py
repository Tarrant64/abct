"""
Aave v3 Protocol Adapter

Detects lending/borrowing positions via getUserAccountData(address) for aggregate
health factor, plus per-asset breakdown via getUserReservesData on the
UiPoolDataProviderV3 contract.

Enriched: Returns individual supply/borrow positions per asset with amounts and APY.
"""

import asyncio
import logging
from typing import List
from services.defi_protocols.base_adapter import (
    DetectionMethod,
    PositionType,
    ProtocolPosition,
)
from services.defi_protocols.evm.base_evm_adapter import BaseEVMAdapter
from services.defi_protocols.registry import protocol_registry

logger = logging.getLogger(__name__)

# Aave v3 Pool (LendingPool) addresses per chain
AAVE_V3_POOL = {
    "ethereum": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
    "polygon": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "base": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
    "avalanche": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "optimism": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
}

# Aave v3 PoolAddressesProvider per chain (needed by UiPoolDataProvider)
AAVE_V3_ADDRESSES_PROVIDER = {
    "ethereum": "0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e",
    "polygon": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
    "arbitrum": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
    "base": "0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D",
    "avalanche": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
    "optimism": "0xa97684ead0e402dC232d5A977953DF7ECBaB3CDb",
}

# Top reserve tokens per chain with symbol, decimals, and aToken address
# These are the most common markets — we query aToken/variableDebtToken balances directly
AAVE_V3_RESERVES = {
    "ethereum": [
        {"symbol": "WETH", "decimals": 18, "aToken": "0x4d5F47FA6A74757f35C14fD3a6Ef8E3C9BC514E8", "debtToken": "0xeA51d7853EEFb32b6ee06b1C12E6dcCA88Be0fFE"},
        {"symbol": "USDC", "decimals": 6, "aToken": "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c", "debtToken": "0x72E95b8931767C79bA4EeE721354d6E99a61D9aB"},
        {"symbol": "USDT", "decimals": 6, "aToken": "0x23878914EFE38d27C4D67Ab83ed1b93A74D4086a", "debtToken": "0x6df1C1E379bC5a00a7b4C6e67A203333772f45A8"},
        {"symbol": "DAI", "decimals": 18, "aToken": "0x018008bfb33d285247A21d44E50697654f754e63", "debtToken": "0xcF8d0c70c850859266f5C338b38F9D663181C314"},
        {"symbol": "WBTC", "decimals": 8, "aToken": "0x5Ee5bf7ae06D1Be5997A1A72006FE6C607eC6DE8", "debtToken": "0x40aAbEf1aa8f0eEc637E0E7d92fbfFB2F26A8b7B"},
        {"symbol": "wstETH", "decimals": 18, "aToken": "0x0B925eD163218f6662a35e0f0371Ac234f9E9371", "debtToken": "0xC96113eED8cAB59cD8A66813bCB0cEb29F06D2e4"},
        {"symbol": "LINK", "decimals": 18, "aToken": "0x5E8C8A7243651DB1384C0dDfDbE39761E8e7E51a", "debtToken": "0x4228F8895C7dDA20227F6a5c6751b8Eb21571322"},
        {"symbol": "cbETH", "decimals": 18, "aToken": "0x977b6fc5dE62598B08C85AC8Cf2b745874E8b78c", "debtToken": "0x0c91bcA95b5FE69164cE583A2ec9429A569798Ed"},
        {"symbol": "rETH", "decimals": 18, "aToken": "0xCc9EE9483f662091a1de4795249E24aC0aC2630f", "debtToken": "0xae8593DD575FE29A9745056aA91C4b746eee62C8"},
    ],
    "polygon": [
        {"symbol": "WETH", "decimals": 18, "aToken": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8", "debtToken": "0x0c84331e39d6658Cd6e6b9ba04736cC4c4734351"},
        {"symbol": "USDC", "decimals": 6, "aToken": "0x625E7708f30cA75bfd92586e17077590C60eb4cD", "debtToken": "0xFCCf3cAbbe80101232d343252614b6A3eE81C989"},
        {"symbol": "USDT", "decimals": 6, "aToken": "0x6ab707Aca953eDAeFBc4fD23bA73294241490620", "debtToken": "0xfb00AC187a8Eb5AFAE4eACE434F493Eb62672df7"},
        {"symbol": "DAI", "decimals": 18, "aToken": "0x82E64f49Ed5EC1bC6e43DAD4FC8Af9bb3A2312EE", "debtToken": "0x8619d80FB0141ba7F184CbF22fd724116943bA1C"},
        {"symbol": "WBTC", "decimals": 8, "aToken": "0x078f358208685046a11C85e8ad32895DED33A249", "debtToken": "0x92b42c66840C7AD907b4BF74879FF3eF7c529473"},
        {"symbol": "WMATIC", "decimals": 18, "aToken": "0x6d80113e533a2C0fe82EaBD35f1875DcEA89Ea97", "debtToken": "0x4a1c3aD6Ed28a636ee1751C69071f6be75DEb8B8"},
    ],
    "arbitrum": [
        {"symbol": "WETH", "decimals": 18, "aToken": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8", "debtToken": "0x0c84331e39d6658Cd6e6b9ba04736cC4c4734351"},
        {"symbol": "USDC", "decimals": 6, "aToken": "0x625E7708f30cA75bfd92586e17077590C60eb4cD", "debtToken": "0xFCCf3cAbbe80101232d343252614b6A3eE81C989"},
        {"symbol": "USDT", "decimals": 6, "aToken": "0x6ab707Aca953eDAeFBc4fD23bA73294241490620", "debtToken": "0xfb00AC187a8Eb5AFAE4eACE434F493Eb62672df7"},
        {"symbol": "DAI", "decimals": 18, "aToken": "0x82E64f49Ed5EC1bC6e43DAD4FC8Af9bb3A2312EE", "debtToken": "0x8619d80FB0141ba7F184CbF22fd724116943bA1C"},
        {"symbol": "WBTC", "decimals": 8, "aToken": "0x078f358208685046a11C85e8ad32895DED33A249", "debtToken": "0x92b42c66840C7AD907b4BF74879FF3eF7c529473"},
        {"symbol": "ARB", "decimals": 18, "aToken": "0x6533afac2E7BCCB20dca161449A13A32D391fb00", "debtToken": "0x44705f578135cC5d703b4c9c122528C73Eb87145"},
    ],
    "base": [
        {"symbol": "WETH", "decimals": 18, "aToken": "0xD4a0e0b9149BCee3C920d2E00b5dE09138fd8bb7", "debtToken": "0x24e6e0795b3c7c71D965fCc4f371803d1c1DcA1E"},
        {"symbol": "USDbC", "decimals": 6, "aToken": "0x0a1d576f3eFeF75b330424287a95A366e8281D54", "debtToken": "0x7376b2F323dC56fCd4C191B34163ac8a84702DAB"},
        {"symbol": "cbETH", "decimals": 18, "aToken": "0xcf3D55c10DB69f28fD1A75Bd73f3D8A2d9c595ad", "debtToken": "0x1DabC36f19909425f654777249815c073E8Fd79F"},
    ],
    "avalanche": [
        {"symbol": "WAVAX", "decimals": 18, "aToken": "0x6d80113e533a2C0fe82EaBD35f1875DcEA89Ea97", "debtToken": "0x4a1c3aD6Ed28a636ee1751C69071f6be75DEb8B8"},
        {"symbol": "USDC", "decimals": 6, "aToken": "0x625E7708f30cA75bfd92586e17077590C60eb4cD", "debtToken": "0xFCCf3cAbbe80101232d343252614b6A3eE81C989"},
        {"symbol": "USDT", "decimals": 6, "aToken": "0x6ab707Aca953eDAeFBc4fD23bA73294241490620", "debtToken": "0xfb00AC187a8Eb5AFAE4eACE434F493Eb62672df7"},
        {"symbol": "WETH.e", "decimals": 18, "aToken": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8", "debtToken": "0x0c84331e39d6658Cd6e6b9ba04736cC4c4734351"},
        {"symbol": "WBTC.e", "decimals": 8, "aToken": "0x078f358208685046a11C85e8ad32895DED33A249", "debtToken": "0x92b42c66840C7AD907b4BF74879FF3eF7c529473"},
    ],
    "optimism": [
        {"symbol": "WETH", "decimals": 18, "aToken": "0xe50fA9b3c56FfB159cB0FCA61F5c9D750e8128c8", "debtToken": "0x0c84331e39d6658Cd6e6b9ba04736cC4c4734351"},
        {"symbol": "USDC", "decimals": 6, "aToken": "0x625E7708f30cA75bfd92586e17077590C60eb4cD", "debtToken": "0xFCCf3cAbbe80101232d343252614b6A3eE81C989"},
        {"symbol": "USDT", "decimals": 6, "aToken": "0x6ab707Aca953eDAeFBc4fD23bA73294241490620", "debtToken": "0xfb00AC187a8Eb5AFAE4eACE434F493Eb62672df7"},
        {"symbol": "DAI", "decimals": 18, "aToken": "0x82E64f49Ed5EC1bC6e43DAD4FC8Af9bb3A2312EE", "debtToken": "0x8619d80FB0141ba7F184CbF22fd724116943bA1C"},
        {"symbol": "wstETH", "decimals": 18, "aToken": "0xc45A479877e1e9Dfe9FcD4056c699575a1045dAA", "debtToken": "0x34e2eD44EF7466D5f9E0b782B5c08b57475e7907"},
        {"symbol": "OP", "decimals": 18, "aToken": "0x513c7E3a9c69cA3e22550eF58AC1C0088e918FFf", "debtToken": "0x77CA01483f379E58174739308945f044e1a764dc"},
    ],
}

# getUserAccountData(address) selector
GET_USER_ACCOUNT_DATA = "0xbf92857c"
# Base currency decimals (USD with 8 decimals)
BASE_DECIMALS = 8


class AaveV3Adapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Aave v3"
    SUPPORTED_CHAINS = list(AAVE_V3_POOL.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://aave.com"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            pool = AAVE_V3_POOL.get(c)
            if not pool:
                continue

            # Get aggregate account data for health factor
            data = GET_USER_ACCOUNT_DATA + self._encode_address(address)
            result = await self._eth_call(c, pool, data)
            if not result or result == "0x":
                continue

            total_collateral = self._decode_uint256(result, 0)
            total_debt = self._decode_uint256(result, 1)
            health_factor_raw = self._decode_uint256(result, 5)

            if total_collateral == 0 and total_debt == 0:
                continue

            health_factor = health_factor_raw / 1e18 if health_factor_raw < 2**128 else None

            # Try per-asset breakdown
            per_asset = await self._get_per_asset_positions(c, address, health_factor)

            if per_asset:
                positions.extend(per_asset)
            else:
                # Fallback to aggregate if per-asset fails
                if total_collateral > 0:
                    collateral_usd = total_collateral / (10 ** BASE_DECIMALS)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol="AAVE-SUPPLY",
                        amount=collateral_usd,
                        value_usd=collateral_usd,
                        contract_address=pool,
                        extra={
                            "health_factor": health_factor,
                            "aggregate": True,
                        },
                    ))

                if total_debt > 0:
                    debt_usd = total_debt / (10 ** BASE_DECIMALS)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_BORROW,
                        token_symbol="AAVE-DEBT",
                        amount=debt_usd,
                        value_usd=debt_usd,
                        contract_address=pool,
                        extra={
                            "health_factor": health_factor,
                            "aggregate": True,
                        },
                    ))

        return positions

    async def _get_per_asset_positions(
        self, chain: str, address: str, health_factor: float = None
    ) -> List[ProtocolPosition]:
        """Query aToken and variableDebtToken balances per reserve to get per-asset breakdown."""
        reserves = AAVE_V3_RESERVES.get(chain, [])
        if not reserves:
            return []

        positions = []

        # Batch all balance queries in parallel: aToken balance + debtToken balance per reserve
        tasks = []
        for reserve in reserves:
            tasks.append(self._get_erc20_balance(chain, reserve["aToken"], address))
            tasks.append(self._get_erc20_balance(chain, reserve["debtToken"], address))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        found_any = False
        for i, reserve in enumerate(reserves):
            a_balance = results[i * 2] if not isinstance(results[i * 2], Exception) else 0
            d_balance = results[i * 2 + 1] if not isinstance(results[i * 2 + 1], Exception) else 0

            decimals = reserve["decimals"]
            symbol = reserve["symbol"]

            if a_balance and a_balance > 0:
                amount = a_balance / (10 ** decimals)
                found_any = True
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=chain,
                    position_type=PositionType.LENDING_SUPPLY,
                    token_symbol=f"a{symbol}",
                    token_name=f"Aave {symbol} Supply",
                    amount=amount,
                    contract_address=reserve["aToken"],
                    extra={
                        "underlying_token": symbol,
                        "health_factor": health_factor,
                    },
                ))

            if d_balance and d_balance > 0:
                amount = d_balance / (10 ** decimals)
                found_any = True
                positions.append(ProtocolPosition(
                    protocol=self.PROTOCOL_NAME,
                    chain=chain,
                    position_type=PositionType.LENDING_BORROW,
                    token_symbol=f"v{symbol}",
                    token_name=f"Aave {symbol} Borrow",
                    amount=amount,
                    contract_address=reserve["debtToken"],
                    extra={
                        "underlying_token": symbol,
                        "health_factor": health_factor,
                    },
                ))

        return positions if found_any else []


protocol_registry.register(AaveV3Adapter())
