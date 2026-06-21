import os
import logging
import asyncio
import telebot
from database import Database
from foundation_scanner import FoundationScanner
from wallet_checker import WalletChecker

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

bot = telebot.TeleBot(TOKEN)
db = Database()
scanner = FoundationScanner()
checker = WalletChecker(ETHERSCAN_API_KEY)


@bot.message_handler(commands=["start", "help"])
def start(message):
    bot.reply_to(message,
        "🎨 Foundation NFT Scanner\n\n"
        "/scan — сканировать новых пользователей Foundation\n"
        "/scan 50 — указать количество (макс 200)\n"
        "/list — показать базу (50 записей)\n"
        "/stats — статистика\n"
        "/top — топ по балансу кошелька"
    )


@bot.message_handler(commands=["scan"])
def scan(message):
    parts = message.text.split()
    limit = 50
    if len(parts) > 1:
        try:
            limit = min(int(parts[1]), 200)
        except ValueError:
            pass

    msg = bot.reply_to(message, f"⏳ Сканирую {limit} пользователей Foundation...")

    try:
        results = asyncio.run(do_scan(limit))
        bot.edit_message_text(
            f"✅ Готово!\n\n"
            f"👤 Проверено: {results['checked']}\n"
            f"💼 С кошельками: {results['with_wallet']}\n"
            f"🔗 С соцсетями: {results['with_social']}\n"
            f"💾 Новых в базе: {results['new_records']}\n\n"
            f"/list — просмотр базы",
            message.chat.id, msg.message_id
        )
    except Exception as e:
        logger.error(f"Scan error: {e}")
        bot.edit_message_text(f"❌ Ошибка: {e}", message.chat.id, msg.message_id)


async def do_scan(limit):
    users = await scanner.get_users(limit)
    checked = 0
    with_wallet = 0
    with_social = 0
    new_records = 0

    for user in users:
        checked += 1
        wallet = user.get("wallet")
        if not wallet:
            continue
        with_wallet += 1

        socials = user.get("socials", {})
        if not any(socials.values()):
            continue
        with_social += 1

        balance = await checker.get_eth_balance(wallet)
        added = db.add_account(
            username=user.get("username", ""),
            foundation_url=user.get("foundation_url", ""),
            wallet_address=wallet,
            balance_eth=balance,
            twitter=socials.get("twitter", ""),
            instagram=socials.get("instagram", ""),
            website=socials.get("website", "")
        )
        if added:
            new_records += 1

    return {
        "checked": checked,
        "with_wallet": with_wallet,
        "with_social": with_social,
        "new_records": new_records
    }


@bot.message_handler(commands=["list"])
def list_accounts(message):
    accounts = db.get_accounts(limit=50)
    if not accounts:
        bot.reply_to(message, "База пуста. Используйте /scan")
        return

    lines = ["👤 Пользователи Foundation с соцсетями:\n"]
    for i, acc in enumerate(accounts, 1):
        bal = f"{acc['balance_eth']:.4f} ETH" if acc['balance_eth'] is not None else "N/A"
        social_parts = []
        if acc.get("twitter"):
            social_parts.append(f"TW:{acc['twitter']}")
        if acc.get("instagram"):
            social_parts.append(f"IG:{acc['instagram']}")
        if acc.get("website"):
            social_parts.append("🌐")
        socials_str = " | ".join(social_parts) if social_parts else ""
        lines.append(
            f"{i}. {acc['foundation_url']}\n"
            f"   💰 {bal} {socials_str}"
        )

    text = "\n".join(lines)
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        bot.send_message(message.chat.id, chunk, disable_web_page_preview=True)


@bot.message_handler(commands=["top"])
def top_accounts(message):
    accounts = db.get_top_by_balance(limit=20)
    if not accounts:
        bot.reply_to(message, "База пуста. Используйте /scan")
        return

    lines = ["🏆 Топ по балансу кошелька:\n"]
    for i, acc in enumerate(accounts, 1):
        bal = f"{acc['balance_eth']:.4f} ETH" if acc['balance_eth'] is not None else "N/A"
        lines.append(f"{i}. {acc['foundation_url']} — {bal}")

    bot.reply_to(message, "\n".join(lines), disable_web_page_preview=True)


@bot.message_handler(commands=["stats"])
def stats(message):
    s = db.get_stats()
    bot.reply_to(message,
        f"📊 Статистика:\n\n"
        f"👤 Пользователей: {s['unique_accounts']}\n"
        f"💼 Кошельков: {s['unique_wallets']}\n"
        f"💰 Суммарный баланс: {s['total_balance']:.4f} ETH\n"
        f"🐦 С Twitter: {s['with_twitter']}\n"
        f"📸 С Instagram: {s['with_instagram']}"
    )


if __name__ == "__main__":
    logger.info("Bot started...")
    bot.infinity_polling()
