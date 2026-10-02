# ---------------------------------------------------
# File Name: func.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

import math
import time , re
from pyrogram import enums
from config import CHANNEL_ID, OWNER_ID, THUMBNAIL_DIR 
from toxic.core.mongo.plans_db import premium_users
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import cv2
from pyrogram.errors import FloodWait, InviteHashInvalid, InviteHashExpired, UserAlreadyParticipant, UserNotParticipant
from datetime import datetime as dt
import asyncio, subprocess, re, os, time
from PIL import Image
async def chk_user(message, user_id):
    user = await premium_users()
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    user_strings = [str(u) for u in user]
    owner_strings = [str(o) for o in owner_list]
    if str(user_id) in owner_strings or str(user_id) in user_strings:
        return 0
    else:
        return 1

async def chk_mirror_user(user_id):
    """Checks if a user has active Topic Mirroring plan (or is Owner/Sudo). Returns 0 if authorized, 1 if not."""
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    owner_strings = [str(o) for o in owner_list]
    if str(user_id) in owner_strings:
        return 0
    from toxic.core.mongo.plans_db import mirror_premium_users
    mirror_users_list = await mirror_premium_users()
    mirror_user_strings = [str(u) for u in mirror_users_list]
    if str(user_id) in mirror_user_strings:
        return 0
    return 1
async def gen_link(app,chat_id):
   link = await app.export_chat_invite_link(chat_id)
   return link

async def subscribe(app, message):
    update_channel = CHANNEL_ID
    if not update_channel:
        return 0
    try:
        url = await gen_link(app, update_channel)
    except Exception as err:
        print(f"⚠️ Failed to gen_link for channel {update_channel}: {err}")
        return 0

    user_id = message.from_user.id if message.from_user else message.chat.id
    first_name = message.from_user.first_name if (message.from_user and message.from_user.first_name) else "User"

    try:
        user = await app.get_chat_member(update_channel, user_id)
        if str(getattr(user, "status", "")).lower() in ["kicked", "banned"]:
            await message.reply_text(
                "<blockquote><b>❌ ACCESS BANNED</b></blockquote>\n\n"
                "You are banned from using this bot.\n"
                "💬 <b>Contact Admin:</b> @CHOSEN_ONEx_bot",
                parse_mode=enums.ParseMode.HTML
            )
            return 1
        return 0
    except UserNotParticipant:
        caption = (
            "<blockquote><b>🛑 ACCESS REQUIRED — MUST JOIN CHANNEL 🛑</b></blockquote>\n\n"
            f"<b>👋 Hello {first_name}!</b>\n\n"
            "<blockquote><b>📢 To use this Bot, you must join our Official Updates Channel!</b>\n\n"
            "<i>Due to high server load & security filters, access is reserved exclusively for our channel members.</i></blockquote>\n\n"
            "<b>✨ Follow simple steps below to unlock:</b>\n"
            "1️⃣ Click <b>📢 Join Official Channel</b> button below.\n"
            "2️⃣ Click <b>Join Channel</b> in Telegram.\n"
            "3️⃣ Come back & send <code>/start</code> again or click <b>🔄 Check Access</b>!\n\n"
            "<blockquote><b>⚡ Ultra Fast & Smart Content Xtractor Pro!</b></blockquote>"
        )
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 Join Official Channel", url=f"{url}")],
            [InlineKeyboardButton("🔄 Check Access / Try Again", callback_data="check_subscription")],
            [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CHOSEN_ONEx_bot")]
        ])
        photo_url = "https://freeimage.host/i/n7cbXDX"
        try:
            await message.reply_photo(photo=photo_url, caption=caption, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
        except Exception:
            await message.reply_text(caption, reply_markup=buttons, parse_mode=enums.ParseMode.HTML)
        return 1
    except Exception as e:
        print(f"⚠️ Subscribe check exception: {e}")
        return 0
async def get_seconds(time_string):
    def extract_value_and_unit(ts):
        value = ""
        unit = ""

        index = 0
        while index < len(ts) and ts[index].isdigit():
            value += ts[index]
            index += 1

        unit = ts[index:].lstrip()

        if value:
            value = int(value)

        return value, unit

    value, unit = extract_value_and_unit(time_string)

    if unit == 's':
        return value
    elif unit == 'min':
        return value * 60
    elif unit == 'hour':
        return value * 3600
    elif unit == 'day':
        return value * 86400
    elif unit == 'month':
        return value * 86400 * 30
    elif unit == 'year':
        return value * 86400 * 365
    else:
        return 0
PROGRESS_BAR = """
   ┉━┉━┉━┉┉━┉━┉━┉┉━┉━
>*┋ **__Total Size:⚜️__** {2}
>*┋ **__Completed:✅__** {1}
>*┋ **__Progress:💠__** {0}%
>*┋ **__Speed:🚀__** {3}/s
>*┋ **__ETA:⏳__** {4}\n ╚═══━━━─⚝─━━━═══╝\n\n Now You Can Rest...😉
"""

async def progress_bar(current, total, ud_type, message, start):

    now = time.time()
    diff = now - start
    
    # Update every 5 seconds or on completion to minimize API overhead
    if not hasattr(progress_bar, "last_updates"):
        progress_bar.last_updates = {}
            
    msg_id = getattr(message, "id", id(message))
    last_update = progress_bar.last_updates.get(msg_id, 0)

    if (now - last_update) >= 5 or current == total:
        progress_bar.last_updates[msg_id] = now
        percentage = current * 100 / total if total > 0 else 0
        speed = current / diff if diff > 0 else 0
        
        # Avoid division by zero and handle tiny speeds
        if speed > 0:
            time_to_completion = round((total - current) / speed)
            estimated_total_time = TimeFormatter(milliseconds=time_to_completion * 1000)
        else:
            estimated_total_time = "Calculating..."

        progress = "{0}{1}".format(
            ''.join(["❤️" for i in range(math.floor(percentage / 10))]),
            ''.join(["🤍" for i in range(10 - math.floor(percentage / 10))]))

        tmp = progress + PROGRESS_BAR.format( 
            round(percentage, 2),
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),
            estimated_total_time
        )
        try:
            await message.edit(text=f"{ud_type} {tmp}")
        except Exception:
            pass


