import os
import re
import uuid
import asyncio
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

M3U8_REGEX = re.compile(r"(https?://\S+?\.m3u8\S*)", re.I)


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return name[:80] if name else "audio"


def parse_lines(text: str):
    results = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        match = M3U8_REGEX.search(line)
        if not match:
            continue

        url = match.group(1)
        name = line[:match.start()].strip()
        name = safe_filename(name)

        results.append((name, url))

    return results


def run_cmd(cmd):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=900,
    )


def get_duration(file_path: Path) -> str:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(file_path),
    ]

    result = run_cmd(cmd)

    try:
        seconds = int(float(result.stdout.strip()))
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"
    except:
        return "Unknown"


async def download_m3u8(name: str, url: str):
    file_id = uuid.uuid4().hex[:8]
    output = DOWNLOAD_DIR / f"{name}_{file_id}.mp3"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", url,
        "-vn",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        str(output),
    ]

    result = await asyncio.to_thread(run_cmd, cmd)

    if result.returncode != 0 or not output.exists():
        raise Exception(result.stderr[-1000:])

    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send .m3u8 links like this:\n\n"
        "Episode Name https://example.com/audio.m3u8\n\n"
        "You can also upload a .txt file with multiple lines."
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    items = parse_lines(text)

    if not items:
        await update.message.reply_text(
            "❌ No .m3u8 link found.\n\n"
            "Format:\nEpisode Name https://example.com/audio.m3u8"
        )
        return

    await process_items(update, items)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Please upload only .txt file.")
        return

    file = await doc.get_file()
    txt_path = DOWNLOAD_DIR / f"{uuid.uuid4().hex}.txt"
    await file.download_to_drive(txt_path)

    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    items = parse_lines(text)

    if not items:
        await update.message.reply_text("❌ No .m3u8 links found in txt file.")
        return

    await process_items(update, items)


async def process_items(update: Update, items):
    await update.message.reply_text(f"⏳ Found {len(items)} link(s). Processing...")

    for name, url in items:
        try:
            await update.message.reply_text(f"⬇️ Downloading: {name}")

            audio_path = await download_m3u8(name, url)
            duration = get_duration(audio_path)

            caption = f"🎧 {name}\n⏱ Length: {duration}"

            with open(audio_path, "rb") as audio:
                await update.message.reply_audio(
                    audio=audio,
                    filename=f"{name}.mp3",
                    caption=caption,
                    title=name,
                )

            audio_path.unlink(missing_ok=True)

        except Exception as e:
            await update.message.reply_text(
                f"❌ Failed: {name}\n\nReason:\n{str(e)[:500]}"
            )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in Render Environment Variables")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.TEXT, handle_document))

    print("✅ Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
