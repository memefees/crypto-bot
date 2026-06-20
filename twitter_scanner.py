import re
import asyncio
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

# Regex for Ethereum addresses (0x + 40 hex chars)
ETH_ADDRESS_RE = re.compile(r'\b0x[a-fA-F0-9]{40}\b')

# Keywords that suggest crypto wallets in bio/tweets
CRYPTO_KEYWORDS = ["wallet", "eth", "ethereum", "0x", "metamask", "defi", "web3", "nft", "crypto"]


class TwitterScanner:
    BASE_URL = "https://api.twitter.com/2"

    def __init__(self, bearer_token: str):
        self.headers = {"Authorization": f"Bearer {bearer_token}"}

    async def search_accounts(self, keyword: str, max_results: int = 100) -> list[dict]:
        """
        Search recent tweets for keyword, extract users and ETH wallet addresses
        found in tweet text or user bio.
        """
        accounts = {}

        async with aiohttp.ClientSession(headers=self.headers) as session:
            # Search recent tweets
            tweets = await self._search_tweets(session, keyword, max_results)
            if not tweets:
                return []

            # Collect unique user IDs
            user_ids = list({t["author_id"] for t in tweets if "author_id" in t})

            # Fetch user profiles in batches of 100
            for i in range(0, len(user_ids), 100):
                batch = user_ids[i:i+100]
                users = await self._get_users(session, batch)
                for user in users:
                    username = user.get("username", "")
                    name = user.get("name", "")
                    bio = user.get("description", "") or ""
                    url = f"https://x.com/{username}"

                    wallets = set(ETH_ADDRESS_RE.findall(bio))

                    # Also scan this user's tweets text
                    for tweet in tweets:
                        if tweet.get("author_id") == user.get("id"):
                            wallets.update(ETH_ADDRESS_RE.findall(tweet.get("text", "")))

                    if wallets:
                        if username not in accounts:
                            accounts[username] = {
                                "username": username,
                                "url": url,
                                "wallets": list(wallets)
                            }
                        else:
                            accounts[username]["wallets"] = list(
                                set(accounts[username]["wallets"]) | wallets
                            )

            # Also check tweet texts for 0x addresses and link back to author
            for tweet in tweets:
                addrs = ETH_ADDRESS_RE.findall(tweet.get("text", ""))
                if addrs:
                    author_id = tweet.get("author_id")
                    # find username for this author
                    for u in accounts.values():
                        pass  # already handled above

        return list(accounts.values())

    async def _search_tweets(self, session: aiohttp.ClientSession,
                              keyword: str, max_results: int = 100) -> list[dict]:
        """Search recent tweets containing keyword."""
        # Filter out retweets, require English or any language
        query = f"{keyword} (0x OR wallet OR ethereum) -is:retweet lang:en"
        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": "author_id,text",
            "expansions": "author_id",
            "user.fields": "username,name,description"
        }
        url = f"{self.BASE_URL}/tweets/search/recent"

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                else:
                    text = await resp.text()
                    logger.error(f"Twitter search error {resp.status}: {text}")
                    return []
        except Exception as e:
            logger.error(f"Twitter search exception: {e}")
            return []

    async def _get_users(self, session: aiohttp.ClientSession,
                          user_ids: list[str]) -> list[dict]:
        """Fetch user profiles by IDs."""
        params = {
            "ids": ",".join(user_ids),
            "user.fields": "username,name,description,id"
        }
        url = f"{self.BASE_URL}/users"

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                else:
                    text = await resp.text()
                    logger.error(f"Twitter users error {resp.status}: {text}")
                    return []
        except Exception as e:
            logger.error(f"Twitter users exception: {e}")
            return []
