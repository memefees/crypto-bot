
import re
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ETH_ADDRESS_RE = re.compile(r'\b0x[a-fA-F0-9]{40}\b')

NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.kavin.rocks",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


class TwitterScanner:
    def __init__(self, bearer_token: str = ""):
        # bearer_token больше не нужен, оставлен для совместимости с bot.py
        self._timeout = aiohttp.ClientTimeout(total=20)

    async def search_accounts(self, keyword: str, max_results: int = 100) -> list[dict]:
        accounts = {}

        nitter = await self._search_nitter(keyword)
        accounts.update(nitter)

        google = await self._search_google(keyword)
        for username, data in google.items():
            if username not in accounts:
                accounts[username] = data
            else:
                merged = set(accounts[username]["wallets"]) | set(data["wallets"])
                accounts[username]["wallets"] = list(merged)

        logger.info(f"Итого найдено аккаунтов с кошельками: {len(accounts)}")
        return list(accounts.values())

    # ------------------------------------------------------------------ #
    #  Nitter                                                              #
    # ------------------------------------------------------------------ #

    async def _search_nitter(self, keyword: str) -> dict:
        accounts = {}
        query = f"{keyword} 0x"

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            for instance in NITTER_INSTANCES:
                try:
                    search_url = f"{instance}/search?q={query}&f=tweets"
                    async with session.get(search_url) as resp:
                        if resp.status != 200:
                            logger.warning(f"Nitter {instance} вернул {resp.status}")
                            continue
                        html = await resp.text()
                        found = self._parse_nitter_html(html)
                        accounts.update(found)
                        logger.info(f"Nitter {instance}: {len(found)} аккаунтов")
                        break
                except Exception as e:
                    logger.warning(f"Nitter {instance} ошибка: {e}")

        return accounts

    def _parse_nitter_html(self, html: str) -> dict:
        accounts = {}
        soup = BeautifulSoup(html, "html.parser")

        for item in soup.select(".timeline-item"):
            tag = item.select_one(".username")
            if not tag:
                continue
            username = tag.get_text(strip=True).lstrip("@")

            content = item.select_one(".tweet-content")
            text = content.get_text() if content else ""

            wallets = set(ETH_ADDRESS_RE.findall(text))
            if not wallets:
                continue

            if username not in accounts:
                accounts[username] = {
                    "username": username,
                    "url": f"https://x.com/{username}",
                    "wallets": list(wallets),
                }
            else:
                merged = set(accounts[username]["wallets"]) | wallets
                accounts[username]["wallets"] = list(merged)

        return accounts

    # ------------------------------------------------------------------ #
    #  Google dork                                                         #
    # ------------------------------------------------------------------ #

    async def _search_google(self, keyword: str) -> dict:
        accounts = {}
        query = f'site:x.com "{keyword}" "0x"'
        url = f"https://www.google.com/search?q={query}&num=50"

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"Google вернул {resp.status}")
                        return accounts
                    html = await resp.text()
            except Exception as e:
                logger.error(f"Google запрос не удался: {e}")
                return accounts

        soup = BeautifulSoup(html, "html.parser")
        skip = {"search", "home", "explore", "i", "hashtag", "intent", "share"}

        for a in soup.select("a[href]"):
            href = a.get("href", "")
            m = re.search(r'https://(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,50})', href)
            if not m:
                continue
            username = m.group(1)
            if username.lower() in skip:
                continue

            parent = a.find_parent()
            text = parent.get_text() if parent else ""
            wallets = set(ETH_ADDRESS_RE.findall(text))
            if not wallets:
                continue

            if username not in accounts:
                accounts[username] = {
                    "username": username,
                    "url": f"https://x.com/{username}",
                    "wallets": list(wallets),
                }

        logger.info(f"Google dork: {len(accounts)} аккаунтов")
        return accounts
