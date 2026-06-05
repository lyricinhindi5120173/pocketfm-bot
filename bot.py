import os, re, uuid, asyncio, subprocess
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

M3U8_REGEX = re.compile(r"(https?://[^\s]+\.m3u8[^\s]*)", re.I)

def safe_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return name[:80] if name else "audio"

def parse_lines(text):
    items = []
    for line in text.splitlines():
        line = line.strip()
        match = M3U8_REGEX.search(line)
        if match:
            url = match.group(1)
            name = safe_filename(line[:match.start()].strip())
            items.append((name, url))
    return items

def run_cmd(cmd, timeout=3600):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)

def get_duration_seconds(file_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        str(file_path)
    ]
    result = run_cmd(cmd, timeout=60)
    try:
        return int(float(result.stdout.strip()))
    except:
        return 0

async def download_m3u8(name, url):
    file_id = uuid.uuid4().hex[:8]
    output = DOWNLOAD_DIR / f"{name}_{file_id}.mp3"

    cmd = [
        "ffmpeg", "-y",
        "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
        "-rw_timeout", "30000000",
        "-i", url,
        "-vn",
        "-map", "0:a:0",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        "-metadata", f"title={name}",
        "-metadata", "artist=",
        str(output)
    ]

    result = await asyncio.to_thread(run_cmd, cmd, 3600)

    if result.returncode != 0 or not output.exists():
        raise Exception(result.stderr[-700:])

    return output

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send like this:\n\n"
        "Episode Name https://example.com/audio.m3u8\n\n"
        "Or upload .txt file with same format."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = parse_lines(update.message.text or "")
    if not items:
        await update.message.reply_text("❌ No .m3u8 link found.")
        return
    await process_items(update, items)

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document

    if not doc.file_name.lower().endswith(".txt"):
        await update.message.reply_text("❌ Upload only .txt file.")
        return

    file = await doc.get_file()
    txt_path = DOWNLOAD_DIR / f"{uuid.uuid4().hex}.txt"
    await file.download_to_drive(txt_path)

    text = txt_path.read_text(encoding="utf-8", errors="ignore")
    items = parse_lines(text)

    if not items:
        await update.message.reply_text("❌ No .m3u8 links found.")
        return

    await process_items(update, items)

async def process_items(update: Update, items):
    for name, url in items:
        audio_path = None
        try:
            audio_path = await download_m3u8(name, url)
            duration = get_duration_seconds(audio_path)

            with open(audio_path, "rb") as audio:
                await update.message.reply_audio(
                    audio=audio,
                    filename=f"{name}.mp3",
                    title=name,
                    performer="",
                    duration=duration,
                    read_timeout=300,
                    write_timeout=300,
                    connect_timeout=60,
                    pool_timeout=60
                )

        except subprocess.TimeoutExpired:
            await update.message.reply_text(f"❌ Failed: {name}\nReason: Download timeout")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed: {name}\nReason:\n{str(e)[:400]}")
        finally:
            if audio_path:
                audio_path.unlink(missing_ok=True)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .read_timeout(300)
        .write_timeout(300)
        .connect_timeout(60)
        .pool_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.Document.TEXT, handle_document))

    print("✅ Bot running")
    app.run_polling()

if __name__ == "__main__":
    main()
