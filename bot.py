import os
import shutil
import subprocess
import uuid
from pathlib import Path

from mutagen.mp4 import MP4
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ARTIST_NAME = "@I_pfm"

MAX_INPUT_MB = int(os.getenv("MAX_INPUT_MB", "20"))

# Extra voice range: 08:53 to 10:40
EXTRA_VOICE_RANGES = os.getenv("EXTRA_VOICE_RANGES", "08:53-10:40").strip()

# reduce = safer, silence = stronger
EXTRA_VOICE_ACTION = os.getenv("EXTRA_VOICE_ACTION", "reduce").strip().lower()

WORK_DIR = Path("work")
WORK_DIR.mkdir(exist_ok=True)


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])


def time_to_seconds(t):
    parts = t.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    raise ValueError("Bad time format")


def parse_ranges(text):
    if not text:
        return []

    ranges = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        start, end = item.split("-")
        ranges.append((time_to_seconds(start), time_to_seconds(end)))
    return ranges


def encode_only(input_path, output_path):
    run_cmd([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ])


def process_audio(input_path, output_path, ranges):
    if not ranges:
        encode_only(input_path, output_path)
        return

    filters = []
    parts = []
    current = 0
    index = 0

    for start_sec, end_sec in ranges:
        if start_sec > current:
            filters.append(
                f"[0:a]atrim={current}:{start_sec},asetpts=PTS-STARTPTS[p{index}]"
            )
            parts.append(f"[p{index}]")
            index += 1

        if EXTRA_VOICE_ACTION == "silence":
            clean_filter = "volume=0.02"
        else:
            clean_filter = "afftdn=nf=-25,highpass=f=120,lowpass=f=7500,volume=0.35"

        filters.append(
            f"[0:a]atrim={start_sec}:{end_sec},asetpts=PTS-STARTPTS,"
            f"{clean_filter}[p{index}]"
        )
        parts.append(f"[p{index}]")
        index += 1

        current = end_sec

    filters.append(
        f"[0:a]atrim={current},asetpts=PTS-STARTPTS[p{index}]"
    )
    parts.append(f"[p{index}]")

    filter_complex = ";".join(filters)
    filter_complex += ";" + "".join(parts)
    filter_complex += f"concat=n={len(parts)}:v=0:a=1[outa]"

    run_cmd([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path)
    ])


def set_artist_metadata(file_path, title):
    audio = MP4(str(file_path))
    audio["\xa9ART"] = [ARTIST_NAME]
    audio["aART"] = [ARTIST_NAME]
    audio["\xa9nam"] = [title]
    audio.save()


def get_file_from_message(message):
    if message.audio:
        return message.audio, message.audio.file_name or "audio"
    if message.voice:
        return message.voice, "voice.ogg"
    if message.document:
        return message.document, message.document.file_name or "audio_file"
    if message.video:
        return message.video, message.video.file_name or "video_audio"
    return None, None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running.\n\n"
        "Send audio file.\n"
        "Bot will:\n"
        "1. Change artist name to @I_pfm\n"
        "2. Reduce extra voice from 08:53 to 10:40\n\n"
        "Mode: reduce"
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    tg_file_obj, original_name = get_file_from_message(message)

    if not tg_file_obj:
        await message.reply_text("❌ Send audio/document/video file.")
        return

    file_size = getattr(tg_file_obj, "file_size", 0) or 0

    if file_size > MAX_INPUT_MB * 1024 * 1024:
        await message.reply_text(
            f"❌ File too large.\n"
            f"Current limit: {MAX_INPUT_MB} MB.\n\n"
            "Render normal Telegram Bot API cannot handle 60 MB properly."
        )
        return

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / Path(original_name).name
    output_path = job_dir / "processed_artist_I_pfm.m4a"

    status = await message.reply_text("⏳ Downloading...")

    try:
        telegram_file = await tg_file_obj.get_file()
        await telegram_file.download_to_drive(custom_path=str(input_path))

        ranges = parse_ranges(EXTRA_VOICE_RANGES)

        await status.edit_text("⏳ Processing audio...")
        process_audio(input_path, output_path, ranges)

        title = Path(original_name).stem[:60] or "Processed Audio"
        set_artist_metadata(output_path, title)

        await status.edit_text("⏳ Sending file...")

        with output_path.open("rb") as f:
            await message.reply_audio(
                audio=f,
                title=title,
                performer=ARTIST_NAME,
                filename="processed_artist_I_pfm.m4a"
            )

        await status.delete()

    except Exception as e:
        await status.edit_text(f"❌ Failed:\n{str(e)[-1200:]}")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in Render Environment.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))

    app.add_handler(
        MessageHandler(
            filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.VIDEO,
            handle_audio
        )
    )

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
