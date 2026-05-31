import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
POCKETFM_ACCESS_TOKEN = os.getenv("POCKETFM_ACCESS_TOKEN", "")


def check_pocketfm_session():
    if not POCKETFM_ACCESS_TOKEN:
        return False, "POCKETFM_ACCESS_TOKEN is missing in Render Environment."

    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://pocketfm.com/",
        "Cookie": f"auth-token={POCKETFM_ACCESS_TOKEN}; locale=IN; language=hindi",
    }

    try:
        r = requests.get(
            "https://pocketfm.com/api/auth/session",
            headers=headers,
            timeout=20,
        )

        if r.status_code != 200:
            return False, f"HTTP {r.status_code}\n{r.text[:500]}"

        data = r.json()

        user_data = data.get("user_data", {})
        name = user_data.get("full_name") or user_data.get("first_name") or "Unknown user"

        return True, f"Pocket FM session working.\nLogged in as: {name}"

    except Exception as e:
        return False, f"Request failed:\n{str(e)}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pocket FM Session Test Bot\n\n"
        "Commands:\n"
        "/testsession - Check Pocket FM token\n"
        "/help - Show help"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Add these Render environment variables:\n\n"
        "TELEGRAM_BOT_TOKEN\n"
        "POCKETFM_ACCESS_TOKEN\n\n"
        "Then use:\n"
        "/testsession"
    )


async def testsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Checking Pocket FM session...")

    ok, msg = check_pocketfm_session()

    if ok:
        await update.message.reply_text("✅ " + msg)
    else:
        await update.message.reply_text("❌ " + msg)


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN missing in Render Environment.")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("testsession", testsession))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
