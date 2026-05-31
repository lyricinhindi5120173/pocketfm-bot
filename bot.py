from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
POCKETFM_ACCESS_TOKEN = os.getenv("POCKETFM_ACCESS_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running.\n\nCommands:\n"
        "/start - Start bot\n"
        "/help - Show help\n"
        "/checkenv - Check Render env\n"
        "/testsession - Check PocketFM token"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start\n/help\n/checkenv\n/testsession"
    )

async def checkenv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = ""
    msg += "✅ BOT_TOKEN found\n" if BOT_TOKEN else "❌ BOT_TOKEN missing\n"
    msg += "✅ POCKETFM_ACCESS_TOKEN found\n" if POCKETFM_ACCESS_TOKEN else "❌ POCKETFM_ACCESS_TOKEN missing\n"
    await update.message.reply_text(msg)

async def testsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if POCKETFM_ACCESS_TOKEN:
        await update.message.reply_text(
            "✅ Session token found.\nYour Render environment variable is working."
        )
    else:
        await update.message.reply_text("❌ POCKETFM_ACCESS_TOKEN missing.")

async def set_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("help", "Show help"),
        BotCommand("checkenv", "Check environment variables"),
        BotCommand("testsession", "Check PocketFM session token"),
    ])

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN missing")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("checkenv", checkenv))
    app.add_handler(CommandHandler("testsession", testsession))

    print("✅ Bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
