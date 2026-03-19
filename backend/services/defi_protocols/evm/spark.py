"""
Spark Protocol Adapter

Same ABI as Aave v3 (fork). Uses getUserAccountData(address) for aggregate data
plus per-asset spToken/variableDebtToken balance checks for detailed breakdown.

Enriched: Returns individual supply/borrow positions per asset with amounts.
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

# Spark LendingPool addresses
SPARK_POOL = {
    "ethereum": "0xC13e21B648A5Ee794902342038FF3aDAB66BE987",
}

# Spark reserve tokens with spToken and variableDebtToken addresses
SPARK_RESERVES = {
    "ethereum": [
        {"symbol": "WETH", "decimals": 18, "aToken": "0x59cD1C87501baa753d0B5B5Ab5D8416A45cD71DB", "debtToken": "0x2e7576042566f8D6990e07A1B61Ad1efd86Ae70d"},
        {"symbol": "wstETH", "decimals": 18, "aToken": "0x12B54025C112Aa61fAce2CDB7118740875A566E9", "debtToken": "0xd5c3E3B566f73Fa6b41FdB6C0D5E2475E66AE3b2"},
        {"symbol": "DAI", "decimals": 18, "aToken": "0x4DEDf26112B3Ec8eC46e7E31EA5e123490B05B8B", "debtToken": "0xf705d2B7e92B3F38e6ae7afaDAA2fEE110fE5914"},
        {"symbol": "sDAI", "decimals": 18, "aToken": "0x78f897F0fE2d3B5690EbAe7f19862DEacedF10a7", "debtToken": "0x0000000000000000000000000000000000000000"},
        {"symbol": "USDC", "decimals": 6, "aToken": "0x377C3bd93f2a2984E1E7bE6A5C22c525eD4A4815", "debtToken": "0x7B70D04099CB9cfb1Db7B6820bADAfB5b8dC1bAD"},
        {"symbol": "USDT", "decimals": 6, "aToken": "0xe7dF13b8e3d6740fe17CBE928C7334243d86c92f", "debtToken": "0x529b6158f0AE8297f1E7a6955AaF4656299Fd39b"},
        {"symbol": "rETH", "decimals": 18, "aToken": "0x9985dF20D7e9103ECBCeb16a84956434B6f06ae8", "debtToken": "0xBa2C8F2eA5B56690bFb8b709438F049e5Dd76B96"},
        {"symbol": "WBTC", "decimals": 8, "aToken": "0x4197ba364AE6698015AE5c1468f54087602715b2", "debtToken": "0xf6fEe3A8aC8040C3d6d81d9A4a168516Ec9B51D2"},
    ],
}

GET_USER_ACCOUNT_DATA = "0xbf92857c"
BASE_DECIMALS = 8


class SparkAdapter(BaseEVMAdapter):
    PROTOCOL_NAME = "Spark"
    SUPPORTED_CHAINS = list(SPARK_POOL.keys())
    DETECTION_METHOD = DetectionMethod.CONTRACT_CALL
    PROTOCOL_URL = "https://spark.fi"

    async def detect_positions(
        self, address: str, chain: str = None
    ) -> List[ProtocolPosition]:
        positions = []
        chains = [chain] if chain else self.SUPPORTED_CHAINS

        for c in chains:
            pool = SPARK_POOL.get(c)
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
                # Fallback to aggregate
                if total_collateral > 0:
                    collateral_usd = total_collateral / (10 ** BASE_DECIMALS)
                    positions.append(ProtocolPosition(
                        protocol=self.PROTOCOL_NAME,
                        chain=c,
                        position_type=PositionType.LENDING_SUPPLY,
                        token_symbol="SPARK-SUPPLY",
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
                        token_symbol="SPARK-DEBT",
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
        """Query spToken and variableDebtToken balances per reserve for per-asset breakdown."""
        reserves = SPARK_RESERVES.get(chain, [])
        if not reserves:
            return []

        positions = []
        tasks = []

        async def _zero():
            return 0

        for reserve in reserves:
            tasks.append(self._get_erc20_balance(chain, reserve["aToken"], address))
            # Skip debt check for reserves without debt tokens
            if reserve["debtToken"] != "0x0000000000000000000000000000000000000000":
                tasks.append(self._get_erc20_balance(chain, reserve["debtToken"], address))
            else:
                tasks.append(_zero())

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
                    token_symbol=f"sp{symbol}",
                    token_name=f"Spark {symbol} Supply",
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
                    token_symbol=f"vd{symbol}",
                    token_name=f"Spark {symbol} Borrow",
                    amount=amount,
                    contract_address=reserve["debtToken"],
                    extra={
                        "underlying_token": symbol,
                        "health_factor": health_factor,
                    },
                ))

        return positions if found_any else []


protocol_registry.register(SparkAdapter())
