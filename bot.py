import os
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
POCKETFM_ACCESS_TOKEN = os.getenv("POCKETFM_ACCESS_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot is running.\n\n"
        "Commands:\n"
        "/checkenv - check environment variables\n"
        "/testsession - test token/session"
    )


async def checkenv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = ""

    if BOT_TOKEN:
        msg += "✅ BOT_TOKEN found\n"
    else:
        msg += "❌ BOT_TOKEN missing\n"

    if POCKETFM_ACCESS_TOKEN:
        msg += "✅ POCKETFM_ACCESS_TOKEN found\n"
    else:
        msg += "❌ POCKETFM_ACCESS_TOKEN missing\n"

    await update.message.reply_text(msg)


async def testsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not POCKETFM_ACCESS_TOKEN:
            await update.message.reply_text(
                "❌ POCKETFM_ACCESS_TOKEN is missing in Render Environment."
            )
            return

        await update.message.reply_text(
            "✅ Session token found.\n"
            "Your Render environment variable is working."
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Request failed:\n{type(e).__name__}: {e}"
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing. Add it in Render Environment Variables.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("checkenv", checkenv))
    app.add_handler(CommandHandler("testsession", testsession))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
