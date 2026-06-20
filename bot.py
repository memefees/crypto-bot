import asyncio
import logging
import re
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "YOUR_TWITTER_BEARER_TOKEN")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "YOUR_ETHERSCAN_API_KEY")

db = Database()
scanner = TwitterScanner(TWITTER_BEARER_TOKEN)
checker = WalletChecker(ETHERSCAN_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Crypto Twitter Scanner Bot*\n\n"
        "Команды:\n"
        "/scan `<keyword>` — сканировать твиты по ключевому слову\n"
        "/list — показать 50 найденных аккаунтов с кошельками\n"
        "/stats — статистика базы\n"
        "/help — помощь",
        parse_mode="Markdown"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Как использовать:*\n\n"
        "1. `/scan crypto` — ищет твиты со словом 'crypto' и извлекает ETH-адреса\n"
        "2. `/scan bitcoin wallet` — можно использовать несколько слов\n"
        "3. `/list` — выводит последние 50 уникальных аккаунтов из базы\n"
        "4. `/stats` — сколько аккаунтов и кошельков найдено\n\n"
        "Бот ищет:\n"
        "• ETH-адреса (0x...)\n"
        "• Упоминания кошельков в bio и твитах",
        parse_mode="Markdown"
    )


async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажите ключевое слово: `/scan crypto`", parse_mode="Markdown")
        return

    keyword = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Сканирую твиты по запросу: `{keyword}`...", parse_mode="Markdown")

    try:
        results = await scanner.search_accounts(keyword)
        new_count = 0

        for account in results:
            wallets = account.get("wallets", [])
            for wallet in wallets:
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
            f"✅ Сканирование завершено!\n\n"
            f"🔎 Проверено аккаунтов: {len(results)}\n"
            f"💾 Новых записей добавлено: {new_count}\n\n"
            f"Используйте /list для просмотра базы.",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Scan error: {e}")
        await msg.edit_text(f"❌ Ошибка при сканировании: {str(e)}")


async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = db.get_accounts(limit=50)

    if not accounts:
        await update.message.reply_text(
            "📭 База пуста. Используйте `/scan <keyword>` для поиска.",
            parse_mode="Markdown"
        )
        return

    lines = ["📋 *Аккаунты с крипто-кошельками:*\n"]
    for i, acc in enumerate(accounts, 1):
        balance_str = f"{acc['balance_eth']:.4f} ETH" if acc['balance_eth'] is not None else "N/A"
        short_wallet = f"{acc['wallet_address'][:6]}...{acc['wallet_address'][-4:]}"
        lines.append(
            f"{i}. [{acc['twitter_username']}]({acc['twitter_url']}) "
            f"| `{short_wallet}` | 💰 {balance_str}"
        )

    # Telegram имеет лимит 4096 символов — разбиваем на части
    full_text = "\n".join(lines)
    chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="Markdown", disable_web_page_preview=True)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = db.get_stats()
    await update.message.reply_text(
        f"📊 *Статистика базы:*\n\n"
        f"👤 Уникальных аккаунтов: {s['unique_accounts']}\n"
        f"💼 Уникальных кошельков: {s['unique_wallets']}\n"
        f"📝 Всего записей: {s['total_records']}\n"
        f"💰 Суммарный баланс: {s['total_balance']:.4f} ETH",
        parse_mode="Markdown"
    )


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("list", list_accounts))
    app.add_handler(CommandHandler("stats", stats))

    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
