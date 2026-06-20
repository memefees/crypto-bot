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
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

db = Database()
scanner = TwitterScanner()
checker = WalletChecker(ETHERSCAN_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Crypto Twitter Scanner Bot\n\n"
        "/scan crypto — сканировать\n"
        "/list — показать аккаунты\n"
        "/stats — статистика"
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
                if db.add_account(account["username"], account["url"], wallet, balance):
                    new_count += 1

        await msg.edit_text(
            f"Готово!\nПроверено: {len(results)}\nНовых: {new_count}\n\n/list — просмотр"
        )
    except Exception as e:
        logger.error(f"Scan error: {e}")
        await msg.edit_text(f"Ошибка: {e}")


async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_accounts(limit=50)
    if not accounts:
        await update.message.reply_text("База пуста. /scan crypto")
        return

    lines = ["Аккаунты с кошельками:\n"]
    for i, acc in enumerate(accounts, 1):
        bal = f"{acc['balance_eth']:.4f} ETH" if acc['balance_eth'] is not None else "N/A"
        w = f"{acc['wallet_address'][:6]}...{acc['wallet_address'][-4:]}"
        lines.append(f"{i}. {acc['twitter_url']} | {w} | {bal}")

    text = "\n".join(lines)
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        await update.message.reply_text(chunk, disable_web_page_preview=True)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(
        f"Статистика:\nАккаунтов: {s['unique_accounts']}\n"
        f"Кошельков: {s['unique_wallets']}\n"
        f"Баланс: {s['total_balance']:.4f} ETH"
    )


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("list", list_accounts))
    app.add_handler(CommandHandler("stats", stats))
    logger.info("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
