# ---------------------------------------------------
# File Name: get_func.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan
# GitHub: https://github.com/devgaganin/
# Telegram: https://t.me/team_spy_pro
# YouTube: https://youtube.com/@dev_gagan
# Created: 2025-01-11
# Last Modified: 2025-02-01
# Version: 2.0.5
# License: MIT License
# Improved logic handles
# ---------------------------------------------------

import asyncio
import time
import gc
import os
import re
from typing import Callable
from devgagan import app, get_client, task_semaphore
import aiofiles
from devgagan import sex as gf
from telethon.tl.types import DocumentAttributeVideo, Message
from telethon.sessions import StringSession
import pymongo
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import ChannelBanned, ChannelInvalid, ChannelPrivate, ChatIdInvalid, ChatInvalid
from pyrogram.enums import MessageMediaType, ParseMode
from devgagan.core.func import *
from pyrogram.errors import RPCError
from pyrogram.types import Message
from config import MONGO_DB as MONGODB_CONNECTION_STRING, LOG_GROUP, OWNER_ID, STRING, STRINGS, API_ID, API_HASH, THUMBNAIL_DIR
from devgagan.core.mongo import db as odb
from telethon import TelegramClient, events, Button
from devgagantools import fast_upload, fast_download
from datetime import datetime
import asyncio
import unicodedata
from datetime import datetime
from pyrogram.enums import ParseMode
from telethon.tl.types import DocumentAttributeVideo
import random

# Define custom emojis for random selection
CUSTOM_EMOJIS = ["🍁", "🍀", "👑", "✨", "🦋", "🌟", "💖"]

# Enhanced cleaning utilities

def remove_chaudhary_fancy(text):
    if not text:
        return text
    
    translation_map = {
        # Small Caps
        'ᴀ': 'a', 'ʙ': 'b', 'ᴄ': 'c', 'ᴅ': 'd', 'ᴇ': 'e', 'ғ': 'f', 'ɢ': 'g', 'ʜ': 'h', 
        'ɪ': 'i', 'ᴊ': 'j', 'ᴋ': 'k', 'ʟ': 'l', 'ᴍ': 'm', 'ɴ': 'n', 'ᴏ': 'o', 'ᴘ': 'p', 
        'ǫ': 'q', 'ʀ': 'r', 'ꜱ': 's', 'ᴛ': 't', 'ᴜ': 'u', 'ᴠ': 'v', 'ᴡ': 'w', 'x': 'x', 
        'ʏ': 'y', 'ᴢ': 'z',
        # Lao / Tai Viet / other mimics
        'ꫝ': 'h', 'ຮ': 's', 'ꪮ': 'o', 'ꪎ': 'x', 'ꪗ': 'y',
    }
    
    # Pre-translate text for matching
    translated_chars = []
    orig_indices = []
    current_idx = 0
    for char in text:
        norm_char = unicodedata.normalize("NFKC", char)
        translated_char = "".join(translation_map.get(c, c) for c in norm_char)
        
        orig_indices.append((current_idx, current_idx + len(translated_char)))
        current_idx += len(translated_char)
        translated_chars.append(translated_char)
        
    normalized_text = "".join(translated_chars)
    
    unwanted_patterns = [
        r'chaudhary[^a-zA-Z0-9\s]*',
        r'PahadiXBabhan[^a-zA-Z0-9\s]*',
        r'LUCIFER[^a-zA-Z0-9\s]*',
        r'Babhan[^a-zA-Z0-9\s]*',
        r'Pahadi[^a-zA-Z0-9\s]*',
        r'insaan[^a-zA-Z0-9\s]*',
        r'team\s*hs[^a-zA-Z0-9\s]*',
        r'team\s*hs\s*亗?',
        r'(?:extracted|downloaded|download|uploaded|upload|forwarded)[\s_]*by\s*[:\-➤>–\-]*\s*[^\n]*',
    ]
    
    match_indices = set()
    for pattern in unwanted_patterns:
        matches = list(re.finditer(f'(?i){pattern}', normalized_text))
        for match in matches:
            for idx in range(match.start(), match.end()):
                match_indices.add(idx)
            
    cleaned_chars = []
    for i, char in enumerate(text):
        codepoint = ord(char)
        if 0x13000 <= codepoint <= 0x1342F or char in ('𓆩', '𓆪', '𓃮'):
            continue
            
        start_norm, end_norm = orig_indices[i]
        if any(idx in match_indices for idx in range(start_norm, end_norm)):
            continue
        cleaned_chars.append(char)
        
    result = "".join(cleaned_chars)
    result = re.sub(r'^[ \t\-_]+|[ \t\-_]+$', '', result)
    result = re.sub(r'[ \t]+', ' ', result)
    return result.strip()

def clean_text_advanced(text, user_tag, delete_words=None, replacements=None):
    """Advanced text cleaning for captions and filenames.
    Removes unwanted branding, replaces mentions, stylizes brackets, and applies custom deletions/replacements.
    """
    if not text:
        return text
    
    # Clean Chaudhary fancy text first
    text = remove_chaudhary_fancy(text)
    
    unwanted_phrases = [
        r'team[\s_\-\.]*jnc',
        r'team[\s_\-\.]*spy',
        r'team[\s_\-\.]*spy',
        r'team[\s_\-\.]*spy[\s_\-\.]*pro',
        r"let'?s\s*help",
        r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?',
        r'devgagan',
        r'@Src_pro_bot',
        r'Chosen\s*One',
        r'jnc',
        r'spy',
        r'spay',
        r'lets\s*help'
    ]
    for phrase in unwanted_phrases:
        text = re.sub(f'(?i)[*_]*{phrase}[*_]*', '', text)
    
    # Replace @mentions with user_tag
    if user_tag:
        text = re.sub(r'@\w+', user_tag, text)
    
    # Stylize brackets
    text = re.sub(r'[({[]', '〘', text)
    text = re.sub(r'[)}\]]', '〙', text)
    
    # Rebrand extraction markers
    text = re.sub(r'(?i)(Extracted|Downloaded|Download|Uploaded|Upload|Forwarded)[\s_]*By[\s_:➤>–\-]*[^\n]*', '', text)
    
    if delete_words:
        for word in delete_words:
            text = text.replace(word, ' ')
    if replacements:
        for old, new in replacements.items():
            text = text.replace(old, new)
    
    # Collapse whitespace but keep newlines
    text = re.sub(r'[ \t]+', ' ', text).strip()
    return text


def clean_filename(text, user_tag=""):
    """Clean filename, optionally replacing @mentions with a tag.
    Returns a safe filename string.
    """
    if not text:
        return "file"
    
    # Clean Chaudhary fancy text first
    text = remove_chaudhary_fancy(text)
    
    # Apply advanced cleaning without delete/replacements (just branding removal)
    text = clean_text_advanced(text, user_tag)
    
    # Normalize Unicode
    text = unicodedata.normalize("NFKC", text)
    
    # Remove emojis and symbols, keep basic punctuation for filenames
    text = ''.join(
        char for char in text
        if not unicodedata.category(char).startswith('S')
        and not unicodedata.category(char).startswith('C')
        and not unicodedata.category(char).startswith('P')
        or char in ['.', '-', '_', '〘', '〙', '⛥', '⚝']
    )
    
    # Normalize spaces, dashes, underscores
    text = re.sub(r'[_\s\-]+', ' ', text)
    
    # Preserve PDF marker
    if text.lower().endswith('.pdf'):
        text = re.sub(r'(?i)\.pdf$', ' ⛥.pdf', text)
    
    return text.strip()


