import os
import shutil
import subprocess
import uuid
from pathlib import Path

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, TPE1, TIT2, ID3NoHeaderError
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
ARTIST_NAME = "@I_pfm"

WORK_DIR = Path("work")
WORK_DIR.mkdir(exist_ok=True)

MAX_INPUT_MB = int(os.getenv("MAX_INPUT_MB", "60"))


def run_cmd(cmd, timeout=900):
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-1500:])


def set_mp3_artist(mp3_path: Path, title: str):
    try:
        audio = EasyID3(str(mp3_path))
    except ID3NoHeaderError:
        audio = ID3()
        audio.save(str(mp3_path))
        audio = EasyID3(str(mp3_path))

    audio["artist"] = ARTIST_NAME
    audio["albumartist"] = ARTIST_NAME
    audio["title"] = title
    audio.save()

    tags = ID3(str(mp3_path))
    tags.delall("TPE1")
    tags.delall("TIT2")
    tags.add(TPE1(encoding=3, text=ARTIST_NAME))
    tags.add(TIT2(encoding=3, text=title))
    tags.save(str(mp3_path))


def process_audio(input_path: Path, output_path: Path):
    title = input_path.stem[:60] or "Audio"

    run_cmd([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
        "-af", "loudnorm,afftdn=nf=-25",
        "-codec:a", "libmp3lame",
        "-b:a", "128k",
        "-map_metadata", "-1",
        str(output_path)
    ])

    set_mp3_artist(output_path, title)
    return title


def get_file_from_message(message):
    if message.audio:
        return message.audio, message.audio.file_name or "audio.mp3"
    if message.document:
        return message.document, message.document.file_name or "audio_file"
    if message.voice:
        return message.voice, "voice.ogg"
    if message.video:
        return message.video, message.video.file_name or "video.mp4"
    return None, None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running.\n\nSend audio file.\nBot will return MP3 with Artist @I_pfm."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    tg_file, filename = get_file_from_message(message)

    if not tg_file:
        await message.reply_text("❌ Send audio file only.")
        return

    if tg_file.file_size and tg_file.file_size > MAX_INPUT_MB * 1024 * 1024:
        await message.reply_text(
            f"❌ File too large.\nCurrent limit: {MAX_INPUT_MB} MB."
        )
        return

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / filename
    output_path = job_dir / f"{Path(filename).stem}_I_pfm.mp3"

    status = await message.reply_text("⏳ Processing audio...")

    try:
        file = await tg_file.get_file()
        await file.download_to_drive(custom_path=str(input_path))

        title = process_audio(input_path, output_path)

        await status.edit_text("⏳ Uploading...")

        with open(output_path, "rb") as f:
            await message.reply_audio(
                audio=f,
                title=title,
                performer=ARTIST_NAME,
                filename=output_path.name,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=300,
                pool_timeout=300
            )

        await status.delete()

    except subprocess.TimeoutExpired:
        await status.edit_text("❌ Failed: Processing timed out.")
    except Exception as e:
        await status.edit_text(f"❌ Failed:\n{str(e)[-1000:]}")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .read_timeout(300)
        .write_timeout(300)
        .connect_timeout(300)
        .pool_timeout(300)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))

    app.add_handler(MessageHandler(
        filters.AUDIO | filters.Document.ALL | filters.VOICE | filters.VIDEO,
        handle_audio
    ))

    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
