import os
import time
import re
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)
import pocketfm

# ── Conversation states ───────────────────────────────────────────
PHONE, OTP = range(2)

# ── In-memory token store  {telegram_user_id: token} ─────────────
_TOKENS = {}


def _get_token(uid):
    return _TOKENS.get(str(uid), "")


def _set_token(uid, token):
    _TOKENS[str(uid)] = token


def _extract_slug(url_or_slug):
    """
    Accept a full pocketfm.com URL or a raw slug/hash.
    Returns the terminal slug segment.
    e.g. https://pocketfm.com/episode/214040b4ee41483f85758d4fca287b38
      -> 214040b4ee41483f85758d4fca287b38
    """
    # Full URL
    m = re.search(r"pocketfm\.com/(?:episode|show)/([A-Za-z0-9_-]+)", url_or_slug)
    if m:
        return m.group(1)
    # Raw slug — return last path segment
    parts = [p for p in url_or_slug.strip("/").split("/") if p]
    return parts[-1] if parts else url_or_slug.strip()


# ── /start ────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎙 *Pocket FM Stream Bot*\n\n"
        "Commands:\n"
        "/login   — Log in with your phone + OTP\n"
        "/episode — Get .m3u8 link for one episode\n"
        "/show    — Get .m3u8 links for all episodes of a show\n"
        "/token   — Show your current token\n"
        "/logout  — Clear your saved token\n"
        "/cancel  — Cancel current action",
        parse_mode="Markdown",
    )


# ── /login ────────────────────────────────────────────────────────

async def cmd_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if _get_token(uid):
        await update.message.reply_text(
            "✅ You are already logged in.\n"
            "Use /token to see your token or /logout to log out first."
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "📱 Enter your *10-digit Indian mobile number*\n"
        "Example: `9876543210`\n\n"
        "Type /cancel to abort.",
        parse_mode="Markdown",
    )
    return PHONE


async def recv_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip().lstrip("+").replace(" ", "").replace("-", "")
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text(
            "❌ Invalid number. Enter exactly 10 digits (no +91).\nTry again or /cancel."
        )
        return PHONE

    await update.message.reply_text("⏳ Sending OTP to " + phone + "...")
    ok, msg = pocketfm.send_otp(phone)

    if not ok:
        await update.message.reply_text("❌ " + msg + "\nUse /login to try again.")
        return ConversationHandler.END

    context.user_data["phone"] = phone
    await update.message.reply_text(
        "✅ OTP sent!\n"
        "Enter the 4 or 6-digit OTP received on your phone:"
    )
    return OTP


