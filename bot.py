import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from database import Database
from twitter_scanner import TwitterScanner
from wallet_checker import WalletChecker

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

db = Database()
scanner = TwitterScanner(TWITTER_BEARER_TOKEN)
checker = WalletChecker(ETHERSCAN_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Crypto Twitter Scanner Bot\n\n"
        "Команды:\n"
        "/scan crypto — сканировать по ключевому слову\n"
        "/list — показать 50 аккаунтов\n"
        "/stats — статистика базы\n"
        "/help — помощь"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как использовать:\n\n"
        "1. /scan crypto — ищет твиты и ETH-адреса\n"
        "2. /list — выводит найденные аккаунты\n"
        "3. /stats — сколько аккаунтов найдено"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Укажите ключевое слово: /scan crypto")
        return

    keyword = " ".join(context.args)
    msg = await update.message.reply_text(f"Сканирую: {keyword}...")

    try:
        results = await scanner.search_accounts(keyword)
        new_count = 0

        for account in results:
            for wallet in account.get("wallets", []):
                balance = await checker.get_eth_balance(wallet)
                added = db.add_account(
                    twitter_username=account["username"],
                    twitter_url=account["url"],
                    wallet_address=wallet,
                    balance_eth=balance
                )
                if added:
                    new_count += 1

        await msg.edit_text(
            f"Готово!\n\n"
            f"Проверено аккаунтов: {len(results)}\n"
            f"Новых записей: {new_count}\n\n"
            f"Используйте /list для просмотра."
        )
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await msg.edit_text(f"Ошибка: {str(e)}")


async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_accounts(limit=50)

    if not accounts:
        await update.message.reply_text("База пуста. Используйте /scan crypto")
        return

    lines = ["Аккаунты с крипто-кошельками:\n"]
    for i, acc in enumerate(accounts, 1):
        balance_str = f"{acc['balance_eth']:.4f} ETH" if acc['balance_eth'] is not None else "N/A"
        short = f"{acc['wallet_address'][:6]}...{acc['wallet_address'][-4:]}"
        lines.append(f"{i}. {acc['twitter_url']} | {short} | {balance_str}")

    full_text = "\n".join(lines)
    for chunk in [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]:
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(
        f"Статистика:\n\n"
        f"Аккаунтов: {s['unique_accounts']}\n"
        f"Кошельков: {s['unique_wallets']}\n"
        f"Всего записей: {s['total_records']}\n"
        f"Суммарный баланс: {s['total_balance']:.4f} ETH"
    )


async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("list", list_accounts))
    app.add_handler(CommandHandler("stats", stats))

    logger.info("Bot started...")
    await app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    asyncio.run(main())
