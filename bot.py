import os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
POCKETFM_ACCESS_TOKEN = os.getenv("POCKETFM_ACCESS_TOKEN")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running.\n\n"
        "Commands:\n"
        "/start - Start bot\n"
        "/help - Show help\n"
        "/checkenv - Check Render env\n"
        "/testsession - Check PocketFM token\n"
        "/episode <PocketFM episode link> - Process episode link"
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
        "/episode https://pocketfm.com/episode/your-episode-id"
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
    if POCKETFM_ACCESS_TOKEN:
        await update.message.reply_text("✅ Session token found.")
    else:
        await update.message.reply_text("❌ POCKETFM_ACCESS_TOKEN is missing.")


async def episode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Send episode link like this:\n\n"
            "/episode https://pocketfm.com/episode/your-episode-id"
        )
        return

    url = context.args[0].strip()

    if "pocketfm.com" not in url:
        await update.message.reply_text("❌ Please send a valid Pocket FM link.")
        return

    await update.message.reply_text(
        "✅ Episode command connected.\n\n"
        f"Received link:\n{url}\n\n"
        "Now your bot main command is working."
    )


def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing in Render environment.")
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
