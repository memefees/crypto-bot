import asyncio
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)


class WalletChecker:
    ETHERSCAN_URL = "https://api.etherscan.io/api"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def get_eth_balance(self, address: str) -> Optional[float]:
        """Returns ETH balance for address, or None on error."""
        params = {
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest",
            "apikey": self.api_key
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.ETHERSCAN_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "1":
                            wei = int(data["result"])
                            return wei / 1e18
            return None
        except Exception as e:
            logger.error(f"Balance check error for {address}: {e}")
            return None
