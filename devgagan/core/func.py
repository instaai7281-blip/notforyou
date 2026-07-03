# ---------------------------------------------------
# File Name: func.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan
# GitHub: https://github.com/devgaganin/
# Telegram: https://t.me/team_spy_pro
# YouTube: https://youtube.com/@dev_gagan
# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

import math
import time , re
from pyrogram import enums
from config import CHANNEL_ID, OWNER_ID, THUMBNAIL_DIR 
from devgagan.core.mongo.plans_db import premium_users
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
async def gen_link(app,chat_id):
   link = await app.export_chat_invite_link(chat_id)
   return link

async def subscribe(app, message):
   update_channel = CHANNEL_ID
   url = await gen_link(app, update_channel)
   if update_channel:
      try:
         user = await app.get_chat_member(update_channel, message.from_user.id)
         if user.status == "kicked":
            await message.reply_text("You are Banned. Contact -- @CHOSEN_ONEx_bot")
            return 1
      except UserNotParticipant:
        caption = f"**Join our channel to use the bot 😉\nAfter Join... /start Again**"
        await message.reply_photo(photo="https://postimg.cc/K133r7Vf",caption=caption, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Join Now...", url=f"{url}")]]))
        return 1
      except Exception:
         await message.reply_text("Something Went Wrong. Contact us @CHOSEN_ONEx_bot ...")
         return 1
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
    if not hasattr(progress_bar, "last_update"):
        progress_bar.last_update = 0
            
    if (now - progress_bar.last_update) >= 5 or current == total:
        progress_bar.last_update = now
        percentage = current * 100 / total
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
        except:
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
    default_values = {'width': 1, 'height': 1, 'duration': 1}
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

        width = width or 1
        height = height or 1
        duration = duration or 1
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

# REPLACE screenshot() function in devgagan/core/func.py (Line 221-257)

async def screenshot(video, duration, sender):
    try:
        # Validate inputs
        if duration <= 0:
            duration = 10  # Fallback duration to allow seek
            
        out = f"thumb_{sender}_{int(time.time())}.jpg"
        success = False
        
        # 1. Try OpenCV first (super fast and handles non-black detection efficiently)
        try:
            print(f"[DEBUG] Trying OpenCV screenshot for: {video}")
            vcap = cv2.VideoCapture(video)
            if vcap.isOpened():
                frame_count = vcap.get(cv2.CAP_PROP_FRAME_COUNT)
                if frame_count > 0:
                    # Try 20 seek points from 5% to 100% of the video
                    attempts = 20
                    seek_pcts = [i * 0.05 for i in range(1, attempts + 1)]
                    fallback_frame = None
                    
                    for pct in seek_pcts:
                        frame_no = int(frame_count * pct)
                        vcap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
                        ret, frame = vcap.read()
                        if ret and frame is not None:
                            if fallback_frame is None:
                                fallback_frame = frame.copy()
                            
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            mean_val = gray.mean()
                            print(f"[DEBUG] OpenCV seek {pct*100:.1f}%: mean brightness = {mean_val:.2f}")
                            if mean_val >= 10.0:
                                cv2.imwrite(out, frame)
                                success = True
                                break
                    
                    if not success and fallback_frame is not None:
                        print("[DEBUG] OpenCV all seek attempts below brightness threshold. Using fallback frame.")
                        cv2.imwrite(out, fallback_frame)
                        success = True
                        
                vcap.release()
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
    percent = (current / total) * 100
    now = time.time()
    if not hasattr(progress_callback, "last_update"):
        progress_callback.last_update = 0

    if now - progress_callback.last_update >= 3 or percent % 10 == 0:
        progress_callback.last_update = now
        completed_blocks = int(percent // 10)
        remaining_blocks = 10 - completed_blocks
        progress_bar = "❤️" * completed_blocks + "🤍" * remaining_blocks
        current_mb = current / (1024 * 1024)  
        total_mb = total / (1024 * 1024)      
        await progress_message.edit(
    f"╔══━⚡️Uploading⚡️━══╗\n"
    f" ┉━┉━┉━┉┉━┉━┉━┉┉━┉━\n"
    f">*┋ {progress_bar}\n\n"
    f">*┋ **__Progress:__** {percent:.2f}%\n"
    f">*┋ **__Uploaded:__** {current_mb:.2f} MB / {total_mb:.2f} MB\n\n"
    f"  ╚═══━━━─⚝─━━━═══╝\n\n"
    f"**__Pwrd by CHOSEN ONE ⚝__**"
        )

async def prog_bar(current, total, ud_type, message, start):

    now = time.time()
    diff = now - start
    
    if not hasattr(prog_bar, "last_update"):
        prog_bar.last_update = 0
            
    if (now - prog_bar.last_update) >= 3 or current == total:
        prog_bar.last_update = now

        percentage = current * 100 / total
        speed = current / diff
        elapsed_time = round(diff) * 1000
        time_to_completion = round((total - current) / speed) * 1000
        estimated_total_time = elapsed_time + time_to_completion

        elapsed_time = TimeFormatter(milliseconds=elapsed_time)
        estimated_total_time = TimeFormatter(milliseconds=estimated_total_time)

        progress = "{0}{1}".format(
            ''.join(["❤️" for i in range(math.floor(percentage / 10))]),
            ''.join(["🤍" for i in range(10 - math.floor(percentage / 10))]))

        tmp = progress + PROGRESS_BAR.format( 
            round(percentage, 2),
            humanbytes(current),
            humanbytes(total),
            humanbytes(speed),

            estimated_total_time if estimated_total_time != '' else "0 s"
        )
        try:
            await message.edit_text(
                text="{}     {}".format(ud_type, tmp),)             

        except:
            pass
def thumbnail(sender):
    path = os.path.join(THUMBNAIL_DIR, f'{sender}.jpg')
    return path if os.path.exists(path) else None

def add_pdf_watermark(pdf_path, watermark_text):
    try:
        import fitz
        if not watermark_text:
            return pdf_path
            
        abs_path = os.path.abspath(pdf_path)
        doc = fitz.open(abs_path)
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
            
        # Save modifications
        doc.save(abs_path, incremental=False, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()
        return abs_path
    except Exception as e:
        print(f"[ERROR] Failed to add watermark to PDF: {e}")
        return pdf_path
