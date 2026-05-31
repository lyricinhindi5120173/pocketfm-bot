import os
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from pocketfm import get_episode
from pocketfm_cookie import get_session_status
from pocketfm_browser import capture_episode_m3u8

BOT_TOKEN = os.getenv("BOT_TOKEN")
POCKETFM_ACCESS_TOKEN = os.getenv("POCKETFM_ACCESS_TOKEN", "")


def extract_episode_slug(url: str) -> str:
    url = url.strip()

    match = re.search(r"/episode/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)

    parts = url.rstrip("/").split("/")
    return parts[-1]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running.\n\n"
        "Commands:\n"
        "/help\n"
        "/checkenv\n"
        "/testsession\n"
        "/episode <PocketFM episode link>"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start\n"
        "/help\n"
        "/checkenv\n"
        "/testsession\n"
        "/episode <PocketFM episode link>\n\n"
        "Example:\n"
        "/episode https://pocketfm.com/episode/aac86975e3634eb1a6482cd696345b03"
    )


async def checkenv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"BOT_TOKEN: {'✅ found' if BOT_TOKEN else '❌ missing'}\n"
        f"POCKETFM_ACCESS_TOKEN: {'✅ found' if POCKETFM_ACCESS_TOKEN else '❌ missing'}"
    )


async def testsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        ok, msg = get_session_status()
        if ok:
            await update.message.reply_text(
                "✅ PocketFM session check successful.\n\n"
                f"{msg[:500]}"
            )
        else:
            await update.message.reply_text(
                "❌ PocketFM session check failed.\n\n"
                f"{msg[:500]}"
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Session test error:\n{type(e).__name__}: {e}"
        )


async def episode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Send link like this:\n\n"
            "/episode https://pocketfm.com/episode/episode-id"
        )
        return

    url = context.args[0].strip()

    if "pocketfm.com" not in url:
        await update.message.reply_text("❌ Invalid PocketFM link.")
        return

    episode_slug = extract_episode_slug(url)

    await update.message.reply_text(
        "⏳ Extracting .m3u8...\n\n"
        f"Episode ID:\n{episode_slug}"
    )

    # Method 1: token/page/API extractor from pocketfm.py
    try:
        title, stream, status = get_episode(episode_slug, POCKETFM_ACCESS_TOKEN)

        if stream:
            await update.message.reply_text(
                "✅ .m3u8 extracted using token/page/API method.\n\n"
                f"Title:\n{title}\n\n"
                f"Stream:\n{stream}"
            )
            return

        await update.message.reply_text(
            "⚠️ Method 1 failed.\n\n"
            f"Status:\n{status}\n\n"
            "Trying browser capture method..."
        )

    except Exception as e:
        await update.message.reply_text(
            "⚠️ Method 1 error.\n\n"
            f"{type(e).__name__}: {e}\n\n"
            "Trying browser capture method..."
        )

    # Method 2: Playwright browser capture from pocketfm_browser.py
    try:
        stream, title, status = await capture_episode_m3u8(url)

        if stream:
            await update.message.reply_text(
                "✅ .m3u8 extracted using browser capture method.\n\n"
                f"Title:\n{title}\n\n"
                f"Stream:\n{stream}"
            )
            return

        await update.message.reply_text(
            "❌ Could not extract .m3u8.\n\n"
            f"Title:\n{title}\n"
            f"Status:\n{status}"
        )

    except Exception as e:
        await update.message.reply_text(
            "❌ Browser capture failed.\n\n"
            f"{type(e).__name__}: {e}"
        )


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("checkenv", checkenv))
    app.add_handler(CommandHandler("testsession", testsession))
    app.add_handler(CommandHandler("episode", episode_command))

    print("✅ Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
