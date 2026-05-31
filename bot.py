import os
import json
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
COOKIE_FILE = "cookies.json"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot is running.\n\n"
        "Commands:\n"
        "/testsession - check cookies.json\n"
        "/samplecookie - create sample cookies.json"
    )


async def samplecookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sample = [
        {
            "name": "example_cookie",
            "value": "example_value",
            "domain": ".example.com",
            "path": "/"
        }
    ]

    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(sample, f, indent=2)

    await update.message.reply_text("✅ Sample cookies.json created.")


async def testsession(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if not os.path.exists(COOKIE_FILE):
            await update.message.reply_text(
                "❌ cookies.json not found.\n\n"
                "Upload/create cookies.json first.\n"
                "For testing, use /samplecookie"
            )
            return

        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data is None:
            await update.message.reply_text("❌ cookies.json is empty or invalid.")
            return

        if isinstance(data, dict):
            cookies = data.get("cookies")

            if cookies is None:
                await update.message.reply_text(
                    "❌ cookies.json is a dict, but no 'cookies' key found.\n\n"
                    "Expected format:\n"
                    '{ "cookies": [ ... ] }'
                )
                return

        elif isinstance(data, list):
            cookies = data

        else:
            await update.message.reply_text(
                f"❌ Wrong cookies.json format: {type(data).__name__}"
            )
            return

        if not isinstance(cookies, list):
            await update.message.reply_text("❌ cookies must be a list.")
            return

        if len(cookies) == 0:
            await update.message.reply_text("❌ Cookie list is empty.")
            return

        await update.message.reply_text(
            f"✅ Session file OK.\n"
            f"Cookies found: {len(cookies)}"
        )

    except json.JSONDecodeError:
        await update.message.reply_text("❌ cookies.json is not valid JSON.")
    except Exception as e:
        await update.message.reply_text(
            f"❌ Request failed:\n{type(e).__name__}: {e}"
        )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in .env file")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("testsession", testsession))
    app.add_handler(CommandHandler("samplecookie", samplecookie))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
