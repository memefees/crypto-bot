import re
import logging
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

ETH_ADDRESS_RE = re.compile(r'\b0x[a-fA-F0-9]{40}\b')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class TwitterScanner:
    def __init__(self, bearer_token: str = ""):
        self._timeout = aiohttp.ClientTimeout(total=30)

    async def search_accounts(self, keyword: str, max_results: int = 100) -> list:
        accounts = {}

        # Метод 1: DuckDuckGo HTML (работает без JS)
        ddg = await self._search_duckduckgo(keyword)
        accounts.update(ddg)
        logger.info(f"DuckDuckGo: {len(ddg)} аккаунтов")

        # Метод 2: Bing поиск
        if len(accounts) < 5:
            bing = await self._search_bing(keyword)
            for u, d in bing.items():
                if u not in accounts:
                    accounts[u] = d
            logger.info(f"Bing: {len(bing)} аккаунтов")

        # Метод 3: поиск через Wayback Machine / общедоступные индексы
        if len(accounts) < 5:
            cc = await self._search_commoncrawl(keyword)
            for u, d in cc.items():
                if u not in accounts:
                    accounts[u] = d
            logger.info(f"CommonCrawl: {len(cc)} аккаунтов")

        logger.info(f"Итого: {len(accounts)} аккаунтов с кошельками")
        return list(accounts.values())

    async def _search_duckduckgo(self, keyword: str) -> dict:
        accounts = {}
        query = f'site:x.com {keyword} "0x"'

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            try:
                # DuckDuckGo HTML версия
                url = "https://html.duckduckgo.com/html/"
                async with session.post(url, data={"q": query}) as resp:
                    if resp.status != 200:
                        logger.warning(f"DDG статус: {resp.status}")
                        return accounts
                    html = await resp.text()

                soup = BeautifulSoup(html, "html.parser")
                skip = {"search", "home", "explore", "i", "hashtag", "intent",
                        "share", "login", "signup", "about", "settings"}

                for result in soup.select(".result"):
                    # URL результата
                    link = result.select_one(".result__url")
                    snippet = result.select_one(".result__snippet")
                    if not snippet:
                        continue

                    href = link.get_text() if link else ""
                    m = re.search(r'x\.com/([A-Za-z0-9_]{1,50})', href)
                    if not m:
                        # Ищем в тексте сниппета
                        m = re.search(r'x\.com/([A-Za-z0-9_]{1,50})', snippet.get_text())
                    if not m:
                        continue

                    username = m.group(1)
                    if username.lower() in skip:
                        continue

                    text = snippet.get_text()
                    wallets = set(ETH_ADDRESS_RE.findall(text))
                    if wallets and username not in accounts:
                        accounts[username] = {
                            "username": username,
                            "url": f"https://x.com/{username}",
                            "wallets": list(wallets),
                        }

            except Exception as e:
                logger.error(f"DuckDuckGo ошибка: {e}")

        return accounts

    async def _search_bing(self, keyword: str) -> dict:
        accounts = {}
        query = f'site:x.com {keyword} 0x'
        url = f"https://www.bing.com/search?q={query.replace(' ', '+')}&count=50"

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        logger.warning(f"Bing статус: {resp.status}")
                        return accounts
                    html = await resp.text()

                soup = BeautifulSoup(html, "html.parser")
                skip = {"search", "home", "explore", "i", "hashtag", "intent",
                        "share", "login", "signup", "about", "settings"}

                for result in soup.select(".b_algo"):
                    a = result.select_one("a[href]")
                    snippet = result.select_one(".b_caption p")
                    if not a or not snippet:
                        continue

                    href = a.get("href", "")
                    m = re.search(r'x\.com/([A-Za-z0-9_]{1,50})', href)
                    if not m:
                        continue

                    username = m.group(1)
                    if username.lower() in skip:
                        continue

                    text = snippet.get_text()
                    wallets = set(ETH_ADDRESS_RE.findall(text))
                    if wallets and username not in accounts:
                        accounts[username] = {
                            "username": username,
                            "url": f"https://x.com/{username}",
                            "wallets": list(wallets),
                        }

            except Exception as e:
                logger.error(f"Bing ошибка: {e}")

        return accounts

    async def _search_commoncrawl(self, keyword: str) -> dict:
        """Поиск через CommonCrawl CDX API — индекс реальных страниц x.com"""
        accounts = {}
        url = "https://index.commoncrawl.org/CC-MAIN-2024-51-index"
        params = {
            "url": "x.com/*",
            "matchType": "prefix",
            "output": "json",
            "filter": f"=mime:text/html",
            "limit": "100",
            "fl": "url,filename,offset,length",
        }

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return accounts
                    text = await resp.text()

                import json
                for line in text.strip().split("\n")[:20]:
                    try:
                        record = json.loads(line)
                        page_url = record.get("url", "")
                        m = re.search(r'x\.com/([A-Za-z0-9_]{1,50})', page_url)
                        if m:
                            username = m.group(1)
                            if username not in accounts:
                                accounts[username] = {
                                    "username": username,
                                    "url": f"https://x.com/{username}",
                                    "wallets": [],
                                }
                    except Exception:
                        continue

            except Exception as e:
                logger.error(f"CommonCrawl ошибка: {e}")

        return accounts