def clean_text_message(text, sender=None):
    """Clean text messages - remove links, mentions, hashtags, unwanted branding."""
    if not text:
        return text
        
    if sender:
        is_keep_original = load_user_data(sender, "keep_original_caption", False)
        if is_keep_original:
            text = re.sub(r'tg://\S+', '', text)
            text = re.sub(r'\[[^\]]*\]\((?:tg://|https?://(?:t\.me|telegram\.(?:me|dog)))\S*\)', '', text)
            text = re.sub(r'[*_`\[\](]*@\w+[*_`\])(]*', '', text)
            text = re.sub(r'@\w+', '', text)
            return text
    
    # Remove zero-width characters
    text = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', text)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Remove tg:// links and markdown links to telegram domains first
    text = re.sub(r'tg://\S+', '', text)
    text = re.sub(r'\[[^\]]*\]\((?:tg://|https?://(?:t\.me|telegram\.(?:me|dog)))\S*\)', '', text)
    
    # Remove ALL URLs
    text = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+', '', text)
    
    # Remove @mentions (with formatting)
    text = re.sub(r'[*_`\[\](]*@\w+[*_`\])(]*', '', text)
    text = re.sub(r'@\w+', '', text)
    
    # Remove hashtags
    text = re.sub(r'#\S+', '', text)
    
    # Remove unwanted branding patterns
    branding_patterns = [
        r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*sp[ay]+[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*spy[\s_\-\.]*pro[*_]*',
        r"(?i)[*_]*let'?s\s*help[*_]*",
        r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?',
        r'(?i)devgagan',
        r'(?i)(Extracted|Downloaded|Download|Uploaded|Upload|Forwarded)[\s_]*By[\s_:➤>–\-]*[^\n]*',
        r'(?i)powered\s*by[^\n]*',
        r'(?i)via\s*@\w+',
        r'(?i)bot:\s*@\w+',
    ]
    for pattern in branding_patterns:
        text = re.sub(pattern, '', text)
    
    # Clean Chaudhary fancy text
    text = remove_chaudhary_fancy(text)
    
    # Apply user-specific cleaning if sender available
    if sender:
        delete_words = load_delete_words(sender)
        replacements = load_replacement_words(sender)
        for word in delete_words:
            text = text.replace(word, '')
        for old, new in replacements.items():
            text = text.replace(old, new)
    
    # Collapse whitespace but keep newlines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


# MongoDB database name and collection name
DB_NAME = "user_data"
COLLECTION_NAME = "users_data_db"

VIDEO_EXTENSIONS = ['mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv', 'webm', 'mpg', 'mpeg', '3gp', 'ts', 'm4v', 'f4v', 'vob']
DOCUMENT_EXTENSIONS = ['pdf', 'docs']

mongo_app = pymongo.MongoClient(MONGODB_CONNECTION_STRING)
db = mongo_app[DB_NAME]
collection = db[COLLECTION_NAME]

if STRINGS:
    from devgagan import pro
else:
    pro = None

user_progress = {}

async def is_enabled(user_id, media_type):
    data = await odb.get_data(user_id)
    if not data:
        return True
    filters = data.get("filters", {})
    return filters.get(media_type, True)

async def fetch_upload_method(user_id):
    """Fetch the user's preferred upload method."""
    user_data = collection.find_one({"user_id": user_id})
    return user_data.get("upload_method", "Pyrogram") if user_data else "Pyrogram"


def extract_message_topic_id(msg):
    if not msg:
        return None
    try:
        if hasattr(msg, "chat"):
            if hasattr(msg, "message_thread_id") and msg.message_thread_id:
                return msg.message_thread_id
            if hasattr(msg, "reply_to_message_id") and msg.reply_to_message_id:
                return msg.reply_to_message_id
        else:
            if hasattr(msg, "reply_to") and msg.reply_to:
                return msg.reply_to.reply_to_msg_id
    except Exception:
        pass
    return None


def extract_source_topic_id(link):
    if not link:
        return None
    try:
        link = re.sub(r'https?://', '', link)
        link = re.sub(r'^(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', link)
        parts = [p for p in link.split('/') if p]
        
        if len(parts) >= 4 and parts[0] == 'c':
            return int(parts[2])
            
        if len(parts) >= 3 and parts[0] != 'c':
            if parts[1].isdigit() and parts[2].isdigit():
                return int(parts[1])
    except Exception:
        pass
    return None


def parse_target_chat(input_str):
    if not input_str:
        return None
    input_str = input_str.strip()
    
    # Check if it is a Telegram link
    if "t.me/" in input_str or "telegram.me/" in input_str or "telegram.dog/" in input_str:
        # Clean protocol
        link = re.sub(r'https?://', '', input_str)
        # Clean domain
        link = re.sub(r'^(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', link)
        # parts: e.g. c/2407156919/430/431
        parts = [p for p in link.split('/') if p]
        
        if not parts:
            return input_str
            
        if parts[0] == 'c':
            # Private chat link
            if len(parts) >= 2:
                chat_id_str = parts[1]
                if not chat_id_str.startswith("-100"):
                    chat_id_str = "-100" + chat_id_str
                
                # Check for topic ID
                if len(parts) >= 4:
                    topic_id = parts[2]
                    return f"{chat_id_str}/{topic_id}"
                else:
                    return chat_id_str
        else:
            # Public username link
            chat_username = parts[0]
            if not chat_username.startswith("@"):
                chat_username = "@" + chat_username
                
            if len(parts) >= 3:
                topic_id = parts[1]
                return f"{chat_username}/{topic_id}"
            else:
                return chat_username
                
    return input_str


async def check_and_auto_forward(sender, message_or_file, caption=None, reply_markup=None, attributes=None, thumb_path=None, client_to_use=None, source_topic_id=None):
    try:
        from devgagan.core.mongo.db import get_forward_mapping
        target_dest = await get_forward_mapping(sender)
        if not target_dest:
            return
            
        dest_chat_id = target_dest
        dest_topic_id = None
        if '/' in str(target_dest):
            try:
                parts = str(target_dest).split('/', 1)
                dest_chat_id = int(parts[0])
                dest_topic_id = int(parts[1])
            except Exception:
                pass
        else:
            if source_topic_id:
                dest_topic_id = source_topic_id
                
        from pyrogram.types import Message as PyMessage
        if isinstance(message_or_file, PyMessage):
            try:
                await message_or_file.copy(
                    chat_id=dest_chat_id,
                    message_thread_id=dest_topic_id,
                    caption=caption
                )
            except Exception as e:
                if dest_topic_id:
                    print(f"Auto-forward to topic {dest_topic_id} failed: {e}. Falling back to main group...")
                    await message_or_file.copy(
                        chat_id=dest_chat_id,
                        caption=caption
                    )
                else:
                    raise e
        else:
            if client_to_use:
                try:
                    await client_to_use.send_file(
                        dest_chat_id,
                        message_or_file,
                        caption=caption,
                        attributes=attributes,
                        reply_to=dest_topic_id,
                        thumb=thumb_path
                    )
                except Exception as e:
                    if dest_topic_id:
                        print(f"Auto-forward Telethon to topic {dest_topic_id} failed: {e}. Falling back to main group...")
                        await client_to_use.send_file(
                            dest_chat_id,
                            message_or_file,
                            caption=caption,
                            attributes=attributes,
                            thumb=thumb_path
                        )
                    else:
                        raise e
    except Exception as e:
        print(f"Auto-forward helper failed: {e}")


def format_caption_to_html(caption: str) -> str:
    if not caption:
        return None

    caption = re.sub(r"^> (.*)", r"<blockquote>\1</blockquote>", caption, flags=re.MULTILINE)
    caption = re.sub(r"```(.*?)```", r"<pre>\1</pre>", caption, flags=re.DOTALL)
    caption = re.sub(r"`(.*?)`", r"<code>\1</code>", caption)
    caption = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", caption)
    caption = re.sub(r"\*(.*?)\*", r"<b>\1</b>", caption)
    caption = re.sub(r"__(.*?)__", r"<i>\1</i>", caption)
    caption = re.sub(r"_(.*?)_", r"<i>\1</i>", caption)
    caption = re.sub(r"~~(.*?)~~", r"<s>\1</s>", caption)
    caption = re.sub(r"\|\|(.*?)\|\|", r"<details>\1</details>", caption)
    caption = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', caption)
    
    return caption.strip()

    

from pyrogram.enums import ParseMode
from datetime import datetime
from telethon.tl.types import DocumentAttributeVideo
import os, gc, time, asyncio
import shutil, subprocess, os, math

# Unified log_upload
async def log_upload(user_id, file_type, file_msg, upload_method, duration=None, file_name=None):
    try:
        user = await app.get_users(user_id)
        bot = await app.get_me()

        # Keep mention format exactly like you want
        user_mention = user.mention if user else "User"

        bot_name = f"{bot.first_name} (@{bot.username})" if bot else "Unknown Bot"
        display_text = file_msg.caption or file_name or "No caption/filename"
        clean_text = (display_text[:1000] + '...') if len(display_text) > 1000 else display_text

        text = (
            f"{clean_text}\n\n"
            f"📁 **log info:**\n"
            f"👤 **User:** {user_mention}\n"
            f"🆔 **User ID:** `{user_id}`\n"
        )

        text += f"🤖 **Saved by:** {bot_name}"

        await file_msg.copy(LOG_GROUP, caption=text)

        # Real-time Auto-Forwarder for specific users (AIA)
        from devgagan.core.mongo.db import get_forward_mapping
        target_dest = await get_forward_mapping(user_id)
        if target_dest:
            dest_chat_id = target_dest
            dest_topic_id = None
            if '/' in str(target_dest):
                try:
                    parts = str(target_dest).split('/', 1)
                    dest_chat_id = int(parts[0])
                    dest_topic_id = int(parts[1])
                except Exception:
                    pass
            try:
                await file_msg.copy(
                    chat_id=dest_chat_id,
                    message_thread_id=dest_topic_id,
                    caption=clean_text
                )
            except Exception as fe:
                print(f"Log Forwarder failed to copy message: {fe}")

    except Exception as e:
        await app.send_message(LOG_GROUP, f"❌ Log Error: `{e}`")


# Upload handler
async def upload_media(sender, target_chat_id, file, caption, edit, topic_id, thumb=None, source_topic_id=None):
    try:
        upload_method = await fetch_upload_method(sender)
        metadata = video_metadata(file)

        # Extract metadata safely (only if video)
        width = metadata.get('width', 0)
        height = metadata.get('height', 0)
        duration = metadata.get('duration', 0)

        # Use passed thumb or retrieve/generate it
        thumb_path = thumb
        if not thumb_path:
            thumb_path = thumbnail(sender)
            if not thumb_path and file.lower().endswith(tuple(VIDEO_EXTENSIONS)):
                try:
                    print(f"[DEBUG] Trying to create thumbnail for: {file}, duration: {duration}")
                    thumb_path = await screenshot(file, duration, sender)
                    if not thumb_path:
                        print(f"[ERROR] Screenshot returned None for user {sender}")
                    else:
                        print(f"[SUCCESS] Thumbnail created: {thumb_path}")
                except Exception as e:
                    print(f"[ERROR] Screenshot exception for {sender}: {str(e)}")
                    thumb_path = None

        ext = file.split('.')[-1].lower()
        raw_name = os.path.basename(file)
        clean_name = clean_filename(os.path.splitext(raw_name)[0], user_tag='')
        file_name = f"{clean_name}.{ext}"

        video_formats = set(VIDEO_EXTENSIONS)
        image_formats = {'jpg', 'png', 'jpeg'}

        # ✅ Generate cleaned caption for user post
        if file.lower().endswith('.pdf') and not caption:
            filename = os.path.basename(file)
            tag = get_user_branding_tag(sender)
            caption = f"> **{filename}**\n\n> **{tag}**"

        # ✅ Generate log caption separately
        user = await app.get_users(sender)
        bot = await app.get_me()
        user_mention = user.mention if user else "User"
        bot_name = f"{bot.first_name} (@{bot.username})" if bot else "Bot"

        display_text = caption or file_name or "No caption/filename"
        clean_text = (display_text[:1000] + '...') if len(display_text) > 1000 else display_text

        log_caption = (            
            f"📁 **log info:**\n"
            f"👤 **User:** {user_mention}\n"
            f"🆔 **User ID:** `{sender}`\n"
            f"🤖 **Saved by:** {bot_name}"
        )

        # ────── Pyrogram Upload ──────
        if upload_method == "Pyrogram":
            has_spoiler = get_user_spoiler_preference(sender)
            if ext in video_formats:
                # Send to user
                dm = await app.send_video(
                    chat_id=target_chat_id,
                    video=file,
                    caption=caption,
                    height=height,
                    width=width,
                    duration=duration,
                    thumb=thumb_path,
                    message_thread_id=topic_id,
                    parse_mode=ParseMode.MARKDOWN,
                    progress=progress_bar,
                    progress_args=("╔══━⚡️Uploading...⚡️━══╗\n", edit, time.time()),
                    has_spoiler=has_spoiler
                )

            elif ext in image_formats:
                dm = await app.send_photo(
                    chat_id=target_chat_id,
                    photo=file,
                    caption=None,
                    progress=progress_bar,
                    message_thread_id=topic_id,
                    progress_args=("╔══━⚡️Uploading...⚡️━══╗\n", edit, time.time()),
                    has_spoiler=has_spoiler
                )

            else:
                dm = await app.send_document(
                    chat_id=target_chat_id,
                    document=file,
                    caption=caption,
                    thumb=thumb_path,
                    message_thread_id=topic_id,
                    parse_mode=ParseMode.MARKDOWN,
                    progress=progress_bar,
                    progress_args=("╔══━⚡️Uploading...⚡️━══╗\n", edit, time.time())
                )

            # ✅ Fast log: copy already-uploaded message instead of re-uploading from disk
            log_file_msg = await dm.copy(LOG_GROUP)
            await check_and_auto_forward(sender, dm, caption=caption, source_topic_id=source_topic_id)

            # ✅ Send log info separately as reply to log file
            await app.send_message(
                LOG_GROUP,
                text=log_caption,
                reply_to_message_id=log_file_msg.id,
                parse_mode=ParseMode.MARKDOWN
            )


        # ────── Telethon Upload ──────
        elif upload_method == "Telethon":
            await edit.delete()
            progress_message = await gf.send_message(sender, "**__Uploading...__**")
            caption_html = await format_caption_to_html(caption)

            uploaded = await fast_upload(
                gf, file,
                reply=progress_message,
                name=file_name,
                progress_bar_function=lambda done, total: progress_callback(done, total, sender)
            )
            await progress_message.delete()

            attributes = [
                DocumentAttributeVideo(duration=duration, w=width, h=height, supports_streaming=True)
            ] if ext in video_formats else []

            bot = await app.get_me()
            bot_name = f"{bot.first_name} (@{bot.username})" if bot else "Bot"

            log_caption = (
                f"📁 **File Name:** {file_name}\n\n"
                f"📤 **Upload Info**\n"
                f"👤 **User:** [{sender}](tg://user?id={sender})\n"
                f"🆔 **User ID:** `{sender}`\n"
                f"🗂️ **Type:** `{ext.upper()}`\n"

            )

            # Use already generated/retrieved thumb_path

            await gf.send_file(
                target_chat_id,
                uploaded,
                caption=caption_html,
                attributes=attributes,
                reply_to=topic_id,
                thumb=thumb_path
            )

            await gf.send_file(
                LOG_GROUP,
                uploaded,
                caption=log_caption,
                attributes=attributes,
                thumb=thumb_path
            )

            await check_and_auto_forward(
                sender=sender,
                message_or_file=uploaded,
                caption=caption_html,
                attributes=attributes,
                thumb_path=thumb_path,
                client_to_use=gf,
                source_topic_id=source_topic_id
            )

    except Exception as e:
        await app.send_message(LOG_GROUP, f"❌ **Upload Failed:** `{str(e)}`")
        print(f"Error during media upload: {e}")

    finally:
    # Only delete if it was not from saved thumbnail
        if thumb_path and os.path.exists(thumb_path) and not thumb_path.startswith(THUMBNAIL_DIR):
            os.remove(thumb_path)
        gc.collect()



async def get_msg(userbot: TelegramClient, sender: int, edit_id: int, msg_link: str, i: int = 0, message: Message = None):
    await task_semaphore.acquire()
    try:
        # If edit_id is None (e.g. in batch mode), create a temporary message to act as edit message
        edit = ''
        if edit_id is None:
            try:
                edit = await app.send_message(sender, "Processing batch link... ⏳")
                edit_id = edit.id
            except Exception as e:
                print(f"Failed to create batch status message: {e}")

        # Sanitize the message link
        msg_link = msg_link.split("?single")[0]
        chat, msg_id = None, None
        saved_channel_ids = load_saved_channel_ids()
        size_limit = 2 * 1024 * 1024 * 1024  # 1.99 GB size limit
        file = ''
        # Extract chat and message ID for various Telegram link formats
        if 't.me/c/' in msg_link or 't.me/b/' in msg_link:
            parts = [p for p in msg_link.split("/") if p]
            if 't.me/b/' in msg_link:
                chat = parts[-2]
                msg_id = int(parts[-1]) + i
            else:
                chat = int('-100' + parts[parts.index('c') + 1])
                msg_id = int(parts[-1]) + i
        elif 'tg://openmessage' in msg_link:
            import urllib.parse
            parsed_url = urllib.parse.urlparse(msg_link)
            params = urllib.parse.parse_qs(parsed_url.query)
            # Handle user_id, chat_id and id parameters
            chat_val = params.get("user_id", [None])[0] or params.get("chat_id", [None])[0] or params.get("id", [None])[0]
            msg_id = int(params.get("message_id", [0])[0]) + i
            if chat_val:
                chat_val = chat_val.strip()
                if chat_val.isdigit():
                    if len(chat_val) >= 10 and not chat_val.startswith("-100"):
                        chat = int("-100" + chat_val)
                    else:
                        chat = int(chat_val)
                elif chat_val.startswith("-"):
                    chat = int(chat_val)
                else:
                    chat = chat_val
            
            pass
        elif 't.me/' in msg_link or 'telegram.me/' in msg_link or 'telegram.dog/' in msg_link:
            if '/s/' in msg_link: # handles stories
                edit = await app.edit_message_text(sender, edit_id, "Story Link Detected... 📸")
                if userbot is None:
                    await edit.edit("Please login using /login to save stories.")     
                    return
                parts = [p for p in msg_link.split("/") if p]
                # parts: ['https:', 't.me', 's', 'chat_id', 'msg_id'] -> index 3 is chat_id
                chat = parts[3]
                if chat.isdigit():
                    chat = f"-100{chat}"
                msg_id = int(parts[-1])
                await download_user_stories(userbot, chat, msg_id, edit, sender)
                await edit.delete(2)
                return
            
            # Public links, Forum/Topic links
            # Link format: t.me/username/mid or t.me/username/topicid/mid
            # Split and filter empty parts
            domain = "t.me/" if "t.me/" in msg_link else "telegram.me/" if "telegram.me/" in msg_link else "telegram.dog/"
            parts = [p for p in msg_link.split(domain)[1].split("/") if p]
            if not parts:
                return
            chat = parts[0]
            msg_id = int(parts[-1]) + i
        else:
            chat = None
            msg_id = None

        if not chat or not msg_id:
            return

        # Check if the channel is protected
        if chat in saved_channel_ids:
            await app.edit_message_text(
                message.chat.id, edit_id,
                "This channel is protected by **__CHOSEN ONE ⚝__💀**.\nKya Be... Hamara Hi Content Nikalega 🌝 Kahi Or Try Kar 😘"
            )
            return

        # Determine if we should try a fast copy or force download
        is_private = 't.me/c/' in msg_link or 't.me/b/' in msg_link or 'tg://openmessage' in msg_link
        force_extraction = thumbnail(sender) or get_user_rename_preference(sender) != '⚝'

        # Set initial status message if not already set (e.g. by story/private link logic above)
        if not edit:
            status_text = "Processing link... 🌝"
            if is_private:
                status_text = "Processing Private Link... 🔐"
            elif force_extraction:
                status_text = "Custom settings detected, extracting... ⚡"
            edit = await app.edit_message_text(sender, edit_id, status_text)

        # Fast copy path without custom settings
        if not force_extraction:
            copy_success = await copy_message_with_chat_id(app, userbot, sender, chat, msg_id, edit)
            if copy_success:
                await edit.delete(2)
                return
            # If copy fails, fallback to extraction logic below
            await edit.edit("**Copy failed, trying extraction...**")
        
        # Ensure userbot is available for private links if we reached this point
        if is_private and userbot is None:
            await edit.edit("Please login using /login to access private links.")
            return

        # Fetch the target message
        # Priority: 1. Userbot (Personal) 2. Shared Userbot (Pro) 3. Bot (App)
        client = userbot if userbot else (get_client() or app)
        
        try:
            msg = await client.get_messages(chat, msg_id)
        except Exception as e:
            if userbot: # If userbot failed, try fallback to shared client or bot
                client = get_client() or app
                msg = await client.get_messages(chat, msg_id)
            else:
                raise e
        
        if not msg or msg.service or msg.empty:
            return

        # Apply filter checks in get_msg!
        if msg.media == MessageMediaType.WEB_PAGE_PREVIEW or msg.text:
            if not await is_enabled(sender, "text"):
                await edit.edit("🔇 **Text is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
        elif msg.media:
            if msg.video and not await is_enabled(sender, "video"):
                await edit.edit("🔇 **Video is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
            if msg.document and msg.document.file_name and msg.document.file_name.lower().endswith(('.html', '.htm')) and not await is_enabled(sender, "html"):
                await edit.edit("🔇 **HTML Files are turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
            if msg.document and not await is_enabled(sender, "document"):
                await edit.edit("🔇 **Document is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
            if msg.photo and not await is_enabled(sender, "photo"):
                await edit.edit("🔇 **Photo is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
            if msg.audio and not await is_enabled(sender, "audio"):
                await edit.edit("🔇 **Audio is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
            if msg.voice and not await is_enabled(sender, "voice"):
                await edit.edit("🔇 **Voice is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return
            if msg.sticker and not await is_enabled(sender, "sticker"):
                await edit.edit("🔇 **Sticker is turned OFF in settings. Skipping...**")
                await edit.delete(2)
                return

        # Special handling for protected content (Restrict Saving Content)
        # Main bots (app) cannot download protected content; only user accounts (userbots) can.
        if getattr(msg, "has_protected_content", False) and client == app:
            shared_client = get_client()
            if shared_client:
                client = shared_client
                # Refetch message with the new client to ensure session consistency for download
                msg = await client.get_messages(chat, msg_id)
            else:
                await edit.edit("🔒 **Protected Content Detected**\n\nThis channel has 'Restrict Saving Content' enabled. Only users who have **logged in** via /login can download this. Please login and try again.")
                return
        
        target_chat_id = get_target_chat_id(message.chat.id)
        topic_id = None
        if '/' in str(target_chat_id):
            try:
                target_chat_id, topic_id = map(int, str(target_chat_id).split('/', 1))
            except ValueError:
                pass
        else:
            topic_id = extract_message_topic_id(msg)

        # Handle different message types
        if msg.media == MessageMediaType.WEB_PAGE_PREVIEW:
            if not await is_enabled(sender, "text"):
                return
            await clone_message(app, msg, target_chat_id, topic_id, edit_id, LOG_GROUP, sender=sender)
            return

        if msg.text:
            if not await is_enabled(sender, "text"):
                return
            await clone_text_message(app, msg, target_chat_id, topic_id, edit_id, LOG_GROUP, sender=sender)
            return

        if msg.sticker:
            await handle_sticker(app, msg, target_chat_id, topic_id, edit_id, LOG_GROUP)
            return

        
        # Handle file media (photo, document, video)
        file_size = get_message_file_size(msg)

        file_name = await get_media_filename(msg)
        await edit.edit("**>Downloading...Darling 😘**")

        # Download media
        try:
            # unique directory for each user to prevent concurrency collisions
            temp_dir = os.path.join("downloads", str(sender))
            os.makedirs(temp_dir, exist_ok=True)
            
            # Join the chat first to resolve username entity and prevent PeerIdInvalid / ChannelPrivate errors
            if client and client != app and isinstance(chat, str) and not chat.startswith("-") and not chat.isdigit():
                try:
                    await client.join_chat(chat)
                except Exception:
                    pass
            
            target_file_path = os.path.join(temp_dir, file_name)
            file = await client.download_media(
                msg,
                file_name=target_file_path,            
                progress_args=("╔══━⚡️ Downloading ⚡️━══╗\n", edit, time.time()),
                progress=progress_bar
            )
        except Exception as e:
            print(f"Download error: {e}")
            file = None
        
        if not file:
            # Final fallback: if it's protected and failed, maybe the shared client isn't in the channel?
            if getattr(msg, "has_protected_content", False) and not userbot:
                 await edit.edit("❌ **Protected Download Failed**\n\nThis content is protected and the shared userbot couldn't access it. Please **login with your own account** using /login to bypass this restriction.")
            else:
                 await edit.edit(f"❌ **Download failed** - The file might be corrupted or the session has expired.\n\n**Error:** `{str(client.__class__.__name__)} session issue`")
            return

        caption = await get_final_caption(msg, sender)

        # Rename file
        file = await rename_file(file, sender)

        if file and str(file).lower().endswith('.pdf') and not caption:
            filename = os.path.basename(file)
            tag = get_user_branding_tag(sender)
            caption = f"> **{filename}**\n\n> **{tag}**"

        # Apply PDF Watermark if applicable
        if file and str(file).lower().endswith('.pdf'):
            watermark = load_user_data(sender, "watermark_text")
            if watermark:
                await edit.edit("**📄 Adding PDF Watermark...**")
                file = add_pdf_watermark(file, watermark)

        if msg.audio:
            if not await is_enabled(sender, "audio"):
                return
            result = await app.send_audio(target_chat_id, file, caption=caption, message_thread_id=topic_id)
            await result.copy(LOG_GROUP)
            await check_and_auto_forward(sender, result, caption=caption, source_topic_id=extract_message_topic_id(msg))
            await edit.delete(1)
            return
        
        if msg.voice:
            result = await app.send_voice(target_chat_id, file, message_thread_id=topic_id)
            await result.copy(LOG_GROUP)
            await check_and_auto_forward(sender, result, source_topic_id=extract_message_topic_id(msg))
            await edit.delete(1)
            return

        if msg.photo:
            if not await is_enabled(sender, "photo"):
                return
            result = await app.send_photo(target_chat_id, file, caption=None, message_thread_id=topic_id)
            await result.copy(LOG_GROUP)
            await check_and_auto_forward(sender, result, source_topic_id=extract_message_topic_id(msg))
            await edit.delete(1)
            return

        # Upload media
        # await edit.edit("**Checking file...**")
        if msg.video and not await is_enabled(sender, "video"):
            return
        if msg.document and msg.document.file_name and msg.document.file_name.lower().endswith(('.html', '.htm')) and not await is_enabled(sender, "html"):
            return
        if msg.document and not await is_enabled(sender, "document"):
            return

        # Prepare thumbnail beforehand
        thumb_path = thumbnail(sender)
        file_extension = str(file).split('.')[-1].lower()
        if not thumb_path and file_extension in VIDEO_EXTENSIONS:
            metadata = video_metadata(file)
            duration = metadata.get('duration', 0)
            try:
                thumb_path = await screenshot(file, duration, sender)
            except Exception as e:
                print(f"[ERROR] Failed to auto-screenshot in get_msg: {e}")

        free_check = await chk_user(message, sender)
        if file_size > size_limit and (free_check == 0 or pro is None):
            await edit.delete()
            await split_and_upload_file(app, sender, target_chat_id, file, caption, topic_id, thumb=thumb_path, source_topic_id=extract_message_topic_id(msg))
            return
        elif file_size > size_limit:
            await handle_large_file(file, sender, edit, caption)
        else:
            await upload_media(sender, target_chat_id, file, caption, edit, topic_id, thumb=thumb_path, source_topic_id=extract_message_topic_id(msg))

    except (ChannelBanned, ChannelInvalid, ChannelPrivate, ChatIdInvalid, ChatInvalid):
        await app.edit_message_text(sender, edit_id, "🌚 First do /login & then send me the Link again send /guide for more help")
    except Exception as e:
        if edit:
            try:
                await edit.edit(f"Failed to process: `{msg_link}`\n\n**Error:** {str(e)}")
            except:
                pass
        print(f"Error: {e}")
    finally:
        # Clean up
        if file and os.path.exists(file):
            try:
                os.remove(file)
            except Exception:
                pass
        if edit:
            try:
                await edit.delete(1)
            except Exception:
                pass
        task_semaphore.release()
        
async def clone_message(app, msg, target_chat_id, topic_id, edit_id, log_group, sender=None):
    edit = None
    try:
        edit = await app.edit_message_text(target_chat_id, edit_id, "Cloning...")
    except Exception:
        try:
            edit = await app.edit_message_text(msg.chat.id, edit_id, "Cloning...")
        except Exception:
            pass
    cleaned_text = clean_text_message(msg.text.markdown, sender)
    if not cleaned_text.strip():
        branding_tag = get_user_branding_tag(sender)
        cleaned_text = f"> **{branding_tag}**"
    devgaganin = await app.send_message(target_chat_id, cleaned_text, message_thread_id=topic_id)
    await devgaganin.copy(log_group)
    if edit:
        try:
            await edit.delete()
        except Exception:
            pass

async def clone_text_message(app, msg, target_chat_id, topic_id, edit_id, log_group, sender=None):
    edit = None
    try:
        edit = await app.edit_message_text(target_chat_id, edit_id, "Cloning text message...")
    except Exception:
        try:
            edit = await app.edit_message_text(msg.chat.id, edit_id, "Cloning text message...")
        except Exception:
            pass
    cleaned_text = clean_text_message(msg.text.markdown, sender)
    if not cleaned_text.strip():
        branding_tag = get_user_branding_tag(sender)
        cleaned_text = f"> **{branding_tag}**"
    devgaganin = await app.send_message(target_chat_id, cleaned_text, message_thread_id=topic_id)
    await devgaganin.copy(log_group)
    if edit:
        try:
            await edit.delete()
        except Exception:
            pass


async def handle_sticker(app, msg, target_chat_id, topic_id, edit_id, log_group):
    edit = None
    try:
        edit = await app.edit_message_text(target_chat_id, edit_id, "Handling sticker...")
    except Exception:
        try:
            edit = await app.edit_message_text(msg.chat.id, edit_id, "Handling sticker...")
        except Exception:
            pass
    result = await app.send_sticker(target_chat_id, msg.sticker.file_id, message_thread_id=topic_id)
    await result.copy(log_group)
    if edit:
        try:
            await edit.delete()
        except Exception:
            pass




async def get_media_filename(msg):
    if msg.document:
        return msg.document.file_name or "document.txt"
    if msg.video:
        return msg.video.file_name or "video.mp4"
    if msg.audio:
        return msg.audio.file_name or "audio.mp3"
    if msg.photo:
        return "image.jpg"
    return "file.dat"



def get_message_file_size(msg):
    if msg.document:
        return msg.document.file_size
    if msg.photo:
        return msg.photo.file_size
    if msg.video:
        return msg.video.file_size
    return 1



async def get_final_caption(msg, sender):
    # Get original caption in markdown if available
    original_caption = msg.caption.markdown if msg.caption else ""
    
    # Add custom caption if present
    custom_caption = get_user_caption_preference(sender)
    
    # Get filename
    filename = await get_media_filename(msg)
    
    # Format caption using format_caption to ensure consistent text cleaning and branding
    final_caption = format_caption(original_caption, sender, custom_caption, filename=filename)
    
    return final_caption if final_caption else None



async def download_user_stories(userbot, chat_id, msg_id, edit, sender):
    try:
        # Fetch the story using the provided chat ID and message ID
        story = await userbot.get_stories(chat_id, msg_id)
        if not story:
            await edit.edit("No story available for this user.")
            return  
        if not story.media:
            await edit.edit("The story doesn't contain any media.")
            return
        await edit.edit("Downloading Story...")
        
        # unique directory for each user to prevent concurrency collisions
        temp_dir = os.path.join("downloads", str(sender))
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = await userbot.download_media(story, file_name=temp_dir)
        print(f"Story downloaded: {file_path}")
        # Send the downloaded story based on its type
        if story.media:
            await edit.edit("Uploading Story...")
            if story.media == MessageMediaType.VIDEO:
                await app.send_video(sender, file_path)
            elif story.media == MessageMediaType.DOCUMENT:
                await app.send_document(sender, file_path)
            elif story.media == MessageMediaType.PHOTO:
                await app.send_photo(sender, file_path)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)  
        await edit.edit("Story processed successfully.")
    except RPCError as e:
        print(f"Failed to fetch story: {e}")
        await edit.edit(f"Error: {e}")
        
async def copy_message_with_chat_id(app, userbot, sender, chat_id, message_id, edit):
    target_chat_id = get_target_chat_id(sender)
    file = None
    result = None
    size_limit = 2 * 1024 * 1024 * 1024  # 2 GB size limit

    try:
        # Try with app or fallback client
        client_to_use = app
        try:
            msg = await client_to_use.get_messages(chat_id, message_id)
            if not msg or msg.empty:
                raise Exception("Message not found")
        except Exception:
            client_to_use = get_client()
            if client_to_use:
                msg = await client_to_use.get_messages(chat_id, message_id)
            else:
                return False

        if not msg or msg.empty:
            return False

        # Apply filter checks in copy_message_with_chat_id!
        if msg.media == MessageMediaType.WEB_PAGE_PREVIEW or msg.text:
            if not await is_enabled(sender, "text"):
                return True
        elif msg.media:
            if msg.video and not await is_enabled(sender, "video"):
                return True
            if msg.document and msg.document.file_name and msg.document.file_name.lower().endswith(('.html', '.htm')) and not await is_enabled(sender, "html"):
                return True
            if msg.document and not await is_enabled(sender, "document"):
                return True
            if msg.photo and not await is_enabled(sender, "photo"):
                return True
            if msg.audio and not await is_enabled(sender, "audio"):
                return True
            if msg.voice and not await is_enabled(sender, "voice"):
                return True
            if msg.sticker and not await is_enabled(sender, "sticker"):
                return True

        # If protected content, force extraction (return False here)
        if msg.has_protected_content:
            return False

        custom_caption = get_user_caption_preference(sender)
        filename = await get_media_filename(msg)
        final_caption = format_caption(msg.caption or '', sender, custom_caption, filename=filename)
        
        # Force blockquote tag for PDF files
        if msg.document and ((msg.document.file_name and msg.document.file_name.lower().endswith('.pdf')) or msg.document.mime_type == 'application/pdf') and not msg.caption:
            orig_filename = msg.document.file_name or "document.pdf"
            # Aggressively clean up original filename to remove others' tags
            clean_filename_base = remove_chaudhary_fancy(orig_filename)
            clean_filename_base = re.sub(r'@\w+', '', clean_filename_base)
            clean_filename_base = re.sub(r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*', '', clean_filename_base)
            clean_filename_base = re.sub(r'(?i)[*_]*team[\s_\-\.]*spay[*_]*', '', clean_filename_base)
            clean_filename_base = re.sub(r'(?i)[*_]*let\'?s\s*help[*_]*', '', clean_filename_base)
            clean_filename_base = re.sub(r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?', '', clean_filename_base)
            clean_filename_base = re.sub(r'[ \-_]+', ' ', clean_filename_base).strip()
            
            base_name, ext = os.path.splitext(clean_filename_base)
            if ext.lower() != '.pdf':
                ext = '.pdf'
            tag = get_user_branding_tag(sender)
            formatted_filename = f"{base_name.strip()} ⚝{ext}".strip()
            final_caption = f"> **{formatted_filename}**\n\n> **{tag}**"

        topic_id = None
        if '/' in str(target_chat_id):
            try:
                target_chat_id, topic_id = map(int, str(target_chat_id).split('/', 1))
            except ValueError:
                pass
        else:
            topic_id = extract_message_topic_id(msg)

        if msg.media:
            try:
                result = await send_media_message(client_to_use, target_chat_id, msg, final_caption, topic_id, sender)
            except Exception as e:
                if client_to_use != app:
                    print(f"Fast copy with client_to_use failed: {e}. Retrying with app...")
                    result = await send_media_message(app, target_chat_id, msg, final_caption, topic_id, sender)
                else:
                    raise e
        elif msg.text:
            cleaned_text = clean_text_message(msg.text.markdown if hasattr(msg.text, 'markdown') else str(msg.text), sender)
            if not cleaned_text.strip():
                branding_tag = get_user_branding_tag(sender)
                cleaned_text = f"> **{branding_tag}**"
            result = await app.send_message(target_chat_id, cleaned_text, message_thread_id=topic_id)
        
        if result:
            return True

    except Exception as e:
        print(f"App copy failed: {e}")

    # Fallback to userbot if app copy fails
    if userbot:
        try:
            await edit.edit("Trying extraction via userbot... ⚡")
            
            # Resolve chat_id if it's a username string
            if isinstance(chat_id, str) and not chat_id.startswith("-") and not chat_id.isdigit():
                try:
                    chat_entity = await userbot.get_entity(chat_id)
                    resolved_chat_id = chat_entity.id
                except Exception:
                    resolved_chat_id = chat_id
            else:
                resolved_chat_id = chat_id

            msg = await userbot.get_messages(resolved_chat_id, message_id)
            if not msg or msg.empty:
                return False

            if msg.text:
                cleaned_text = clean_text_message(msg.text.markdown if hasattr(msg.text, 'markdown') else str(msg.text), sender)
                if not cleaned_text.strip():
                    branding_tag = get_user_branding_tag(sender)
                    cleaned_text = f"> **{branding_tag}**"
                await app.send_message(target_chat_id, cleaned_text, message_thread_id=topic_id)
                return True

            custom_caption = get_user_caption_preference(sender)
            filename = await get_media_filename(msg)
            final_caption = format_caption(msg.caption.markdown if msg.caption else "", sender, custom_caption, filename=filename)
            
            # Try fast copy via userbot send_media first before downloading
            if not getattr(msg, "has_protected_content", False) and not force_extraction:
                try:
                    has_spoiler = get_user_spoiler_preference(sender)
                    if msg.video:
                        await userbot.send_video(target_chat_id, msg.video, caption=final_caption, message_thread_id=topic_id, has_spoiler=has_spoiler)
                        return True
                    elif msg.document:
                        await userbot.send_document(target_chat_id, msg.document, caption=final_caption, message_thread_id=topic_id)
                        return True
                    elif msg.photo:
                        await userbot.send_photo(target_chat_id, msg.photo, caption=final_caption, message_thread_id=topic_id, has_spoiler=has_spoiler)
                        return True
                    elif msg.audio:
                        await userbot.send_audio(target_chat_id, msg.audio, caption=final_caption, message_thread_id=topic_id)
                        return True
                except Exception as ue:
                    print(f"Userbot instant copy failed: {ue}")

            # unique directory for each user to prevent concurrency collisions
            temp_dir = os.path.join("downloads", str(sender))
            os.makedirs(temp_dir, exist_ok=True)

            # Join the chat first to resolve username entity and prevent PeerIdInvalid / ChannelPrivate errors
            if userbot and isinstance(resolved_chat_id, str) and not resolved_chat_id.startswith("-") and not resolved_chat_id.isdigit():
                try:
                    await userbot.join_chat(resolved_chat_id)
                except Exception:
                    pass

            target_file_path = os.path.join(temp_dir, filename)
            file = await userbot.download_media(
                msg,
                file_name=target_file_path,
                progress=progress_bar,
                progress_args=("╭─────────────────────╮\n│      **__Downloading__...**\n├─────────────────────", edit, time.time())
            )
            if not file:
                return False

            file = await rename_file(file, sender)

            if file and str(file).lower().endswith('.pdf') and not msg.caption:
                filename = os.path.basename(file)
                tag = get_user_branding_tag(sender)
                final_caption = f"> **{filename}**\n\n> **{tag}**"
            file_size = os.path.getsize(file)

            if msg.photo:
                await app.send_photo(target_chat_id, file, caption=None, message_thread_id=topic_id)
            elif msg.video or msg.document:
                freecheck = await chk_user(None, sender)
                if file_size > size_limit and (freecheck == 0 or pro is None):
                    await split_and_upload_file(app, sender, target_chat_id, file, final_caption, topic_id, source_topic_id=extract_message_topic_id(msg))
                elif file_size > size_limit:
                    await handle_large_file(file, sender, edit, final_caption)
                else:
                    await upload_media(sender, target_chat_id, file, final_caption, edit, topic_id, source_topic_id=extract_message_topic_id(msg))
            elif msg.audio:
                await app.send_audio(target_chat_id, file, caption=final_caption, message_thread_id=topic_id)
            elif msg.voice:
                await app.send_voice(target_chat_id, file, message_thread_id=topic_id)
            elif msg.sticker:
                await app.send_sticker(target_chat_id, msg.sticker.file_id, message_thread_id=topic_id)
            
            return True
        except Exception as e:
            print(f"Userbot extraction failed: {e}")
            return False
        finally:
            if file and os.path.exists(file):
                os.remove(file)
    
    return False

async def send_media_message(app, target_chat_id, msg, caption, topic_id, sender):
    try:
        file_name = None

        # Try to get file name if available
        if msg.document and msg.document.file_name:
            file_name = msg.document.file_name
        elif msg.video and msg.video.file_name:
            file_name = msg.video.file_name

        # Caption handling
        if msg.document and ((msg.document.file_name and msg.document.file_name.lower().endswith('.pdf')) or msg.document.mime_type == 'application/pdf') and not msg.caption:
            orig_filename = msg.document.file_name or "document.pdf"
            # Aggressively clean up original filename to remove others' tags
            clean_filename_base = remove_chaudhary_fancy(orig_filename)
            clean_filename_base = re.sub(r'@\w+', '', clean_filename_base)
            clean_filename_base = re.sub(r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*', '', clean_filename_base)
            clean_filename_base = re.sub(r'(?i)[*_]*team[\s_\-\.]*spay[*_]*', '', clean_filename_base)
            clean_filename_base = re.sub(r'(?i)[*_]*let\'?s\s*help[*_]*', '', clean_filename_base)
            clean_filename_base = re.sub(r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?', '', clean_filename_base)
            clean_filename_base = re.sub(r'[ \-_]+', ' ', clean_filename_base).strip()
            
            base_name, ext = os.path.splitext(clean_filename_base)
            if ext.lower() != '.pdf':
                ext = '.pdf'
            formatted_filename = f"{base_name.strip()} ⚝{ext}".strip()
            caption = f"> **{formatted_filename}**\n\n> **{DEFAULT_BRANDING_TAG}**"
        elif caption:
            # If caption exists → keep it same, just replace links if needed
            caption = re.sub(
                r'https?://t\.me/[^\s]+|https?://telegram\.me/[^\s]+',
                'https://t.me/+7R-7p7jVoz9mM2M1',
                caption
            )
        elif file_name:
            # If no caption → use only file name
            cleaned_file_name = remove_chaudhary_fancy(file_name)
            caption = f"🗃 {cleaned_file_name}"
        else:
            # If nothing → fallback
            caption = f"> **{DEFAULT_BRANDING_TAG}**"

        # Send the message with the right method
        has_spoiler = get_user_spoiler_preference(sender)
        if msg.video:
            return await app.send_video(
                target_chat_id,
                msg.video.file_id,
                caption=caption,
                message_thread_id=topic_id,
                has_spoiler=has_spoiler
            )

        if msg.document:
            return await app.send_document(
                target_chat_id,
                msg.document.file_id,
                caption=caption,
                message_thread_id=topic_id,
            )

        if msg.photo:
            return await app.send_photo(
                target_chat_id,
                msg.photo.file_id,
                caption=caption,
                message_thread_id=topic_id,
                has_spoiler=has_spoiler
            )

    except Exception as e:
        print(f"Error while sending media: {e}")
        return await app.send_message(
            target_chat_id,
            f"❌ Failed to send media.\n\nError: {e}"
        )



#CUSTOM_EMOJIS = ["🍁", "🍀", "👑", "✨", "🦋", "🌟", "💖"]

def replace_fancy_and_emoji(text: str) -> str:
    """
    Remove fancy Unicode characters (like 𝐀–𝒁, 𓆩𓆪, etc.)
    Replace emojis (symbols) with our custom emoji set.
    """
    result = []
    for char in text:
        code = ord(char)

        # Skip fancy styled alphabets (Mathematical, etc.)
        if (0x1D400 <= code <= 0x1D7FF) or (0x13000 <= code <= 0x1342F):
            continue

        # Replace emojis or symbolic characters
        if unicodedata.category(char) == "So" or char in ['️', '‍', '\u200d']:
            result.append(random.choice(CUSTOM_EMOJIS))
        else:
            result.append(char)

    return ''.join(result)

def format_caption(original_caption, sender, custom_caption, filename=None):
    branding_tag = get_user_branding_tag(sender)
    is_keep_original = load_user_data(sender, "keep_original_caption", False)

    if is_keep_original:
        if not original_caption:
            original_caption = ""
        # Remove @mentions and telegram/tg links even in raw mode
        original_caption = re.sub(r'tg://\S+', '', original_caption)
        original_caption = re.sub(r'\[[^\]]*\]\((?:tg://|https?://(?:t\.me|telegram\.(?:me|dog)))\S*\)', '', original_caption)
        original_caption = re.sub(r'[*_`\[\](]*@\w+[*_`\])(]*', '', original_caption)
        original_caption = re.sub(r'@\w+', '', original_caption)
        if original_caption.strip():
            return f"{original_caption}\n\n> **{branding_tag}**"
        elif filename:
            return f"> **{filename}**\n\n> **{branding_tag}**"
        else:
            return f"> **{branding_tag}**"

    delete_words = load_delete_words(sender)
    replacements = load_replacement_words(sender)

    if not original_caption:
        original_caption = ""

    # Remove zero-width characters
    original_caption = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', original_caption)

    # Remove HTML tags
    original_caption = re.sub(r'<[^>]+>', '', original_caption)

    # Clean Chaudhary fancy text
    original_caption = remove_chaudhary_fancy(original_caption)

    # Replace known branding tags from other bots
    other_tags = [
        "➪ @PDF_X9 🦋 ❞", "@PDF_X9", "➪ @PDF_X9 🦋",
        "⚝ 𝗝𝘂𝘀𝘁 𝗙ꪮ𝗿 𝗬ꪮ𝘂...💗", "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝",
    ]
    for tag in other_tags:
        original_caption = original_caption.replace(tag, '')

    # Remove unwanted branding patterns
    branding_patterns = [
        r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*sp[ay]+[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*spy[\s_\-\.]*pro[*_]*',
        r"(?i)[*_]*let'?s\s*help[*_]*",
        r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?',
        r'(?i)devgagan',
        r'(?i)chosen\s*one',
    ]
    for pattern in branding_patterns:
        original_caption = re.sub(pattern, '', original_caption)

    # Remove all hashtags
    original_caption = re.sub(r'#\S+', '', original_caption)

    # Remove tg:// links and markdown links to telegram domains first
    original_caption = re.sub(r'tg://\S+', '', original_caption)
    original_caption = re.sub(r'\[[^\]]*\]\((?:tg://|https?://(?:t\.me|telegram\.(?:me|dog)))\S*\)', '', original_caption)

    # Remove ALL URLs
    original_caption = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+', '', original_caption)

    # Remove ALL @mentions (with formatting)
    original_caption = re.sub(r'[*_`\[\](]*@\w+[*_`\])(]*', '', original_caption)
    original_caption = re.sub(r'@\w+', '', original_caption)

    # Replace "Extracted/Downloaded/Uploaded By" patterns
    original_caption = re.sub(
        r'(?i)(📩|⏫)?\s*(Extracted|Downloaded|Download|Uploaded|Upload|Forwarded)[\s_]*By[\s_:➤>–\-]*[^\n]*',
        '',
        original_caption
    )

    # Remove markdown artifacts
    original_caption = re.sub(r'\*{3,}', '', original_caption)
    original_caption = re.sub(r'_{3,}', '', original_caption)

    # 🔁 Delete unwanted words
    for word in delete_words:
        original_caption = original_caption.replace(word, ' ')

    # 🔁 Replace mapped words
    for old, new in replacements.items():
        original_caption = original_caption.replace(old, new)

    # Symbol replacements
    original_caption = original_caption.replace("[", "〘").replace("]", "〙").replace("(", "〘").replace(")", "〙")
    original_caption = original_caption.replace("📕", "📓")
    original_caption = original_caption.replace("📽️", "🍀")

    # Collapse whitespace
    original_caption = re.sub(r'[ \t]+', ' ', original_caption)
    original_caption = re.sub(r'\n{3,}', '\n\n', original_caption)
    original_caption = original_caption.strip()

    # Check custom caption
    if not custom_caption:
        custom_caption = get_user_caption_preference(sender)

    # Apply placeholders if custom caption exists
    if custom_caption:
        original_caption = apply_custom_caption_placeholders(custom_caption, original_caption, filename)
        return original_caption

    # Build final blockquote caption
    if original_caption:
        return f"{original_caption}\n\n> **{branding_tag}**"
    elif filename:
        return f"> **{filename}**\n\n> **{branding_tag}**"
    else:
        return f"> **{branding_tag}**"

# ------------------------ Button Mode Editz FOR SETTINGS ----------------------------

# Define a dictionary to store user chat IDs
user_chat_ids = {}

def get_target_chat_id(user_id):
    chat_id = load_user_data(user_id, "target_chat_id", None)
    if chat_id:
        return chat_id
    return user_id

def load_user_data(user_id, key, default_value=None):
    try:
        user_data = collection.find_one({"_id": user_id})
        return user_data.get(key, default_value) if user_data else default_value
    except Exception as e:
     
        print(f"Error loading {key}: {e}")
        return default_value

def load_saved_channel_ids():
    saved_channel_ids = set()
    try:
        # Retrieve channel IDs from MongoDB collection
        for channel_doc in collection.find({"channel_id": {"$exists": True}}):
            saved_channel_ids.add(channel_doc["channel_id"])
    except Exception as e:
        print(f"Error loading saved channel IDs: {e}")
    return saved_channel_ids

def save_user_data(user_id, key, value):
    try:
        collection.update_one(
            {"_id": user_id},
            {"$set": {key: value}},
            upsert=True
        )
    except Exception as e:
        print(f"Error saving {key}: {e}")


# Delete and replacement word functions
load_delete_words = lambda user_id: set(load_user_data(user_id, "delete_words", []))
save_delete_words = lambda user_id, words: save_user_data(user_id, "delete_words", list(words))

load_replacement_words = lambda user_id: load_user_data(user_id, "replacement_words", {})
save_replacement_words = lambda user_id, replacements: save_user_data(user_id, "replacement_words", replacements)

# User session functions
def load_user_session(user_id):
    return load_user_data(user_id, "session")

# Upload preference functions
set_dupload = lambda user_id, value: save_user_data(user_id, "dupload", value)
get_dupload = lambda user_id: load_user_data(user_id, "dupload", False)

# Spoiler preference functions
def get_user_spoiler_preference(user_id):
    return load_user_data(user_id, "spoiler", False)

def set_user_spoiler_preference(user_id, value):
    save_user_data(user_id, "spoiler", value)

# User preferences storage
user_rename_preferences = {}
user_caption_preferences = {}

# Rename and caption preference functions
async def set_rename_command(user_id, custom_rename_tag):
    user_rename_preferences[str(user_id)] = custom_rename_tag

async def set_caption_command(user_id, custom_caption):
    save_user_data(user_id, "caption", custom_caption)
    save_user_data(user_id, "caption_enabled", True)

get_user_rename_preference = lambda user_id: user_rename_preferences.get(str(user_id), '⚝')

# --- Branding Tag Selection ---
BRANDING_TAGS = {
    "stolenhappiness": "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝",
}
DEFAULT_BRANDING_TAG = "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝"

def get_user_branding_tag(user_id):
    """Get user's selected branding tag from MongoDB."""
    try:
        user_data = collection.find_one({"_id": int(user_id)})
        if not user_data:
            user_data = collection.find_one({"_id": str(user_id)})
        if user_data and "branding_tag" in user_data:
            return user_data["branding_tag"]
    except Exception as e:
        print(f"Error getting branding tag: {e}")
    return DEFAULT_BRANDING_TAG

def set_user_branding_tag(user_id, tag):
    """Save user's branding tag to MongoDB."""
    save_user_data(user_id, "branding_tag", tag)

def get_user_custom_tags(user_id):
    """Get user's list of custom branding tags from MongoDB."""
    try:
        user_data = collection.find_one({"_id": int(user_id)})
        if not user_data:
            user_data = collection.find_one({"_id": str(user_id)})
        if user_data and "custom_tags" in user_data and user_data["custom_tags"]:
            ctags = user_data["custom_tags"]
            if isinstance(ctags, list):
                return ctags
            elif isinstance(ctags, str):
                return [ctags]
    except Exception as e:
        print(f"Error getting custom tags: {e}")
    return []

def add_user_custom_tag(user_id, tag):
    """Add a new custom tag to user's saved list in MongoDB (max 5)."""
    try:
        tags = get_user_custom_tags(user_id)
        tag = tag.strip()
        if not tag:
            return False, "Tag cannot be empty!"
        if tag in tags:
            set_user_branding_tag(user_id, tag)
            return True, "Tag is already saved and selected!"
        if len(tags) >= 5:
            return False, "You can save up to 5 custom tags only! Delete one first."
        tags.append(tag)
        collection.update_one(
            {"_id": int(user_id)},
            {"$set": {"custom_tags": tags}},
            upsert=True
        )
        collection.update_one(
            {"_id": str(user_id)},
            {"$set": {"custom_tags": tags}}
        )
        set_user_branding_tag(user_id, tag)
        return True, "Tag added successfully!"
    except Exception as e:
        print(f"Error adding custom tag: {e}")
        return False, f"Error: {e}"

def delete_user_custom_tag(user_id, tag_index):
    """Delete a custom tag by index from user's saved list in MongoDB."""
    try:
        tags = get_user_custom_tags(user_id)
        if 0 <= tag_index < len(tags):
            deleted_tag = tags.pop(tag_index)
            collection.update_one(
                {"_id": int(user_id)},
                {"$set": {"custom_tags": tags}}
            )
            collection.update_one(
                {"_id": str(user_id)},
                {"$set": {"custom_tags": tags}}
            )
            current_tag = get_user_branding_tag(user_id)
            if current_tag == deleted_tag:
                set_user_branding_tag(user_id, "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
            return True, f"Tag '{deleted_tag}' deleted successfully!"
        return False, "Invalid tag index."
    except Exception as e:
        print(f"Error deleting custom tag: {e}")
        return False, f"Error: {e}"

def get_user_caption_preference(user_id):
    try:
        user_data = collection.find_one({"_id": int(user_id)})
        if not user_data:
            user_data = collection.find_one({"_id": str(user_id)})
        if user_data:
            # Check if custom caption is enabled (defaults to True)
            if user_data.get("caption_enabled", True):
                return user_data.get("caption", "")
    except Exception as e:
        print(f"Error getting user caption preference: {e}")
    return ""

def apply_custom_caption_placeholders(custom_caption, original_caption, filename):
    if not custom_caption:
        return original_caption
    
    # Prevent duplicate custom caption if it's already at the end of the original caption
    norm_custom = custom_caption.strip().replace("\n", "").replace(" ", "")
    norm_orig = original_caption.strip().replace("\n", "").replace(" ", "")
    if norm_custom and norm_orig.endswith(norm_custom):
        return original_caption
    
    # Clean original filename for display
    filename_clean = filename or ""
    if "." in filename_clean:
        filename_clean = ".".join(filename_clean.split(".")[:-1])
    
    # Check for placeholders
    has_caption_placeholder = "{caption}" in custom_caption
    has_filename_placeholder = "{filename}" in custom_caption
    
    if has_caption_placeholder or has_filename_placeholder:
        formatted = custom_caption
        formatted = formatted.replace("{filename}", filename_clean)
        formatted = formatted.replace("{caption}", original_caption or "")
        return formatted
    else:
        # Backward compatibility: append to original caption
        if original_caption:
            return f"{original_caption}\n\n{custom_caption}"
        return custom_caption

# Initialize the dictionary to store user sessions

sessions = {}
m = None
SET_PIC = "settings.jpg"
MESS = "Customize settings ..."

@gf.on(events.NewMessage(incoming=True, pattern='/settings'))
async def settings_command(event):
    user_id = event.sender_id
    await send_settings_message(event.chat_id, user_id)

def get_telethon_settings_buttons(user_id):
    is_spoiler = get_user_spoiler_preference(user_id)
    return [
        [Button.inline("💀 Forward to Chat", b'setchat'), Button.inline("✏️ Set Rename Tag", b'setrename')],
        [Button.inline("🔆 Set Caption", b'setcaption'), Button.inline("💠 Replace Words", b'setreplacement')],
        [Button.inline("‼️ Remove Words 🗑️", b'delete'), Button.inline("🏷️ Branding Tag", b'settag')],
        [Button.inline("🖼️ Set Thumbnail", b'setthumb'), Button.inline("🧲 Remove Thumbnail", b'remthumb')],
        [Button.inline("📄 Set PDF Watermark", b'setpdfwatermark'), Button.inline("🗑️ Remove PDF Watermark", b'rempdfwatermark')],
        [Button.inline("📤 Upload Method", b'uploadmethod'), Button.inline(f"🌶️ Spoiler: {'ON' if is_spoiler else 'OFF'}", b'togglespoiler')],
        [Button.inline("♻️ Reset All Settings ☢️", b'reset'), Button.inline("⛔ Logout", b'logout')],
        [Button.url("💞 Contact Owner 🦋", "https://t.me/Chosen_Onex_bot")]
    ]

async def send_settings_message(chat_id, user_id):
    await gf.send_file(
        chat_id,
        file=SET_PIC,
        caption=MESS,
        buttons=get_telethon_settings_buttons(user_id)
    )


pending_photos = {}

async def refresh_telethon_tag_page(event, user_id):
    current_tag = get_user_branding_tag(user_id)
    custom_tags = get_user_custom_tags(user_id)
    tag_buttons = []
    
    # 1) Stolen Happiness Preset
    is_sh_selected = (current_tag == "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
    tag_buttons.append([Button.inline(f"🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ {'✅' if is_sh_selected else ''}", b'tag_stolenhappiness')])
    
    # 2) Custom saved tags (up to 5)
    for i, tag in enumerate(custom_tags):
        is_active = (current_tag == tag)
        tag_buttons.append([
            Button.inline(f"✨ {tag[:20]}... {'✅' if is_active else ''}" if len(tag) > 20 else f"✨ {tag} {'✅' if is_active else ''}", f"tag_select_{i}".encode()),
            Button.inline("❌", f"tag_delete_{i}".encode())
        ])
        
    # 3) Add new custom tag button if less than 5
    if len(custom_tags) < 5:
        tag_buttons.append([Button.inline("➕ Add Custom Tag", b'tag_custom')])
        
    # 4) Back button
    tag_buttons.append([Button.inline("🔙 Back to Menu", b'back')])

    preview_text = (
        f"🏷️ **Branding Tag Settings**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current Tag: `{current_tag}`\n\n"
        f"📝 **How it will look in your captions:**\n"
        f"> 📁 **File:** `movie_title.mp4`\n"
        f"> ───\n"
        f"> **{current_tag}**\n\n"
        f"This branding tag appears in the captions of your files and on PDF document pages. Select a preset or set a custom tag below:"
    )

    await event.edit(
        preview_text,
        buttons=tag_buttons
    )

@gf.on(events.CallbackQuery)
async def callback_query_handler(event):
    user_id = event.sender_id
    data = event.data.decode()  # Decode bytes to string

    if data == 'setchat':
        await event.respond(
            "🎯 **Set Your Channel or Group**\n\n"
            "🆔 **Send the Chat ID** where you want to forward all posts automatically. 🌝\n\n"
            "💡 *Tip:* Just **add me to that chat**, then send `/id` in the Channel/Group.\n"
            "**I'll automatically detect the Chat ID.**"
        )
        sessions[user_id] = 'setchat'
    
    elif data == 'setrename':
        await event.respond("✏️ Send the **rename tag** you want to set your custom name")
        sessions[user_id] = 'setrename'

    elif data == 'settag':
        await refresh_telethon_tag_page(event, user_id)

    elif data == 'tag_stolenhappiness':
        set_user_branding_tag(user_id, "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
        await event.answer("Branding tag set to Stolen Happiness Preset")
        await refresh_telethon_tag_page(event, user_id)

    elif data == 'tag_custom':
        custom_tags = get_user_custom_tags(user_id)
        if len(custom_tags) >= 5:
            await event.answer("❌ You can save up to 5 custom tags only! Delete one first.", alert=True)
        else:
            await event.respond("✏️ Send your **custom branding tag** text:")
            sessions[user_id] = 'setbrandingtag'

    elif data.startswith('tag_select_'):
        tag_index = int(data.split('_')[-1])
        custom_tags = get_user_custom_tags(user_id)
        if 0 <= tag_index < len(custom_tags):
            tag = custom_tags[tag_index]
            set_user_branding_tag(user_id, tag)
            await event.answer(f"Selected: {tag}")
            await refresh_telethon_tag_page(event, user_id)
        else:
            await event.answer("Invalid tag index")

    elif data.startswith('tag_delete_'):
        tag_index = int(data.split('_')[-1])
        success, msg = delete_user_custom_tag(user_id, tag_index)
        await event.answer(msg, alert=True)
        await refresh_telethon_tag_page(event, user_id)

    elif data == 'setcaption':
        await event.respond("📝 Send the **caption format** (you can include variables like {filename}, {size}):")
        sessions[user_id] = 'setcaption'

    elif data == 'setreplacement':
        await event.respond("🔄 Send replacement inside this ' '\n\n'oldword' 'newword'\n\n")
        sessions[user_id] = 'setreplacement'

    elif data == 'addsession':
        await event.respond("🔐 Send your **Pyrogram V2 session string**:\n\n*(We recommend not sharing this publicly)*")
        sessions[user_id] = 'addsession'

    elif data == 'delete':
        await event.respond("🗑️ Send **words to delete** (separated by space) from the filename/caption:")
        sessions[user_id] = 'deleteword'

    elif data == 'logout':
        await odb.remove_session(user_id)
        user_data = await odb.get_data(user_id)
        if user_data and user_data.get("session") is None:
            await event.respond("✅ You have been **logged out** and your session was removed successfully.")
        else:
            await event.respond("⚠️ You are not logged in.")

    elif data == 'togglespoiler':
        current_val = get_user_spoiler_preference(user_id)
        new_val = not current_val
        set_user_spoiler_preference(user_id, new_val)
        await event.answer(f"Spoiler mode set to {'ON' if new_val else 'OFF'}")
        await event.edit(buttons=get_telethon_settings_buttons(user_id))

    elif data == 'setthumb':
        pending_photos[user_id] = True
        await event.respond("📸 Send the **photo** you want to use as your custom thumbnail.")

    elif data == 'setpdfwatermark':
        await event.respond("📄 Send the **text** you want to use as your custom PDF watermark.")
        sessions[user_id] = 'setpdfwatermark'

    elif data == 'rempdfwatermark':
        try:
            collection.update_one(
                {"_id": user_id},
                {"$unset": {"watermark_text": ""}}
            )
            collection.update_one(
                {"user_id": user_id},
                {"$unset": {"watermark_text": ""}}
            )
            await event.respond("✅ **PDF Watermark removed successfully!**")
        except Exception as e:
            await event.respond(f"❌ Error removing watermark: {e}")

    elif event.data == b'uploadmethod':
        # Retrieve the user's current upload method (default to Pyrogram)
        user_data = collection.find_one({'user_id': user_id})
        current_method = user_data.get('upload_method', 'Pyrogram') if user_data else 'Pyrogram'
        pyrogram_check = " ✅" if current_method == "Pyrogram" else ""
        telethon_check = " ✅" if current_method == "Telethon" else ""

        # Display the buttons for selecting the upload method
        buttons = [
            [Button.inline(f"🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ v1 ⚡{pyrogram_check}", b'pyrogram')],
            [Button.inline(f"⚠️ Coming soon V2 {telethon_check}", b'telethon')]
        ]
        await event.edit("Choose your preferred upload method:\n\n__**Note:** **🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ v2 ⚡**, built on Telethon(base), by @stolen_happines still in beta.__", buttons=buttons)

    elif event.data == b'pyrogram':
        save_user_upload_method(user_id, "Pyrogram")
        await event.edit("Upload method set to **Pyrogram** ✅")

    elif event.data == b'telethon':
        save_user_upload_method(user_id, "Telethon")
        await event.edit("Upload method set to **🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ V2 ⚡ \n\n Use V1 V2 is just Testing purpose**")        
        
    elif event.data == b'reset':
        try:
            user_id_str = str(user_id)
            
            collection.update_one(
                {"_id": user_id},
                {"$unset": {
                    "delete_words": "",
                    "replacement_words": "",
                    "watermark_text": "",
                    "duration_limit": "",
                    "target_chat_id": ""
                }}
            )
            
            collection.update_one(
                {"user_id": user_id},
                {"$unset": {
                    "delete_words": "",
                    "replacement_words": "",
                    "watermark_text": "",
                    "duration_limit": "",
                    "target_chat_id": ""
                }}
            )            
            user_chat_ids.pop(user_id, None)
            user_rename_preferences.pop(user_id_str, None)
            user_caption_preferences.pop(user_id_str, None)
            await odb.remove_thumbnail(user_id)
            thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            await event.respond("✅ Reset successfully, to logout click /logout")
        except Exception as e:
            await event.respond(f"Error clearing delete list: {e}")
    
    elif event.data == b'remthumb':
        try:
            await odb.remove_thumbnail(user_id)
            thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            await event.respond('Thumbnail removed successfully!')
        except Exception as e:
            await event.respond(f"Error removing thumbnail: {e}")
    

@gf.on(events.NewMessage(func=lambda e: e.sender_id in pending_photos))
async def save_thumbnail(event):
    user_id = event.sender_id  # Use event.sender_id as user_id

    if event.photo:
        thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
        await event.download_media(file=thumbnail_path)
        optimize_thumbnail(thumbnail_path)
        try:
            with open(thumbnail_path, "rb") as f:
                binary_data = f.read()
            await odb.set_thumbnail(user_id, binary_data)
        except Exception as e:
            print(f"[ERROR] Failed to save thumbnail to DB: {e}")
        await event.respond('✅ **Custom thumbnail saved successfully!**')
    else:
        await event.respond('❌ Please send a **photo** to set it as a thumbnail.')

    # Remove user from pending photos dictionary in both cases
    pending_photos.pop(user_id, None)

def save_user_upload_method(user_id, method):
    # Save or update the user's preferred upload method
    collection.update_one(
        {'user_id': user_id},  # Query
        {'$set': {'upload_method': method}},  # Update
        upsert=True  # Create a new document if one doesn't exist
    )

@gf.on(events.NewMessage)
async def handle_user_input(event):
    user_id = event.sender_id
    if user_id in sessions:
        session_type = sessions[user_id]

        if session_type == 'setchat':
            try:
                chat_id = event.text.strip()
                parsed_chat = parse_target_chat(chat_id)
                if parsed_chat:
                    chat_id = parsed_chat
                user_chat_ids[user_id] = chat_id
                save_user_data(user_id, "target_chat_id", chat_id)
                save_user_data(user_id, "chat_id", chat_id)
                await event.respond(f"Chat ID set successfully! ✅ Now i will Forward All Content to: `{chat_id}`")
            except Exception as e:
                await event.respond(f"Error setting Chat ID: {e}")
                
        elif session_type == 'setrename':
            custom_rename_tag = event.text
            await set_rename_command(user_id, custom_rename_tag)
            await event.respond(f"😉 Your Custom rename tag set to: {custom_rename_tag} 🌝")
        
        elif session_type == 'setcaption':
            custom_caption = event.text
            await set_caption_command(user_id, custom_caption)
            await event.respond(f"Custom caption set to: {custom_caption}")

        elif session_type == 'setreplacement':
            match = re.match(r"'(.+)' '(.+)'", event.text)
            if not match:
                await event.respond("Usage: 'Oldword(S)' 'ReplaceWord'\n\n **Example:** 'apple' 'banana'")
            else:
                word, replace_word = match.groups()
                delete_words = load_delete_words(user_id)
                if word in delete_words:
                    await event.respond(f"The word '{word}' is in the delete set and cannot be replaced.")
                else:
                    replacements = load_replacement_words(user_id)
                    replacements[word] = replace_word
                    save_replacement_words(user_id, replacements)
                    await event.respond(f"⇆ Replacement saved ⇆ \n\n 🌚 {word} ≫ {replace_word} 🌝")

        elif session_type == 'setbrandingtag':
            custom_tag = event.text.strip()
            if custom_tag:
                success, msg = add_user_custom_tag(user_id, custom_tag)
                if success:
                    await event.respond(f"✅ Tag added and selected:\n\n**{custom_tag}**")
                else:
                    await event.respond(f"❌ {msg}")
            else:
                await event.respond("❌ Tag cannot be empty.")

        elif session_type == 'addsession':
            session_string = event.text
            await odb.set_session(user_id, session_string)
            await event.respond("✅ Session string added successfully!")
                
        elif session_type == 'deleteword':
            words_to_delete = event.message.text.split()
            delete_words = load_delete_words(user_id)
            delete_words.update(words_to_delete)
            save_delete_words(user_id, delete_words)
            await event.respond(f"🗑️ Words added to delete list: {', '.join(words_to_delete)}")

        elif session_type == 'setpdfwatermark':
            watermark_text = event.text
            collection.update_one(
                {"_id": user_id},
                {"$set": {"watermark_text": watermark_text}},
                upsert=True
            )
            collection.update_one(
                {"user_id": user_id},
                {"$set": {"watermark_text": watermark_text}},
                upsert=True
            )
            await event.respond(f"✅ **PDF Watermark set to:** `{watermark_text}`")
               
            
        del sessions[user_id]
    
# Command to store channel IDs
@gf.on(events.NewMessage(incoming=True, pattern='/lock'))
async def lock_command_handler(event):
    if event.sender_id not in OWNER_ID:
        return await event.respond("You are not authorized to use this command.😘 its only for my owner")
    
    # Extract the channel ID from the command
    try:
        channel_id = int(event.text.split(' ')[1])
    except (ValueError, IndexError):
        return await event.respond("Invalid /lock command. Use /lock CHANNEL_ID.")
    
    # Save the channel ID to the MongoDB database
    try:
        # Insert the channel ID into the collection
        collection.insert_one({"channel_id": channel_id})
        await event.respond(f"Channel ID {channel_id} locked successfully.")
    except Exception as e:
        await event.respond(f"Error occurred while locking channel ID: {str(e)}")


async def handle_large_file(file, sender, edit, caption):
    if pro is None:
        await edit.edit('**__ ❌ 4GB trigger not found__**')
        os.remove(file)
        gc.collect()
        return
    
    dm = None
    
    print("4GB connector found.")
    await edit.edit('**__ ✅ 4GB trigger connected...__**\n\n')
    
    target_chat_id = get_target_chat_id(sender)
    file_extension = str(file).split('.')[-1].lower()
    metadata = video_metadata(file)
    duration = metadata['duration']
    width = metadata['width']
    height = metadata['height']
    
    # ✅ Handle thumbnail
    thumb_path = thumbnail(sender)
    if not thumb_path and file_extension in VIDEO_EXTENSIONS:
        thumb_path = await screenshot(file, duration, sender)
    try:
        if file_extension in VIDEO_EXTENSIONS:
            dm = await pro.send_video(
                LOG_GROUP,
                video=file,
                caption=caption,
                thumb=thumb_path,
                height=height,
                width=width,
                duration=duration,
                progress=progress_bar,
                progress_args=(
                    "╭─────────────────────╮\n│       **__4GB Uploader__ ⚡**\n├─────────────────────",
                    edit,
                    time.time()
                )
            )
        else:
            # Send as document
            dm = await pro.send_document(
                LOG_GROUP,
                document=file,
                caption=caption,
                thumb=thumb_path,
                progress=progress_bar,
                progress_args=(
                    "╭─────────────────────╮\n│      **__4GB Uploader ⚡__**\n├─────────────────────",
                    edit,
                    time.time()
                )
            )

        from_chat = dm.chat.id
        msg_id = dm.id
        freecheck = 0
        if freecheck == 1:
            reply_markup = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("💎 Get Premium to Forward", url="https://t.me/GeniusJunctionX")]
                ]
            )
            await app.copy_message(
                target_chat_id,
                from_chat,
                msg_id,
                protect_content=True,
                reply_markup=reply_markup
            )
        else:
            # Simple copy without protect_content or reply_markup
            await app.copy_message(
                target_chat_id,
                from_chat,
                msg_id
            )
            
    except Exception as e:
        print(f"Error while sending file: {e}")

    finally:
        await edit.delete()
        if os.path.exists(file):
            os.remove(file)
        if thumb_path and os.path.exists(thumb_path) and not thumb_path.startswith(THUMBNAIL_DIR):
            os.remove(thumb_path)
        gc.collect()


def strip_unicode_junk(text: str) -> str:
    """Remove stylized junk but preserve Indian language text and matras like ી િ ુ ે ા ૂ ૌ."""
    clean = []
    for char in text:
        codepoint = ord(char)
        name = unicodedata.name(char, "")

        # ✅ Preserve Gujarati & Indian scripts including matras
        if (
            0x0900 <= codepoint <= 0x097F or  # Devanagari
            0x0A80 <= codepoint <= 0x0AFF or  # Gujarati
            0x0980 <= codepoint <= 0x09FF or  # Bengali
            0x0B80 <= codepoint <= 0x0BFF or  # Tamil
            0x0C00 <= codepoint <= 0x0C7F or  # Telugu
            0x0C80 <= codepoint <= 0x0CFF or  # Kannada
            0x0D00 <= codepoint <= 0x0D7F     # Malayalam
        ):
            clean.append(char)
            continue

        # ✅ Preserve basic Latin and digits
        if (
            0x0020 <= codepoint <= 0x007E or
            0x00A0 <= codepoint <= 0x00FF
        ):
            if any(x in name for x in [
                'BOLD', 'ITALIC', 'SCRIPT', 'FRAKTUR', 'DOUBLE-STRUCK', 'CIRCLED', 'TAG'
            ]):
                continue
            clean.append(char)
            continue

        # ✅ Allow some safe symbols
        if char in (' ', '.', '-', '_', '(', ')', '[', ']'):
            clean.append(char)

    result = ''.join(clean)

    # 🧼 Normalize spacing (convert multiple dashes/underscores/spaces)
    result = re.sub(r'[ \-_]+', ' ', result)

    return result.strip()


# ✅ Clean rename function with junk filter
async def rename_file(file, sender, caption=None):
    delete_words = load_delete_words(sender)
    replacements = load_replacement_words(sender)
    custom_rename_tag = get_user_rename_preference(sender)

    # Separate directory and filename
    directory = os.path.dirname(file)
    filename = os.path.basename(file)
    base_name, ext = os.path.splitext(filename)
    
    if ext and ext.lower() == '.pdf':
        custom_rename_tag = '⚝'
    
    ext = ext if ext and len(ext) <= 6 else ".mp4"
    original_base = base_name

    # Use caption if filename is empty/generic
    if not original_base.strip() or original_base.lower() in ['untitled', 'noname', 'video', 'image']:
        if caption:
            # Take first 50 words of caption as filename
            words = caption.split()[:50]
            base_name = ' '.join(words)
        else:
            # Fallback to timestamp if no caption
            base_name = f"file_{int(time.time())}"
    else:
        base_name = original_base

    # Clean the base name
    base_name = os.path.basename(base_name)

    # Clean Chaudhary fancy text first
    base_name = remove_chaudhary_fancy(base_name)

    # Apply text transformations
    # Fully remove all other mentions so that only custom tag is present at the end
    base_name = re.sub(r'@\w+', '', base_name)
    base_name = re.sub(r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*', '', base_name)  # Remove team jnc
    base_name = re.sub(r'(?i)[*_]*team[\s_\-\.]*spay[*_]*', '', base_name) # Remove team spay
    base_name = re.sub(r'(?i)[*_]*let\'?s\s*help[*_]*', '', base_name)  # Remove let's help
    base_name = re.sub(r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?', '', base_name)  # Remove study vault
    for word in delete_words:
        base_name = base_name.replace(word, "")  # Remove banned words
    for word, replace_word in replacements.items():
        base_name = base_name.replace(word, replace_word)  # Apply word replacements

    # Clean Unicode while preserving spaces and basic punctuation
    base_name = strip_unicode_junk(base_name)

    # Final filename assembly
    new_filename = f"{base_name.strip()} {custom_rename_tag}{ext}".strip()
    
    # Ensure filename isn't empty after processing
    if not os.path.splitext(new_filename)[0]:
        new_filename = f"document_{int(time.time())}{ext}"

    new_file_path = os.path.join(directory, new_filename)

    # Perform the rename
    await asyncio.to_thread(os.rename, file, new_file_path)
    return new_file_path


def progress_callback(done, total, user_id):
    # Check if this user already has progress tracking
    if user_id not in user_progress:
        user_progress[user_id] = {
            'previous_done': 0,
            'previous_time': time.time()
        }
    
    # Retrieve the user's tracking data
    user_data = user_progress[user_id]
    
    # Calculate the percentage of progress
    percent = (done / total) * 100
    
    # Format the progress bar
    completed_blocks = int(percent // 10)
    remaining_blocks = 10 - completed_blocks
    progress_bar = "♦" * completed_blocks + "◇" * remaining_blocks
    
    # Convert done and total to MB for easier reading
    done_mb = done / (1024 * 1024)  # Convert bytes to MB
    total_mb = total / (1024 * 1024)
    
    # Calculate the upload speed (in bytes per second)
    speed = done - user_data['previous_done']
    elapsed_time = time.time() - user_data['previous_time']
    
    if elapsed_time > 0:
        speed_bps = speed / elapsed_time  # Speed in bytes per second
        speed_mbps = (speed_bps * 8) / (1024 * 1024)  # Speed in Mbps
    else:
        speed_mbps = 0
    
    # Estimated time remaining (in seconds)
    if speed_bps > 0:
        remaining_time = (total - done) / speed_bps
    else:
        remaining_time = 0
    
    # Convert remaining time to minutes
    remaining_time_min = remaining_time / 60
    
    # Format the final output as needed
    final = (
        f"╭──────────────────╮\n"
        f"│     **__🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ ⚡ Uploader__**       \n"
        f"├──────────\n"
        f"│ {progress_bar}\n\n"
        f"│ **__Progress:__** {percent:.2f}%\n"
        f"│ **__Done:__** {done_mb:.2f} MB / {total_mb:.2f} MB\n"
        f"│ **__Speed:__** {speed_mbps:.2f} Mbps\n"
        f"│ **__ETA:__** {remaining_time_min:.2f} min\n"
        f"╰──────────────────╯\n\n"
        f"**__Pwrd by CHOSEN ONE ⚝__**"
    )
    
    # Update tracking variables for the user
    user_data['previous_done'] = done
    user_data['previous_time'] = time.time()
    
    return final


def dl_progress_callback(done, total, user_id):
    # Check if this user already has progress tracking
    if user_id not in user_progress:
        user_progress[user_id] = {
            'previous_done': 0,
            'previous_time': time.time()
        }
    
    # Retrieve the user's tracking data
    user_data = user_progress[user_id]
    
    # Calculate the percentage of progress
    percent = (done / total) * 100
    
    # Format the progress bar
    completed_blocks = int(percent // 10)
    remaining_blocks = 10 - completed_blocks
    progress_bar = "♦" * completed_blocks + "◇" * remaining_blocks
    
    # Convert done and total to MB for easier reading
    done_mb = done / (1024 * 1024)  # Convert bytes to MB
    total_mb = total / (1024 * 1024)
    
    # Calculate the upload speed (in bytes per second)
    speed = done - user_data['previous_done']
    elapsed_time = time.time() - user_data['previous_time']
    
    if elapsed_time > 0:
        speed_bps = speed / elapsed_time  # Speed in bytes per second
        speed_mbps = (speed_bps * 8) / (1024 * 1024)  # Speed in Mbps
    else:
        speed_mbps = 0
    
    # Estimated time remaining (in seconds)
    if speed_bps > 0:
        remaining_time = (total - done) / speed_bps
    else:
        remaining_time = 0
    
    # Convert remaining time to minutes
    remaining_time_min = remaining_time / 60
    
    # Format the final output as needed
    final = (
        f"╭──────────────────╮\n"
        f"│     **__🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ ⚡ Downloader__**       \n"
        f"├──────────\n"
        f"│ {progress_bar}\n\n"
        f"│ **__Progress:__** {percent:.2f}%\n"
        f"│ **__Done:__** {done_mb:.2f} MB / {total_mb:.2f} MB\n"
        f"│ **__Speed:__** {speed_mbps:.2f} Mbps\n"
        f"│ **__ETA:__** {remaining_time_min:.2f} min\n"
        f"╰──────────────────╯\n\n"
        f"**__Pwrd by CHOSEN ONE ⚝__**"
    )
    
    # Update tracking variables for the user
    user_data['previous_done'] = done
    user_data['previous_time'] = time.time()
    
    return final

# split function .... ?( to handle gareeb bot coder jo string n lga paaye)

async def split_and_upload_file(app, sender, target_chat_id, file_path, caption, topic_id, thumb=None, source_topic_id=None):
    if not os.path.exists(file_path):
        await app.send_message(sender, "❌ File not found!")
        return

    if not thumb:
        thumb = thumbnail(sender)

    file_size = os.path.getsize(file_path)
    start = await app.send_message(sender, f"ℹ️ File size: {file_size / (1024 * 1024):.2f} MB")
    PART_SIZE =  1.9 * 1024 * 1024 * 1024

    part_number = 0
    with open(file_path, "rb") as f:
        while True:
            # Create part filename
            base_name, file_ext = os.path.splitext(file_path)
            part_file = f"{base_name}.part{str(part_number).zfill(3)}{file_ext}"
            
            # Read and write chunks until part is complete
            with open(part_file, "wb") as part_f:
                bytes_written = 0
                while bytes_written < PART_SIZE:
                    chunk = f.read(min(1024 * 1024, int(PART_SIZE - bytes_written))) # 1MB chunks
                    if not chunk:
                        break
                    part_f.write(chunk)
                    bytes_written += len(chunk)
            
            if os.path.getsize(part_file) == 0:
                os.remove(part_file)
                break


            # Uploading part
            edit = await app.send_message(target_chat_id, f"⬆️ Uploading part {part_number + 1}...")
            part_caption = f"{caption} \n\n**Part : {part_number + 1}**"
            sent_doc = await app.send_document(target_chat_id, document=part_file, caption=part_caption, message_thread_id=topic_id,
                thumb=thumb,
                progress=progress_bar,
                progress_args=("╭─────────────────────╮\n│      **__Pyro Uploader__**\n├─────────────────────", edit, time.time())
            )
            try:
                await sent_doc.copy(LOG_GROUP)
                await check_and_auto_forward(sender, sent_doc, caption=part_caption, source_topic_id=source_topic_id)
            except Exception as fe:
                print(f"Log/Forward split part failed: {fe}")
            await edit.delete()
            os.remove(part_file)  # Cleanup after upload

            part_number += 1

    await start.delete()
    os.remove(file_path)