def humanbytes(size):
    if not size:
        return ""
    power = 2**10
    n = 0
    Dic_powerN = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + Dic_powerN[n] + 'B'

def TimeFormatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = ((str(days) + "d, ") if days else "") + \
        ((str(hours) + "h, ") if hours else "") + \
        ((str(minutes) + "m, ") if minutes else "") + \
        ((str(seconds) + "s, ") if seconds else "") + \
        ((str(milliseconds) + "ms, ") if milliseconds else "")
    return tmp[:-2] 
def convert(seconds):
    seconds = seconds % (24 * 3600)
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60      
    return "%d:%02d:%02d" % (hour, minutes, seconds)
async def userbot_join(userbot, invite_link):
    try:
        await userbot.join_chat(invite_link)
        return "Successfully joined the Channel"
    except UserAlreadyParticipant:
        return "User is already a participant."
    except (InviteHashInvalid, InviteHashExpired):
        return "Could not join. Maybe your link is expired or Invalid."
    except FloodWait:
        return "Too many requests, try again later."
    except Exception as e:
        print(e)
        return "Could not join, try joining manually."
def get_link(string):
    # Regex for standard http/https links
    regex_web = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
    # Regex for Telegram deep links (tg://)
    regex_tg = r"(tg://openmessage\?(?:user_id|chat_id)=-?\d+&message_id=\d+)"
    
    url_web = re.findall(regex_web, string)
    url_tg = re.findall(regex_tg, string)
    
    try:
        if url_tg:
            return url_tg[0]
        if url_web:
            return url_web[0][0]
        return False
    except Exception:
        return False

