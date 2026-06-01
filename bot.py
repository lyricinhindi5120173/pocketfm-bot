import os
import re
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from pocketfm_browser import capture_episode_m3u8

BOT_TOKEN = os.getenv("BOT_TOKEN")

def extract_url(text):
    m = re.search(r"https?://\S+", text or "")
    return m.group(0) if m else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running.\n\n"
        "Commands:\n"
        "/start\n"
        "/help\n"
        "/testsession\n"
        "/episode <PocketFM episode link>"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def testsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists("pocketfm_profile"):
        await update.message.reply_text("✅ Browser profile found.")
    else:
        await update.message.reply_text(
            "❌ Browser profile not found.\n\n"
            "Run login first:\n"
            "python pocketfm_browser.py --login"
        )

async def episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url = extract_url(text)

    if not url:
        await update.message.reply_text("❌ Send like:\n/episode https://pocketfm.com/episode/xxxx")
        return

    await update.message.reply_text("⏳ Opening saved browser session...")

    try:
        m3u8, title, status = await capture_episode_m3u8(url)

        if m3u8:
            await update.message.reply_text(
                f"✅ Captured stream\n\n"
                f"Title: {title or 'Unknown'}\n\n"
                f"{m3u8}"
            )
        else:
            await update.message.reply_text(f"❌ Could not capture .m3u8.\n{status}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error:\n{e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""

    if "pocketfm.com/episode" in text:
        await episode(update, context)
    else:
        await update.message.reply_text("Send PocketFM episode link or use /episode <link>")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in Render Environment")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("testsession", testsession))
    app.add_handler(CommandHandler("episode", episode))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
