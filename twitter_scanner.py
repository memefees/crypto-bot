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

# Nitter RSS не требует JS и работает как обычный XML
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
    "https://nitter.privacydev.net",
    "https://nitter.kavin.rocks",
    "https://nitter.net",
]


class TwitterScanner:
    def __init__(self, bearer_token: str = ""):
        self._timeout = aiohttp.ClientTimeout(total=30)

    async def search_accounts(self, keyword: str, max_results: int = 100) -> list[dict]:
        accounts = {}

        # Метод 1: Nitter RSS поиск
        rss_results = await self._search_via_rss(keyword)
        accounts.update(rss_results)
        logger.info(f"RSS: {len(rss_results)} аккаунтов")

        # Метод 2: Nitter HTML поиск
        if len(accounts) < 10:
            html_results = await self._search_via_html(keyword)
            for u, d in html_results.items():
                if u not in accounts:
                    accounts[u] = d
                else:
                    merged = set(accounts[u]["wallets"]) | set(d["wallets"])
                    accounts[u]["wallets"] = list(merged)
            logger.info(f"HTML: {len(html_results)} аккаунтов")

        # Метод 3: DuckDuckGo (не блокирует серверы)
        if len(accounts) < 5:
            ddg_results = await self._search_duckduckgo(keyword)
            for u, d in ddg_results.items():
                if u not in accounts:
                    accounts[u] = d
            logger.info(f"DDG: {len(ddg_results)} аккаунтов")

        logger.info(f"Итого: {len(accounts)} аккаунтов с кошельками")
        return list(accounts.values())

    async def _search_via_rss(self, keyword: str) -> dict:
        """Nitter RSS — работает без JS, возвращает XML"""
        accounts = {}
        query = keyword.replace(" ", "+") + "+0x"

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            for instance in NITTER_INSTANCES:
                try:
                    url = f"{instance}/search/rss?q={query}&f=tweets"
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        xml = await resp.text()
                        if "<item>" not in xml:
                            continue

                        soup = BeautifulSoup(xml, "xml")
                        for item in soup.find_all("item"):
                            # Автор
                            creator = item.find("dc:creator")
                            if not creator:
                                creator = item.find("creator")
                            username = creator.get_text(strip=True).lstrip("@") if creator else None

                            # Текст
                            desc = item.find("description")
                            text = desc.get_text() if desc else ""

                            wallets = set(ETH_ADDRESS_RE.findall(text))
                            if wallets and username:
                                if username not in accounts:
                                    accounts[username] = {
                                        "username": username,
                                        "url": f"https://x.com/{username}",
                                        "wallets": list(wallets),
                                    }
                                else:
                                    merged = set(accounts[username]["wallets"]) | wallets
                                    accounts[username]["wallets"] = list(merged)

                        if accounts:
                            logger.info(f"RSS работает: {instance}")
                            break

                except Exception as e:
                    logger.warning(f"RSS {instance}: {e}")

        return accounts

    async def _search_via_html(self, keyword: str) -> dict:
        """Nitter HTML поиск"""
        accounts = {}
        query = keyword.replace(" ", "+") + "+0x"

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            for instance in NITTER_INSTANCES:
                try:
                    url = f"{instance}/search?q={query}&f=tweets"
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                        if "timeline-item" not in html:
                            continue

                        soup = BeautifulSoup(html, "html.parser")
                        for item in soup.select(".timeline-item"):
                            tag = item.select_one(".username")
                            if not tag:
                                continue
                            username = tag.get_text(strip=True).lstrip("@")
                            content = item.select_one(".tweet-content")
                            text = content.get_text() if content else ""
                            wallets = set(ETH_ADDRESS_RE.findall(text))
                            if wallets:
                                if username not in accounts:
                                    accounts[username] = {
                                        "username": username,
                                        "url": f"https://x.com/{username}",
                                        "wallets": list(wallets),
                                    }

                        if accounts:
                            break
                except Exception as e:
                    logger.warning(f"HTML {instance}: {e}")

        return accounts

    async def _search_duckduckgo(self, keyword: str) -> dict:
        """DuckDuckGo не блокирует серверные запросы"""
        accounts = {}
        query = f'site:x.com {keyword} 0x'
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"

        async with aiohttp.ClientSession(headers=HEADERS, timeout=self._timeout) as session:
            try:
                async with session.post(url, data={"q": query}) as resp:
                    if resp.status != 200:
                        return accounts
                    html = await resp.text()

                soup = BeautifulSoup(html, "html.parser")
                for result in soup.select(".result"):
                    link = result.select_one(".result__url")
                    snippet = result.select_one(".result__snippet")
                    if not link or not snippet:
                        continue

                    href = link.get_text()
                    m = re.search(r'x\.com/([A-Za-z0-9_]{1,50})', href)
                    if not m:
                        continue
                    username = m.group(1)
                    if username.lower() in {"search", "home", "explore", "i", "hashtag"}:
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
                logger.error(f"DuckDuckGo: {e}")

        return accounts
