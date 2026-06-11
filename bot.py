import os
import shutil
import subprocess
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from mutagen.mp4 import MP4
from sklearn.cluster import KMeans
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from speechbrain.inference.speaker import EncoderClassifier

BOT_TOKEN = os.getenv("BOT_TOKEN")
ARTIST_NAME = "@I_pfm"

MAX_INPUT_MB = int(os.getenv("MAX_INPUT_MB", "20"))

# reduce = safer, silence = stronger but risky
EXTRA_VOICE_ACTION = os.getenv("EXTRA_VOICE_ACTION", "reduce")

WORK_DIR = Path("work")
WORK_DIR.mkdir(exist_ok=True)

classifier = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/spkrec-ecapa-voxceleb"
)


def run_cmd(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])


def convert_to_wav(input_path, wav_path):
    run_cmd([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ac", "1",
        "-ar", "16000",
        str(wav_path)
    ])


def encode_m4a(input_path, output_path):
    run_cmd([
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vn",
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


def merge_ranges(ranges, gap=1.5):
    if not ranges:
        return []

    ranges = sorted(ranges)
    merged = [ranges[0]]

    for start, end in ranges[1:]:
        last_start, last_end = merged[-1]

        if start <= last_end + gap:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def detect_extra_voice_ranges(wav_path):
    audio, sr = sf.read(str(wav_path), dtype="float32")

    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    duration = len(audio) / sr

    chunk_sec = 3.0
    step_sec = 2.0

    chunk_size = int(chunk_sec * sr)
    step_size = int(step_sec * sr)

    embeddings = []
    times = []

    for start in range(0, len(audio) - chunk_size, step_size):
        chunk = audio[start:start + chunk_size]

        rms = float(np.sqrt(np.mean(chunk ** 2)))

        # Skip silence/very low audio
        if rms < 0.01:
            continue

        signal = np.expand_dims(chunk, axis=0)

        emb = classifier.encode_batch(
            np.array(signal)
        ).squeeze().detach().cpu().numpy()

        embeddings.append(emb)
        times.append((start / sr, (start + chunk_size) / sr))

    if len(embeddings) < 8:
        return [], "Not enough speech to detect extra voice."

    embeddings = np.array(embeddings)

    kmeans = KMeans(n_clusters=2, random_state=42, n_init=10)
    labels = kmeans.fit_predict(embeddings)

    count_0 = int(np.sum(labels == 0))
    count_1 = int(np.sum(labels == 1))

    main_label = 0 if count_0 >= count_1 else 1
    extra_label = 1 - main_label

    extra_ratio = min(count_0, count_1) / len(labels)

    # If second speaker is too small, ignore
    if extra_ratio < 0.08:
        return [], "No clear extra voice detected."

    # If both speakers are almost equal, risky
    if extra_ratio > 0.45:
        return [], "Different voices found, but not safe to auto-remove."

    ranges = []

    for label, (start, end) in zip(labels, times):
        if label == extra_label:
            ranges.append((max(0, start - 0.3), min(duration, end + 0.3)))

    ranges = merge_ranges(ranges)

    return ranges, f"Extra voice detected in {len(ranges)} range(s)."


def clean_ranges(input_path, output_path, ranges):
    if not ranges:
        encode_m4a(input_path, output_path)
        return

    filters = []
    concat_parts = []
    current = 0
    index = 0

    for start_sec, end_sec in ranges:
        if start_sec > current:
            filters.append(
                f"[0:a]atrim={current}:{start_sec},asetpts=PTS-STARTPTS[p{index}]"
            )
            concat_parts.append(f"[p{index}]")
            index += 1

        if EXTRA_VOICE_ACTION == "silence":
            clean_filter = "volume=0.03"
        else:
            clean_filter = "afftdn=nf=-25,highpass=f=120,lowpass=f=7500,volume=0.35"

        filters.append(
            f"[0:a]atrim={start_sec}:{end_sec},asetpts=PTS-STARTPTS,"
            f"{clean_filter}[p{index}]"
        )
        concat_parts.append(f"[p{index}]")
        index += 1

        current = end_sec

    filters.append(
        f"[0:a]atrim={current},asetpts=PTS-STARTPTS[p{index}]"
    )
    concat_parts.append(f"[p{index}]")

    filter_complex = ";".join(filters)
    filter_complex += ";" + "".join(concat_parts)
    filter_complex += f"concat=n={len(concat_parts)}:v=0:a=1[outa]"

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
        "1. Detect extra/different voice automatically\n"
        "2. Reduce/remove extra voice if detected\n"
        "3. Set artist name to @I_pfm\n\n"
        "Use /mode_reduce for safer cleaning.\n"
        "Use /mode_silence for stronger removal."
    )


async def mode_reduce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global EXTRA_VOICE_ACTION
    EXTRA_VOICE_ACTION = "reduce"
    await update.message.reply_text("✅ Mode set to reduce. Safer mode.")


async def mode_silence(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global EXTRA_VOICE_ACTION
    EXTRA_VOICE_ACTION = "silence"
    await update.message.reply_text("✅ Mode set to silence. Stronger but risky.")


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
            f"Render normal bot limit here: {MAX_INPUT_MB} MB.\n\n"
            "For 60 MB support, use VPS + self-hosted Telegram Bot API."
        )
        return

    job_id = uuid.uuid4().hex
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    input_path = job_dir / original_name
    wav_path = job_dir / "input.wav"
    cleaned_path = job_dir / "cleaned.m4a"

    status = await message.reply_text("⏳ Downloading...")

    try:
        telegram_file = await tg_file_obj.get_file()
        await telegram_file.download_to_drive(custom_path=str(input_path))

        await status.edit_text("⏳ Converting audio...")
        convert_to_wav(input_path, wav_path)

        await status.edit_text("⏳ Detecting extra voices automatically...")
        ranges, report = detect_extra_voice_ranges(wav_path)

        await status.edit_text("⏳ Processing audio...")
        clean_ranges(input_path, cleaned_path, ranges)

        title = Path(original_name).stem[:60] or "Processed Audio"
        set_artist_metadata(cleaned_path, title)

        range_text = ""
        if ranges:
            for s, e in ranges:
                range_text += f"\n- {int(s//60):02d}:{int(s%60):02d} to {int(e//60):02d}:{int(e%60):02d}"

        await status.edit_text(
            f"✅ {report}\n"
            f"{range_text}\n\n"
            "⏳ Sending file..."
        )

        with cleaned_path.open("rb") as f:
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
    app.add_handler(CommandHandler("mode_reduce", mode_reduce))
    app.add_handler(CommandHandler("mode_silence", mode_silence))

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