async def recv_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp   = update.message.text.strip()
    phone = context.user_data.get("phone", "")

    if not otp.isdigit() or len(otp) not in (4, 6):
        await update.message.reply_text(
            "❌ OTP must be 4 or 6 digits. Try again or /cancel."
        )
        return OTP

    await update.message.reply_text("⏳ Verifying OTP...")
    ok, token, message = pocketfm.verify_otp(phone, otp)

    if not ok:
        await update.message.reply_text("❌ " + message + "\nUse /login to try again.")
        return ConversationHandler.END

    _set_token(update.effective_user.id, token)
    await update.message.reply_text(
        "🎉 *Login successful!*\n\n"
        "You can now use /episode and /show to get stream links.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ── /token ────────────────────────────────────────────────────────

async def cmd_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _get_token(update.effective_user.id)
    if not token:
        await update.message.reply_text("❌ Not logged in. Use /login first.")
        return
    await update.message.reply_text(
        "🔑 *Your Pocket FM token:*\n\n"
        "`" + token + "`",
        parse_mode="Markdown",
    )


# ── /logout ───────────────────────────────────────────────────────

async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in _TOKENS:
        del _TOKENS[uid]
    await update.message.reply_text("👋 Logged out. Use /login to log in again.")


# ── /episode ──────────────────────────────────────────────────────

async def cmd_episode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _get_token(update.effective_user.id)
    if not token:
        await update.message.reply_text("❌ Please /login first.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/episode <url_or_slug>`\n\n"
            "Example:\n"
            "`/episode https://pocketfm.com/episode/214040b4ee41483f85758d4fca287b38`\n"
            "or\n"
            "`/episode 214040b4ee41483f85758d4fca287b38`",
            parse_mode="Markdown",
        )
        return

    slug = _extract_slug(" ".join(args))
    await update.message.reply_text("⏳ Fetching stream URL for: `" + slug + "`...",
                                    parse_mode="Markdown")

    title, stream, status = pocketfm.get_episode(slug, token)

    if stream:
        await update.message.reply_text(
            "✅ *" + (title or slug) + "*\n\n"
            "`" + stream + "`",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❌ Could not get stream URL.\n" + status)


# ── /show ─────────────────────────────────────────────────────────

async def cmd_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    token = _get_token(update.effective_user.id)
    if not token:
        await update.message.reply_text("❌ Please /login first.")
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: `/show <url_or_slug>`\n\n"
            "Example:\n"
            "`/show https://pocketfm.com/show/mahagatha-9c8b7a`\n"
            "or\n"
            "`/show mahagatha-9c8b7a`",
            parse_mode="Markdown",
        )
        return

    slug = _extract_slug(" ".join(args))
    await update.message.reply_text(
        "⏳ Fetching episode list for: `" + slug + "`...\n"
        "This may take a moment for large shows.",
        parse_mode="Markdown",
    )

    slugs, status = pocketfm.get_show_episodes(slug, token)
    if not slugs:
        await update.message.reply_text("❌ Could not get episode list.\n" + status)
        return

    await update.message.reply_text(
        "Found *" + str(len(slugs)) + "* episodes. Fetching stream URLs...",
        parse_mode="Markdown",
    )

    results  = []
    failed   = 0
    locked   = 0
    # Send progress every 10 episodes
    for i, ep_slug in enumerate(slugs, 1):
        title, stream, ep_status = pocketfm.get_episode(ep_slug, token)
        if stream:
            results.append((title or ep_slug, stream))
        elif "locked" in ep_status.lower() or "coin" in ep_status.lower():
            locked += 1
        else:
            failed += 1
        if i % 10 == 0:
            await update.message.reply_text(
                "⏳ Progress: " + str(i) + "/" + str(len(slugs)) + " episodes processed..."
            )
        time.sleep(0.25)

    if not results:
        msg = "❌ No stream URLs found."
        if locked:
            msg += "\n" + str(locked) + " episodes are coin-locked."
        await update.message.reply_text(msg)
        return

    # Split output into chunks (Telegram has 4096 char limit per message)
    lines = []
    for title, stream in results:
        lines.append("*" + title + "*")
        lines.append("`" + stream + "`")
        lines.append("")

    chunk, chunk_len = [], 0
    for line in lines:
        if chunk_len + len(line) > 3800:
            await update.message.reply_text(
                "\n".join(chunk), parse_mode="Markdown"
            )
            chunk, chunk_len = [], 0
            time.sleep(0.3)
        chunk.append(line)
        chunk_len += len(line) + 1

    if chunk:
        await update.message.reply_text(
            "\n".join(chunk), parse_mode="Markdown"
        )

    summary = "✅ Done! Got *" + str(len(results)) + "* stream URLs."
    if locked:
        summary += "\n🔒 " + str(locked) + " episode(s) are coin-locked."
    if failed:
        summary += "\n⚠️ " + str(failed) + " episode(s) failed."
    await update.message.reply_text(summary, parse_mode="Markdown")


# ── /cancel ───────────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def cmd_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Unknown command. Use /start to see all commands."
    )


# ── Main ─────────────────────────────────────────────────────────

def main():
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN environment variable not set.\n"
            "Add it as a GitHub Actions secret."
        )

    app = ApplicationBuilder().token(bot_token).build()

    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", cmd_login)],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_phone)],
            OTP:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_otp)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("token",   cmd_token))
    app.add_handler(CommandHandler("logout",  cmd_logout))
    app.add_handler(CommandHandler("episode", cmd_episode))
    app.add_handler(CommandHandler("show",    cmd_show))
    app.add_handler(login_conv)
    app.add_handler(MessageHandler(filters.COMMAND, cmd_unknown))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
