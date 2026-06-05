import os
import re
import sys
import subprocess
import telebot
from mutagen.mp3 import MP3

# =====================================================================
# SECURE CONFIGURATION MODULE IMPORT
# =====================================================================
try:
    import config
    TELEGRAM_BOT_TOKEN = config.TELEGRAM_BOT_TOKEN
    APPROVED_USERS = getattr(config, "APPROVED_USERS", [])
except ImportError:
    print("[!] Critical Error: config.py file is missing from your repository.", flush=True)
    sys.exit(1)

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def is_authorized(message):
    """
    Checks if the user sending the message is present in the APPROVED_USERS whitelist.
    """
    return message.from_user.id in APPROVED_USERS

def download_and_convert_m3u8(m3u8_url, output_filepath):
    """
    Optimized low-RAM disk streamer. Compiles at 128kbps quality and
    explicitly computes and writes metadata duration headers.
    """
    user_agent = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\n"
    
    command = [
        'ffmpeg', '-y', 
        '-headers', user_agent, 
        '-allowed_extensions', 'ALL',
        '-i', m3u8_url, 
        '-vn', 
        '-acodec', 'libmp3lame', 
        '-ab', '128k',
        '-write_id3v2', '1',          
        '-id3v2_version', '3',        
        '-movflags', 'faststart',
        output_filepath
    ]
    try:
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        return process.returncode == 0 and os.path.exists(output_filepath) and os.path.getsize(output_filepath) > 0
    except Exception as e:
        print(f"[!] FFmpeg Transcoding Error: {e}", flush=True)
        return False

def process_bulk_text(text, chat_id, reply_to_message_id):
    """
    Core parsing engine. Extracts all .m3u8 URLs and uses the line 
    immediately preceding each URL as the track filename.
    """
    link_matches = [m for m in re.finditer(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', text)]
    
    if not link_matches:
        return False

    status_msg = bot.send_message(
        chat_id, 
        f"⚙️ *Found {len(link_matches)} stream targets. Initializing high-quality queue...*", 
        reply_to_message_id=reply_to_message_id,
        parse_mode="Markdown"
    )
    
    last_processed_idx = 0
    total_links = len(link_matches)
    
    for count, match in enumerate(link_matches, start=1):
        m3u8_url = match.group(1)
        start_pos = match.start()
        
        preceding_text = text[last_processed_idx:start_pos].strip()
        text_lines = [line.strip() for line in preceding_text.split('\n') if line.strip()]
        
        if text_lines:
            file_title = text_lines[-1]
            file_title = re.sub(r'[\\/*?:"<>|\r\n\t]', '_', file_title)
            file_title = file_title.strip('_')
        else:
            file_title = f"Track_{count}"

        tmp_filename = f"{file_title}.mp3"
        full_output_path = os.path.join("/tmp", tmp_filename)
        
        try:
            bot.edit_message_text(
                f"📥 *Processing track [{count}/{total_links}]:*\n🎵 _{file_title.replace('_', ' ')}_\n⚡ _Downloading & writing metadata time stamps..._", 
                chat_id=chat_id, 
                message_id=status_msg.message_id, 
                parse_mode="Markdown"
            )
        except Exception:
            pass
        
        if download_and_convert_m3u8(m3u8_url, full_output_path):
            try:
                bot.edit_message_text(f"📤 *Stitching done! Calculating exact duration track values...*", chat_id=chat_id, message_id=status_msg.message_id, parse_mode="Markdown")
            except Exception:
                pass
            
            calculated_duration = 0
            try:
                audio_inspector = MP3(full_output_path)
                calculated_duration = int(audio_inspector.info.length)
            except Exception as duration_err:
                print(f"[!] Warning: Could not calculate precise length via mutagen: {duration_err}", flush=True)

            try:
                # Delete the loading status text message right before sending the final audio file
                try:
                    bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
                except Exception:
                    pass

                with open(full_output_path, 'rb') as f:
                    # 🛠️ FIXED: Caption parameter is completely removed. Sends simple audio with nothing else.
                    bot.send_audio(
                        chat_id=chat_id, 
                        audio=f, 
                        title=file_title.replace('_', ' '),
                        duration=calculated_duration,  
                        reply_to_message_id=reply_to_message_id
                    )
            except Exception as e:
                bot.send_message(chat_id, f"❌ Telegram cloud transmission error on `{file_title}`: {e}")
            finally:
                if os.path.exists(full_output_path):
                    os.remove(full_output_path)
        else:
            bot.send_message(chat_id, f"❌ Transcoding failed for: `{file_title}`. Link may be invalid or expired.")
            try:
                bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except Exception:
                pass
            
        last_processed_idx = match.end()
        
    return True

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message):
        return 
        
    welcome_text = (
        "⚡ **Secure Timestamp-Fixed Multi-Link File Converter Online!**\n\n"
        "👉 **Option 1:** Paste your text followed by the `.m3u8` link directly.\n"
        "👉 **Option 2:** Upload a plain `.txt` file containing your list of names and links!"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(content_types=['document'])
def handle_uploaded_text_files(message):
    if not is_authorized(message):
        return 
        
    if message.document.file_name.endswith('.txt'):
        try:
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            decoded_text = downloaded_file.decode("utf-8", errors="ignore")
            
            has_links = process_bulk_text(decoded_text, message.chat.id, message.message_id)
            if not has_links:
                bot.reply_to(message, "❌ File downloaded, but no valid `.m3u8` links were found inside.")
        except Exception as e:
            bot.reply_to(message, f"❌ Error reading your text document: {e}")

@bot.message_handler(func=lambda message: True)
def handle_incoming_text_messages(message):
    if not is_authorized(message):
        return 
        
    process_bulk_text(message.text.strip(), message.chat.id, message.message_id)

if __name__ == "__main__":
    print("[*] Secure 128k universal timestamp audio compiler online...", flush=True)
    bot.remove_webhook()
    bot.infinity_polling(skip_pending=True)
        