def video_metadata(file):
    default_values = {'width': 0, 'height': 0, 'duration': 0}
    try:
        vcap = cv2.VideoCapture(file)
        if vcap.isOpened():
            width = round(vcap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = round(vcap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = vcap.get(cv2.CAP_PROP_FPS)
            frame_count = vcap.get(cv2.CAP_PROP_FRAME_COUNT)
            vcap.release()
            
            if fps > 0 and frame_count > 0:
                duration = round(frame_count / fps)
                if width > 0 and height > 0 and duration > 0:
                    return {'width': width, 'height': height, 'duration': duration}
    except Exception as e:
        print(f"Error in OpenCV video_metadata: {e}")

    # Fallback to ffprobe
    try:
        import subprocess
        # Get stream info
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "default=noprint_wrappers=1",
            file
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        width, height, duration = None, None, None
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                k, v = line.split('=', 1)
                if k == 'width' and v.isdigit():
                    width = int(v)
                elif k == 'height' and v.isdigit():
                    height = int(v)
                elif k == 'duration':
                    try:
                        duration = round(float(v))
                    except ValueError:
                        pass
                        
        # Get format duration if stream duration is empty/invalid
        if duration is None or duration <= 0:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1",
                file
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            for line in result.stdout.strip().split('\n'):
                if '=' in line:
                    k, v = line.split('=', 1)
                    if k == 'duration':
                        try:
                            duration = round(float(v))
                        except ValueError:
                            pass

        width = width or 0
        height = height or 0
        duration = duration or 0
        return {'width': width, 'height': height, 'duration': duration}
    except Exception as e:
        print(f"Error in ffprobe fallback: {e}")
        return default_values

def hhmmss(seconds):
    return time.strftime('%H:%M:%S',time.gmtime(seconds))

def optimize_thumbnail(image_path):
    try:
        if not image_path or not os.path.exists(image_path):
            return None
        
        abs_path = os.path.abspath(image_path)
        with Image.open(abs_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            # Resize preserving aspect ratio (max 320x320 for Telegram specification)
            img.thumbnail((320, 320))
            # Save it back as optimized JPEG (always under 200KB)
            img.save(abs_path, "JPEG", optimize=True, quality=85)
            
        return abs_path
    except Exception as e:
        print(f"[ERROR] Failed to optimize thumbnail {image_path}: {e}")
        return os.path.abspath(image_path) if image_path else None

# REPLACE screenshot() function in toxic/core/func.py (Line 221-257)

def _opencv_worker(video, out):
    try:
        vcap = cv2.VideoCapture(video)
        if not vcap.isOpened():
            return False
        frame_count = vcap.get(cv2.CAP_PROP_FRAME_COUNT)
        if frame_count <= 0:
            vcap.release()
            return False
            
        attempts = 20
        seek_pcts = [i * 0.05 for i in range(1, attempts + 1)]
        fallback_frame = None
        success = False
        
        for pct in seek_pcts:
            frame_no = int(frame_count * pct)
            vcap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
            ret, frame = vcap.read()
            if ret and frame is not None:
                if fallback_frame is None:
                    fallback_frame = frame.copy()
                
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                mean_val = gray.mean()
                if mean_val >= 10.0:
                    cv2.imwrite(out, frame)
                    success = True
                    break
        
        if not success and fallback_frame is not None:
            cv2.imwrite(out, fallback_frame)
            success = True
            
        vcap.release()
        return success
    except Exception as e:
        print(f"[ERROR] OpenCV worker failed: {e}")
        return False


async def screenshot(video, duration, sender):
    try:
        # Validate inputs
        if duration <= 0:
            duration = 10  # Fallback duration to allow seek
            
        out = f"thumb_{sender}_{int(time.time())}.jpg"
        success = False
        
        # 1. Try OpenCV first (offloaded to background thread to avoid blocking loop)
        try:
            print(f"[DEBUG] Trying OpenCV screenshot for: {video}")
            success = await asyncio.to_thread(_opencv_worker, video, out)
        except Exception as e:
            print(f"[ERROR] OpenCV screenshot failed: {e}")
            success = False

            
        # 2. Fallback to FFmpeg if OpenCV failed or didn't generate a thumbnail
        if not success or not os.path.isfile(out) or os.path.getsize(out) == 0:
            print(f"[DEBUG] OpenCV screenshot failed or produced empty file. Falling back to FFmpeg for: {video}")
            
            # Try multiple seek times to avoid black frames: 
            # 10%, 25%, 50%, 5s, 15s, 2s
            seek_times = []
            if duration > 20:
                seek_times = [
                    int(duration * 0.1),
                    int(duration * 0.25),
                    int(duration * 0.5),
                    5,
                    15,
                    2
                ]
            else:
                seek_times = [
                    max(int(duration) // 2, 1),
                    2,
                    1
                ]
                
            # Remove duplicates while preserving order
            seen = set()
            unique_seek_times = []
            for t in seek_times:
                t = max(1, min(t, int(duration) - 1))
                if t not in seen:
                    seen.add(t)
                    unique_seek_times.append(t)
                    
            fallback_thumb = f"fallback_{out}"
            fallback_created = False
            
            for seek_time in unique_seek_times:
                time_stamp = hhmmss(seek_time)
                print(f"[DEBUG] FFmpeg trying screenshot at seek_time={seek_time} ({time_stamp})")
                
                # Fast seek
                cmd = ["ffmpeg",
                       "-ss", f"{time_stamp}", 
                       "-i", f"{video}",
                       "-frames:v", "1",
                       "-q:v", "2",
                       "-an",
                       "-threads", "1",
                       f"{out}",
                       "-y"
                      ]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await process.communicate()
                
                # Slow seek fallback
                if not os.path.isfile(out) or os.path.getsize(out) == 0:
                    print(f"[DEBUG] Fast seek failed, trying slow seek at {time_stamp}...")
                    cmd = ["ffmpeg",
                           "-i", f"{video}",
                           "-ss", f"{time_stamp}", 
                           "-frames:v", "1",
                           "-q:v", "2",
                           "-an",
                           "-threads", "1",
                           f"{out}",
                           "-y"
                          ]
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process.communicate()
                    
                # Check if created and not black
                if os.path.isfile(out) and os.path.getsize(out) > 0:
                    # Read image in grayscale using cv2
                    img = cv2.imread(out, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        mean_val = img.mean()
                        print(f"[DEBUG] FFmpeg generated mean brightness: {mean_val:.2f}")
                        
                        # Store the first successfully read image as fallback
                        if not fallback_created:
                            import shutil
                            try:
                                shutil.copy2(out, fallback_thumb)
                                fallback_created = True
                            except Exception as e:
                                print(f"[DEBUG] Failed to copy fallback thumb: {e}")
                                
                        if mean_val >= 10.0:  # Not black!
                            success = True
                            break
                        else:
                            print(f"[DEBUG] Thumbnail at seek_time={seek_time} is black. Trying next...")
                            try:
                                os.remove(out)
                            except Exception:
                                pass
                    else:
                        print(f"[DEBUG] cv2 failed to read {out}")
                        try:
                            os.remove(out)
                        except Exception:
                            pass
                            
            if success and os.path.isfile(out) and os.path.getsize(out) > 0:
                if os.path.isfile(fallback_thumb):
                    try:
                        os.remove(fallback_thumb)
                    except Exception:
                        pass
            elif fallback_created and os.path.isfile(fallback_thumb) and os.path.getsize(fallback_thumb) > 0:
                print(f"[WARNING] FFmpeg all seeks below threshold. Using fallback: {fallback_thumb}")
                import shutil
                try:
                    if os.path.isfile(out):
                        os.remove(out)
                except Exception:
                    pass
                try:
                    shutil.move(fallback_thumb, out)
                    success = True
                except Exception as e:
                    print(f"[ERROR] Failed to move fallback to out: {e}")
            else:
                if os.path.isfile(out):
                    try:
                        os.remove(out)
                    except Exception:
                        pass
                if os.path.isfile(fallback_thumb):
                    try:
                        os.remove(fallback_thumb)
                    except Exception:
                        pass
                        
        if success and os.path.isfile(out) and os.path.getsize(out) > 0:
            optimized_out = optimize_thumbnail(out)
            print(f"[SUCCESS] Final thumbnail created and optimized: {optimized_out}")
            return optimized_out
            
        return None
    except Exception as e:
        print(f"[CRITICAL] Screenshot exception: {str(e)}")
        return None
        
last_update_time = time.time()
async def progress_callback(current, total, progress_message):
    percent = (current / total) * 100 if total > 0 else 0
    now = time.time()
    if not hasattr(progress_callback, "last_updates"):
        progress_callback.last_updates = {}

    msg_id = getattr(progress_message, "id", id(progress_message))
    last_update = progress_callback.last_updates.get(msg_id, 0)

    if now - last_update >= 3 or percent % 10 == 0 or current == total:
        progress_callback.last_updates[msg_id] = now
        completed_blocks = int(percent // 10)
        remaining_blocks = 10 - completed_blocks
        progress_bar_str = "❤️" * completed_blocks + "🤍" * remaining_blocks
        current_mb = current / (1024 * 1024)  
        total_mb = total / (1024 * 1024)      
        try:
            await progress_message.edit(
                f"╔══━⚡️Uploading⚡️━══╗\n"
                f" ┉━┉━┉━┉┉━┉━┉━┉┉━┉━\n"
                f">*┋ {progress_bar_str}\n\n"
                f">*┋ **__Progress:__** {percent:.2f}%\n"
                f">*┋ **__Uploaded:__** {current_mb:.2f} MB / {total_mb:.2f} MB\n\n"
                f"  ╚═══━━━─⚝─━━━═══╝\n\n"
                f"⚝__**"
            )
        except Exception:
            pass

async def prog_bar(current, total, ud_type, message, start):

    now = time.time()
    diff = now - start
    
    if not hasattr(prog_bar, "last_updates"):
        prog_bar.last_updates = {}

    msg_id = getattr(message, "id", id(message))
    last_update = prog_bar.last_updates.get(msg_id, 0)

    if (now - last_update) >= 3 or current == total:
        prog_bar.last_updates[msg_id] = now

        percentage = current * 100 / total if total > 0 else 0
        speed = current / diff if diff > 0 else 0
        if speed > 0 and diff > 0:
            elapsed_time = round(diff) * 1000
            time_to_completion = round((total - current) / speed) * 1000
            estimated_total_time = elapsed_time + time_to_completion
            estimated_str = TimeFormatter(milliseconds=estimated_total_time)
        else:
            estimated_str = "Calculating..."

        progress = "{0}{1}".format(
            ''.join(["❤️" for i in range(math.floor(percentage / 10))]),
            ''.join(["🤍" for i in range(10 - math.floor(percentage / 10))]))

        tmp = progress + PROGRESS_BAR.format( 
            round(percentage, 2),
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),

            estimated_str if estimated_str != '' else "0 s"
        )
        try:
            await message.edit_text(
                text="{}     {}".format(ud_type, tmp),)             

        except Exception:
            pass
def thumbnail(sender):
    path = os.path.join(THUMBNAIL_DIR, f'{sender}.jpg')
    return path if os.path.exists(path) else None

def add_pdf_watermark(pdf_path, watermark_text):
    temp_pdf = None
    try:
        import fitz
        import shutil
        if not watermark_text:
            return pdf_path
            
        abs_path = os.path.abspath(pdf_path)
        temp_pdf = abs_path + ".tmp.pdf"
        doc = fitz.open(abs_path)
        try:
            for page in doc:
                rect = page.rect
                width = rect.width
                height = rect.height
                
                # Add watermark text at the bottom of all pages
                footer_rect = fitz.Rect(0, height - 40, width, height - 10)
                page.insert_textbox(
                    footer_rect,
                    watermark_text,
                    fontsize=14,
                    fontname="helv",
                    color=(0.5, 0.5, 0.5),  # Medium gray
                    fill_opacity=0.6,       # Opacity
                    align=1                 # Centered
                )
            # Save modifications to temporary file, close doc, and move to destination
            doc.save(temp_pdf, incremental=False, encryption=fitz.PDF_ENCRYPT_KEEP)
        finally:
            doc.close()

        if os.path.exists(temp_pdf):
            shutil.move(temp_pdf, abs_path)
        return abs_path
    except Exception as e:
        print(f"[ERROR] Failed to add watermark to PDF: {e}")
        if temp_pdf and os.path.exists(temp_pdf):
            try:
                os.remove(temp_pdf)
            except Exception:
                pass
        return pdf_path

