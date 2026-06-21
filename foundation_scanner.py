import asyncio
import logging
import aiohttp

logger = logging.getLogger(__name__)

# Foundation GraphQL API — публичный, без авторизации
FOUNDATION_GQL = "https://api.foundation.app/graphql"

GQL_QUERY = """
query GetUsers($limit: Int!, $offset: Int!) {
  users(limit: $limit, offset: $offset, orderBy: {field: FOLLOWER_COUNT, direction: DESC}) {
    id
    publicKey
    username
    name
    twitterUsername
    instagramUsername
    websiteUrl
    links {
      twitter { handle }
      instagram { handle }
      website { handle }
    }
  }
}
"""

# Fallback: Foundation REST-подобный endpoint через their public API
FOUNDATION_API = "https://api.foundation.app/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


class FoundationScanner:
    def __init__(self):
        self._timeout = aiohttp.ClientTimeout(total=30)

    async def get_users(self, limit: int = 50) -> list[dict]:
        users = []

        # Метод 1: GraphQL
        gql_users = await self._fetch_graphql(limit)
        if gql_users:
            users = gql_users
            logger.info(f"GraphQL: получено {len(users)} пользователей")
        else:
            # Метод 2: Публичный API через известные эндпоинты
            api_users = await self._fetch_public_api(limit)
            users = api_users
            logger.info(f"Public API: получено {len(users)} пользователей")

        return users

    async def _fetch_graphql(self, limit: int) -> list[dict]:
        results = []
        batch = min(limit, 50)
        offset = 0

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            while len(results) < limit:
                payload = {
                    "query": GQL_QUERY,
                    "variables": {"limit": batch, "offset": offset}
                }
                try:
                    async with session.post(FOUNDATION_GQL, json=payload) as resp:
                        if resp.status != 200:
                            logger.warning(f"GraphQL статус: {resp.status}")
                            break
                        data = await resp.json()
                        users_raw = data.get("data", {}).get("users", [])
                        if not users_raw:
                            break

                        for u in users_raw:
                            wallet = u.get("publicKey", "")
                            if not wallet or not wallet.startswith("0x"):
                                continue

                            twitter = u.get("twitterUsername") or ""
                            instagram = u.get("instagramUsername") or ""
                            website = u.get("websiteUrl") or ""

                            # Попробуем и из links
                            links = u.get("links") or {}
                            if not twitter and links.get("twitter"):
                                twitter = links["twitter"].get("handle", "")
                            if not instagram and links.get("instagram"):
                                instagram = links["instagram"].get("handle", "")
                            if not website and links.get("website"):
                                website = links["website"].get("handle", "")

                            username = u.get("username") or u.get("publicKey", "")[:8]
                            results.append({
                                "username": username,
                                "wallet": wallet,
                                "foundation_url": f"https://foundation.app/@{username}",
                                "socials": {
                                    "twitter": twitter,
                                    "instagram": instagram,
                                    "website": website,
                                }
                            })

                        offset += batch
                        if len(users_raw) < batch:
                            break
                        await asyncio.sleep(0.5)

                except Exception as e:
                    logger.warning(f"GraphQL ошибка: {e}")
                    break

        return results[:limit]

    async def _fetch_public_api(self, limit: int) -> list[dict]:
        """Fallback через Foundation public endpoints"""
        results = []

        # Пробуем получить список через trending/creators
        endpoints = [
            f"{FOUNDATION_API}/creators?limit={min(limit,48)}&page=1",
            f"https://api.foundation.app/v2/creators?limit={min(limit,48)}",
        ]

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            for url in endpoints:
                try:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                        # Пробуем разные форматы ответа
                        items = []
                        if isinstance(data, list):
                            items = data
                        elif isinstance(data, dict):
                            items = data.get("creators") or data.get("users") or data.get("data") or []

                        for u in items:
                            wallet = u.get("publicKey") or u.get("address") or u.get("wallet", "")
                            if not wallet or not wallet.startswith("0x"):
                                continue

                            twitter = u.get("twitterUsername") or u.get("twitter") or ""
                            instagram = u.get("instagramUsername") or u.get("instagram") or ""
                            website = u.get("websiteUrl") or u.get("website") or ""
                            username = u.get("username") or wallet[:8]

                            results.append({
                                "username": username,
                                "wallet": wallet,
                                "foundation_url": f"https://foundation.app/@{username}",
                                "socials": {
                                    "twitter": twitter,
                                    "instagram": instagram,
                                    "website": website,
                                }
                            })

                        if results:
                            break

                except Exception as e:
                    logger.warning(f"API {url}: {e}")

        return results[:limit]
