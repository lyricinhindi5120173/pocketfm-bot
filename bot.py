import asyncio
import os
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

import pocketfm_browser


def _extract_slug_or_url(text: str) -> str:
    text = text.strip()
    m = re.search(r"https?://\S+", text)
    if m:
        return m.group(0)
    parts = [p for p in text.strip("/").split("/") if p]
    return parts[-1] if parts else text


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙 Pocket FM Browser Session Bot\n\n"
        "Commands:\n"
        "/session — Show login/session setup steps\n"
        "/episode <url_or_slug> — Capture .m3u8 from an episode page\n"
        "/check — Check whether saved browser profile exists\n\n"
        "This version does not use the broken OTP API. It reuses a real browser session."
    )


async def cmd_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Login setup:\n\n"
        "1. Run this once on the same server/PC where the bot runs:\n"
        "   python pocketfm_browser.py --login\n\n"
        "2. A Chromium window opens. Log in to Pocket FM manually.\n"
        "3. Close the browser after login.\n"
        "4. Start the Telegram bot again.\n"
        "5. Use /episode <Pocket FM episode link>.\n\n"
        "Important: Render/GitHub Actions are bad for this because manual browser login needs GUI/VNC or a persistent browser profile."
    )


async def cmd_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    profile = os.environ.get("POCKETFM_PROFILE_DIR", "pocketfm_profile")
    if os.path.isdir(profile):
        await update.message.reply_text(f"✅ Browser profile found: {profile}")
    else:
        await update.message.reply_text(
            f"❌ Browser profile not found: {profile}\nRun: python pocketfm_browser.py --login"
        )


async def cmd_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage:\n/episode https://pocketfm.com/episode/EPISODE_ID\n\nor\n/episode EPISODE_ID"
        )
        return

    episode = _extract_slug_or_url(" ".join(context.args))
    await update.message.reply_text("⏳ Opening saved browser session and checking episode page...")

    try:
        stream, title, status = await pocketfm_browser.capture_episode_m3u8(episode)
    except Exception as e:
        await update.message.reply_text(f"❌ Browser extraction crashed:\n{type(e).__name__}: {e}")
        return

    if stream:
        safe_title = title or episode
        await update.message.reply_text(f"✅ {safe_title}\n\n{stream}")
    else:
        await update.message.reply_text(f"❌ Could not capture .m3u8.\n{status}")


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Unknown command. Use /start.")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is missing.")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("session", cmd_session))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("episode", cmd_episode))
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("Bot is running with browser-session extraction...")
    app.run_polling()


if __name__ == "__main__":
    main()
