# ---------------------------------------------------
# File Name: topic_mirror.py
# Description: Advanced Forum Topic Mirroring module with:
#              - 2-Phase Topic Pre-Creation & Anti-Duplicate Mapping
#              - Persistent Checkpoints (Resume from last pending message)
#              - Save-Restricted Protected Content Bypass
#              - Media Filters & User Settings Integration
#              - @mentions replaced with '⚝' & 'Extracted by' replaced with Stolen Happiness tag
#              - Full Video Metadata, Thumbnails & PDF Watermarking
#              - Live High-Speed Dashboard UI
# ---------------------------------------------------

import os
import re
import time
import math
import asyncio
import random
import unicodedata
from pyrogram import filters, Client, raw, types, enums
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError, ChatAdminRequired, ChannelInvalid, ChannelPrivate
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from toxic import app, get_client, pro_clients
from config import API_ID, API_HASH, OWNER_ID, LOG_GROUP, THUMBNAIL_DIR
from toxic.core.func import chk_user, chk_mirror_user, humanbytes, TimeFormatter, video_metadata, thumbnail, add_pdf_watermark, screenshot, optimize_thumbnail
from toxic.core.mongo import db
from toxic.core.get_func import get_user_branding_tag, format_caption_to_html, clean_surrogates, get_user_spoiler_preference

# In-memory tracking of active topic mirroring jobs
active_mirrors = {}

VIDEO_EXTENSIONS = ['mp4', 'mov', 'avi', 'mkv', 'flv', 'wmv', 'webm', 'mpg', 'mpeg', '3gp', 'ts', 'm4v', 'f4v', 'vob']

# -------------------------------------------------------------
# ADVANCED TEXT & CAPTION CLEANING UTILITIES
# -------------------------------------------------------------

def remove_chaudhary_fancy(text: str) -> str:
    """Normalizes small caps, stylistic Unicode characters, and removes known watermark phrases."""
    if not text:
        return text
    
    translation_map = {
        'ᴀ': 'a', 'ʙ': 'b', 'ᴄ': 'c', 'ᴅ': 'd', 'ᴇ': 'e', 'ғ': 'f', 'ɢ': 'g', 'ʜ': 'h', 
        'ɪ': 'i', 'ᴊ': 'j', 'ᴋ': 'k', 'ʟ': 'l', 'ᴍ': 'm', 'ɴ': 'n', 'ᴏ': 'o', 'ᴘ': 'p', 
        'ǫ': 'q', 'ʀ': 'r', 'ꜱ': 's', 'ᴛ': 't', 'ᴜ': 'u', 'ᴠ': 'v', 'ᴡ': 'w', 'x': 'x', 
        'ʏ': 'y', 'ᴢ': 'z',
        'ꫝ': 'h', 'ຮ': 's', 'ꪮ': 'o', 'ꪎ': 'x', 'ꪗ': 'y',
    }
    
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
        r'toxic',
        r'@Src_pro_bot',
        r'Chosen\s*One',
        r'team[\s_\-\.]*jnc',
        r'team[\s_\-\.]*sp[ay]+',
        r'team[\s_\-\.]*spy[\s_\-\.]*pro',
        r"let'?s\s*help",
        r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?',
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


def get_log_group():
    """Returns the configured log group ID as an integer, or None."""
    if not LOG_GROUP:
        return None
    try:
        return int(LOG_GROUP)
    except Exception:
        return None


def make_caption_bold(text: str) -> str:
    """Ensures all lines in caption are styled in bold, while cleanly preserving blockquotes and YouTube URLs."""
    if not text:
        return text
    lines = text.split('\n')
    bolded_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            bolded_lines.append("")
            continue
        
        # If line is a pure YouTube link, preserve it cleanly
        if re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+$', stripped, re.IGNORECASE):
            bolded_lines.append(stripped)
            continue

        # Preserve blockquotes "> ..." or ">"
        if stripped.startswith(">"):
            content = stripped.lstrip(">").strip()
            if not content:
                bolded_lines.append(">")
                continue
            if re.match(r'^https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+$', content, re.IGNORECASE):
                bolded_lines.append(f"> {content}")
            elif (content.startswith("**") and content.endswith("**")) or (content.startswith("<b>") and content.endswith("</b>")):
                bolded_lines.append(f"> {content}")
            else:
                bolded_lines.append(f"> **{content}**")
        else:
            if (stripped.startswith("**") and stripped.endswith("**")) or (stripped.startswith("<b>") and stripped.endswith("</b>")):
                bolded_lines.append(stripped)
            else:
                bolded_lines.append(f"**{stripped}**")
                
    return '\n'.join(bolded_lines)


def format_media_filename(raw_filename: str, media_type: str = "document") -> str:
    """Formats any media filename: removes all @mentions, stylizes brackets to 〘〙, cleans promo tags, and adds ⚝ before extension."""
    if not raw_filename:
        raw_filename = "document.pdf" if media_type == "document" else "video.mp4"
    
    # 1. Clean surrogates & Chaudhary fancy text
    clean = clean_surrogates(str(raw_filename))
    clean = remove_chaudhary_fancy(clean)
    
    # 2. Remove ALL @usernames / @channels
    clean = re.sub(r'@\w+', '', clean)
    
    # 3. Clean promoter phrases
    unwanted_phrases = [
        r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*sp[ay]+[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*spy[\s_\-\.]*pro[*_]*',
        r"(?i)[*_]*let\'?s\s*help[*_]*",
        r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?',
        r'(?i)toxic',
        r'(?i)chosen\s*one',
        r'(?i)(Extracted|Downloaded|Download|Uploaded|Upload|Forwarded)[\s_]*By[\s_:➤>–\-]*',
        r'(?i)powered\s*by[\s_:➤>–\-]*',
        r'https?://\S+|t\.me/\S+',
    ]
    for phrase in unwanted_phrases:
        clean = re.sub(phrase, '', clean)
        
    # 4. Stylize brackets: () -> 〘〙, [] -> 〘〙, {} -> 〘〙
    clean = re.sub(r'[({[]', '〘', clean)
    clean = re.sub(r'[)}\]]', '〙', clean)
    
    # 5. Extract extension
    base_name, ext = os.path.splitext(clean)
    if not ext:
        ext = '.pdf' if media_type == 'document' else '.mp4'
        
    # 6. If PDF / document, replace doc emojis with 📙 and ensure starts with 📙
    if ext.lower() in ['.pdf', '.docs', '.doc', '.epub'] or media_type == 'document':
        base_name = re.sub(r'[📕📗📘📓📔📒📄📃📁📂📜📑🔴🔺🔹▪️▫️▶️]+', '📙', base_name)
        base_name = re.sub(r'[\s⚝⛥\*]+$', '', base_name).strip()
        if not base_name.startswith('📙'):
            base_name = f"📙 {base_name}".strip()
    else:
        base_name = re.sub(r'[\s⚝⛥\*]+$', '', base_name).strip()

    # 7. Clean extra spaces/dashes
    base_name = re.sub(r'[ \t\-_]+', ' ', base_name).strip()
    
    return f"{base_name} ⚝{ext}".strip()


format_document_filename = format_media_filename


async def clean_and_brand_caption(user_id: int, original_caption: str) -> str:
    """
    Cleans caption according to user settings:
    - Preserves YouTube links
    - Preserves existing blockquotes from source
    - Replaces @mentions with '⚝'
    - Stylizes brackets () [] {} to 〘〙
    - Replaces document emojis with 📙
    - Replaces 'Extracted by' / 'Downloaded by' with user's branding tag
    - Applies bold formatting across all caption lines
    """
    user_data = await db.get_data(user_id) or {}
    
    # Check if raw caption preference is ON
    if user_data.get("keep_original_caption", False):
        return original_caption or ""

    # Get active branding tag (Default: '🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝')
    branding_tag = get_user_branding_tag(user_id) or "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝"

    text = original_caption or ""
    if not text:
        custom_cap = user_data.get("caption")
        return custom_cap if custom_cap else f"> **{branding_tag}**"

    # 1. Clean Chaudhary & fancy characters
    text = remove_chaudhary_fancy(text)

    # 2. Stylize default brackets: () -> 〘〙, [] -> 〘〙, {} -> 〘〙
    text = re.sub(r'[({[]', '〘', text)
    text = re.sub(r'[)}\]]', '〙', text)

    # 3. Replace document/book emojis with 📙
    text = re.sub(r'[📕📗📘📓📔📒📄📃📁📂📜📑🔴🔺🔹▪️▫️▶️]+', '📙', text)

    # 4. Replace any @mentions (@username, @channel) with ⚝
    text = re.sub(r'@\w+', '⚝', text)

    # 5. Remove known other bot tags & promotional signatures
    other_tags = [
        "➪ @PDF_X9 🦋 ❞", "@PDF_X9", "➪ @PDF_X9 🦋",
        "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝", "⚝ 𝗝𝘂𝘀𝘁 𝗙ꪮ𝗿 𝗬ꪮ𝘂...💗",
        "⛤ Just For You...💗", "Just For You...💗",
    ]
    for tag in other_tags:
        text = text.replace(tag, '')

    # 6. Remove any extraction/download lines including leading arrows/bullets
    extraction_pattern = r'(?im)^[ \t\-_—>➤➢•*|~:]*(?:Extracted|Downloaded|Download|Uploaded|Upload|Forwarded|Powered|Saved|Managed|Source|Credit|Credits)[\s_]*By[\s_:➤>–\-]*[^\n]*$'
    text = re.sub(extraction_pattern, '', text)
    text = re.sub(r'(?im)^[ \t\-_—>➤➢•*|~:]*(?:powered\s*by|bot:|via\s*⚝)[^\n]*$', '', text)

    # 7. Remove other unwanted promoter phrases
    unwanted_phrases = [
        r'(?i)[*_]*team[\s_\-\.]*jnc[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*sp[ay]+[*_]*',
        r'(?i)[*_]*team[\s_\-\.]*spy[\s_\-\.]*pro[*_]*',
        r"(?i)[*_]*let'?s\s*help[*_]*",
        r'✧\s*𝚃𝙷𝙴\s*𝚂𝚃𝚄𝙳𝚈\s*𝚅𝙰𝚄𝙻𝚃\s*✧\s*🏝️?',
    ]
    for phrase in unwanted_phrases:
        text = re.sub(phrase, '', text)

    # 8. Remove any trailing lines with arrows/bullets that only contain junk or leftover tags
    text = re.sub(r'(?im)^[ \t\-_—>➤➢•*|~:]*(?:⚝|⛤|🖤|🦋|\s)*$', '', text)

    # 9. Apply user custom clean words & text replacements from database
    clean_words = user_data.get("clean_words") or []
    for word in clean_words:
        if word:
            text = text.replace(word, "")

    to_replace = user_data.get("to_replace")
    replace_txt = user_data.get("replace_txt")
    if to_replace and replace_txt:
        text = text.replace(to_replace, replace_txt)

    # 10. Clean whitespace & multiple empty lines
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    # 11. Apply custom template caption if configured
    custom_cap = user_data.get("caption")
    if custom_cap:
        text = f"{custom_cap}\n\n{text}".strip()
    else:
        # Ensure branding tag is present at the bottom
        if branding_tag not in text:
            text = f"{text}\n\n> **{branding_tag}**".strip()

    # 12. Clean any stray leading arrows before blockquote markers
    text = re.sub(r'(?m)^[ \t\-_—>➤➢•*|~:]*>\s*', '> ', text)
    
    # 13. Apply bold styling to all caption lines while preserving blockquotes
    text = make_caption_bold(text)
    return text.strip()


def is_media_type_enabled(user_data: dict, media_type: str) -> bool:
    """Checks if the user has enabled or disabled this specific media filter in /settings."""
    filters_data = user_data.get("filters", {})
    return filters_data.get(media_type, True)


def parse_source_link(link: str):
    """Parses various Telegram message link formats."""
    if not link:
        return None, None, None
    try:
        clean_link = link.strip()
        if "tg://openmessage" in clean_link:
            chat_match = re.search(r'chat_id=(-?\d+)', clean_link)
            msg_match = re.search(r'message_id=(\d+)', clean_link)
            topic_match = re.search(r'topic_id=(\d+)', clean_link)
            chat_id = int(chat_match.group(1)) if chat_match else None
            msg_id = int(msg_match.group(1)) if msg_match else None
            topic_id = int(topic_match.group(1)) if topic_match else None
            return chat_id, topic_id, msg_id

        clean_link = re.sub(r'https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', clean_link)
        parts = [p for p in clean_link.split('/') if p]
        if not parts:
            return None, None, None

        if parts[0] == 'c':
            if len(parts) >= 4:
                return int("-100" + parts[1]), int(parts[2]), int(parts[3])
            elif len(parts) == 3:
                return int("-100" + parts[1]), None, int(parts[2])
        else:
            if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                return parts[0], int(parts[1]), int(parts[2])
            elif len(parts) == 2 and parts[1].isdigit():
                return parts[0], None, int(parts[1])
    except Exception as e:
        print(f"[TopicMirror] Error parsing source link '{link}': {e}")
    return None, None, None


def parse_topic_and_post_link(link: str):
    """
    Parses a Telegram link (topic link, post link, channel post link, or tg://openmessage)
    and returns a tuple: (chat_id, topic_id, post_id)
    """
    if not link:
        return None, None, None
    try:
        clean_link = link.strip()
        if "tg://openmessage" in clean_link:
            chat_match = re.search(r'chat_id=(-?\d+)', clean_link)
            topic_match = re.search(r'topic_id=(\d+)', clean_link)
            msg_match = re.search(r'message_id=(\d+)', clean_link)
            chat_id = int(chat_match.group(1)) if chat_match else None
            topic_id = int(topic_match.group(1)) if topic_match else None
            post_id = int(msg_match.group(1)) if msg_match else None
            return chat_id, topic_id, post_id

        clean_link = re.sub(r'https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', clean_link)
        clean_link = clean_link.split('?')[0].rstrip('/')
        parts = [p for p in clean_link.split('/') if p]
        if not parts:
            return None, None, None

        if parts[0] in ('c', 'b'):
            chat_id = int("-100" + parts[1])
            if len(parts) >= 4:
                # e.g., t.me/c/1234567890/15/500 -> (chat_id, topic_id=15, post_id=500)
                return chat_id, int(parts[2]), int(parts[3])
            elif len(parts) == 3:
                # e.g., t.me/c/1234567890/500 -> (chat_id, topic_id=500, post_id=500)
                val = int(parts[2])
                return chat_id, val, val
            elif len(parts) == 2:
                return chat_id, None, None
        else:
            chat_id = parts[0]
            if chat_id.isdigit():
                chat_id = int("-100" + chat_id)
            if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                return chat_id, int(parts[1]), int(parts[2])
            elif len(parts) == 2 and parts[1].isdigit():
                val = int(parts[1])
                return chat_id, val, val
            elif len(parts) == 1:
                return chat_id, None, None
    except Exception as e:
        print(f"[TopicMirror] parse_topic_and_post_link error: {e}")
    return None, None, None


def parse_topic_link(link: str):
    chat_id, topic_id, post_id = parse_topic_and_post_link(link)
    return chat_id, topic_id


DIAMOND_EMOJI_ID = 5312389333909511107

def clean_topic_title(title: str) -> str:
    """Cleans topic title by removing leading/trailing decorative emoji prefixes or clutter, preserving the pure title text."""
    if not title:
        return "Topic"
    clean = str(title).strip()
    clean = re.sub(r'^[💎🔹🔷⚡📁📂📌📍🔸💠✦★☆•\s\-\.\:\?\!]+', '', clean).strip()
    clean = re.sub(r'[\s\-\.\:\?\!•]+$', '', clean).strip()
    return clean or str(title).strip() or "Topic"

format_topic_title_with_diamond = clean_topic_title


async def set_topic_diamond_icon(userbot, app, tgt_chat_id: int, tgt_topic_id: int, title: str):
    """
    Sets the custom 💎 diamond emoji icon (5312389333909511107) on a target forum topic.
    Silently fails — icon update is best-effort only.
    """
    if not tgt_chat_id or not tgt_topic_id or tgt_topic_id == 1:
        return False

    clean_title = clean_topic_title(title)
    clients_to_try = []
    if app:
        clients_to_try.append(app)
    if userbot and userbot not in clients_to_try:
        clients_to_try.append(userbot)

    for client in clients_to_try:
        try:
            peer = await client.resolve_peer(tgt_chat_id)
            await client.invoke(raw.functions.messages.EditForumTopic(
                peer=peer,
                topic_id=tgt_topic_id,
                title=clean_title,
                icon_emoji_id=DIAMOND_EMOJI_ID
            ))
            return True
        except Exception:
            pass
    return False





def extract_caption_content_ids(text: str) -> set:
    """
    Extracts standardized numeric content IDs from message caption text
    (e.g., PDF ID: 123, Video ID: 456, Lecture ID: 789, [ID: 101], ID: 55).
    """
    if not text:
        return set()
    patterns = [
        r'(?i)(?:pdf|video|doc|lecture|file|item|content|msg)[\s_]*id[\s_]*[:\-#]?[\s_]*(\d+)',
        r'(?i)id[\s_]*[:\-#][\s_]*(\d+)',
        r'\[(?:ID|id)[\s:]*(\d+)\]',
        r'\((?:ID|id)[\s:]*(\d+)\)'
    ]
    extracted_ids = set()
    for pattern in patterns:
        for match in re.finditer(pattern, str(text)):
            try:
                extracted_ids.add(int(match.group(1)))
            except Exception:
                pass
    return extracted_ids


async def scan_target_topic_content_ids(app, userbot, tgt_chat_id: int, tgt_topic_id: int, max_limit: int = 1500) -> set:
    """
    Scans existing target topic messages to extract all already-synced caption content IDs
    (e.g., PDF ID, Video ID, etc.) for robust deduplication & seamless continuation.
    """
    synced_ids = set()
    if not tgt_chat_id or not tgt_topic_id:
        return synced_ids

    clients_to_try = []
    if app:
        clients_to_try.append(app)
    if userbot and userbot not in clients_to_try:
        clients_to_try.append(userbot)

    for client in clients_to_try:
        try:
            if tgt_topic_id and tgt_topic_id != 1:
                async for m in client.get_discussion_replies(tgt_chat_id, tgt_topic_id, limit=max_limit):
                    cap = (m.caption or m.text or "") if m else ""
                    if cap:
                        c_ids = extract_caption_content_ids(cap)
                        synced_ids.update(c_ids)
            else:
                async for m in client.get_chat_history(tgt_chat_id, limit=max_limit):
                    m_thread = getattr(m, "message_thread_id", None)
                    reply_to = getattr(m, "reply_to_message_id", None)
                    if m_thread in (None, 1) and (not reply_to or reply_to == 1):
                        cap = (m.caption or m.text or "") if m else ""
                        if cap:
                            c_ids = extract_caption_content_ids(cap)
                            synced_ids.update(c_ids)
            if synced_ids:
                break
        except Exception as err:
            print(f"[TopicMirror] scan_target_topic_content_ids notice for {tgt_topic_id}: {err}")

    return synced_ids




userbot_sessions = {} # user_id -> Client instance


async def get_working_userbot(user_id: int):
    """Returns a cached/reusable authenticated Pyrogram Client for the user session or pool client."""
    user_data = await db.get_data(user_id)
    user_session = user_data.get("session") if user_data else None

    if user_session:
        # Reuse existing cached userbot client if available
        existing_ub = userbot_sessions.get(user_id)
        if existing_ub:
            try:
                if getattr(existing_ub, "is_connected", False):
                    return existing_ub, False
                else:
                    await existing_ub.start()
                    return existing_ub, False
            except Exception as re_err:
                print(f"[TopicMirror] Cached userbot reconnect notice: {re_err}")
                userbot_sessions.pop(user_id, None)

        try:
            ub = Client(
                f"ub_tm_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=user_session,
                no_updates=True,
                max_concurrent_transmissions=128
            )
            await ub.start()
            userbot_sessions[user_id] = ub
            return ub, False
        except Exception as e:
            print(f"[TopicMirror] User session client start failed: {e}")

    client = get_client()
    if client and client.is_connected:
        return client, False

    if pro_clients:
        for c in pro_clients:
            if c.is_connected:
                return c, False

    return None, False



async def ensure_userbot_connected(userbot):
    """Ensures userbot client connection is active during continuous mirroring."""
    if userbot:
        try:
            if not getattr(userbot, "is_connected", False):
                print("[TopicMirror] Userbot disconnected. Attempting auto-reconnect...")
                await userbot.start()
                print("[TopicMirror] ✅ Userbot reconnected successfully!")
        except Exception as e:
            print(f"[TopicMirror] ensure_userbot_connected notice: {e}")


def normalize_topic_title(title: str) -> str:

    """Normalizes topic title for robust matching across spaces, casing, emojis and punctuation."""
    if not title:
        return ""
    clean = unicodedata.normalize('NFKD', str(title)).lower()
    clean = re.sub(r'[\s_\-\.\:\(\)\[\]\/\#\*\+\,\!\?\'\"]+', ' ', clean).strip()
    return clean


def alphanumeric_topic_title(title: str) -> str:
    """Extracts purely letters and numbers (including unicode scripts) for fail-safe topic matching."""
    if not title:
        return ""
    return re.sub(r'[^\w]+', '', str(title), flags=re.UNICODE).lower()


def match_existing_target_topic(st_title: str, target_topics_by_title: dict) -> int:
    """Matches a source topic title against existing target topics using exact & clean/normalized title matching."""
    if not st_title or not target_topics_by_title:
        return None

    clean_t = clean_topic_title(st_title)
    variants = [
        st_title.strip().lower(),
        clean_t.strip().lower(),
        normalize_topic_title(st_title),
        normalize_topic_title(clean_t),
        alphanumeric_topic_title(st_title),
        alphanumeric_topic_title(clean_t)
    ]

    for var in variants:
        if var and var in target_topics_by_title:
            return target_topics_by_title[var]

    return None


async def get_highest_topic_checkpoint(src_chat_id: int, src_topic_id: int, tgt_chat_id: int = None, current_saved_checkpoint: int = 0) -> int:
    """
    Finds the highest last_msg_id checkpoint for a source topic specifically for this target chat ID.
    If tgt_chat_id is provided, only searches within that specific target chat's session to ensure
    each target group/channel maintains its own independent checkpoint.
    """
    highest = current_saved_checkpoint
    try:
        from toxic.core.mongo.db import mirror_db
        query = {"src_chat_id": int(src_chat_id)}
        if tgt_chat_id is not None:
            query["tgt_chat_id"] = int(tgt_chat_id)
        async for doc in mirror_db.find(query):
            topics = doc.get("topics", {})
            st_info = topics.get(str(src_topic_id), {})
            last_id = st_info.get("last_msg_id", 0)
            if last_id > highest:
                highest = last_id
    except Exception as err:
        print(f"[TopicMirror] Checkpoint lookup error: {err}")
    return highest


def get_msg_size(msg) -> int:
    """Safely calculates the payload size of a Telegram message in bytes."""
    if not msg:
        return 0
    try:
        if msg.video and getattr(msg.video, "file_size", None):
            return int(msg.video.file_size)
        if msg.document and getattr(msg.document, "file_size", None):
            return int(msg.document.file_size)
        if msg.audio and getattr(msg.audio, "file_size", None):
            return int(msg.audio.file_size)
        if msg.photo and getattr(msg.photo, "file_size", None):
            return int(msg.photo.file_size)
        if msg.voice and getattr(msg.voice, "file_size", None):
            return int(msg.voice.file_size)
        if msg.text:
            return len(msg.text.encode('utf-8'))
        if msg.caption:
            return len(msg.caption.encode('utf-8'))
    except Exception:
        pass
    return 0


def get_mirror_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Generates the interactive control keyboard with Skip Topic and Cancel Mirror."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏭ Skip Topic", callback_data=f"tmirror_skip_{user_id}"),
            InlineKeyboardButton("🛑 Cancel Mirror", callback_data=f"tmirror_cancel_{user_id}")
        ]
    ])


def _register_topic(topics_by_title: dict, topics_by_id: dict, title: str, tid: int):
    """Registers a topic into both lookup dicts under ALL title variants to prevent any future duplicate creation."""
    if not title or not tid:
        return
    clean_t = clean_topic_title(title)
    for var in [
        title.strip().lower(),
        clean_t.strip().lower(),
        normalize_topic_title(title),
        normalize_topic_title(clean_t),
        alphanumeric_topic_title(title),
        alphanumeric_topic_title(clean_t),
    ]:
        if var:
            topics_by_title[var] = tid
    if topics_by_id is not None:
        topics_by_id[tid] = title


async def search_target_topic_by_rpc(userbot, app, tgt_chat_id: int, title_query: str) -> int:
    """
    Directly queries Telegram servers via GetForumTopics RPC search filter (q=title_query).
    Returns target topic ID if an existing topic with matching title is found on Telegram servers.
    """
    if not title_query or len(str(title_query).strip()) < 1:
        return None
    clean_q = clean_topic_title(title_query).strip()
    clients_to_try = []
    if app:
        clients_to_try.append(app)
    if userbot and userbot not in clients_to_try:
        clients_to_try.append(userbot)

    query_terms = [t for t in [clean_q, title_query.strip(), clean_q[:20].strip(), title_query[:20].strip()] if t]
    for client in clients_to_try:
        try:
            peer = await client.resolve_peer(tgt_chat_id)
            for q_term in query_terms:
                res = await client.invoke(raw.functions.messages.GetForumTopics(
                    peer=peer,
                    q=q_term,
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=50
                ))
                topics = getattr(res, "topics", [])
                for t in topics:
                    tid = getattr(t, "id", None)
                    t_title = getattr(t, "title", "") or ""
                    if tid and t_title:
                        single_dict = {}
                        _register_topic(single_dict, {}, t_title, tid)
                        if match_existing_target_topic(title_query, single_dict) or match_existing_target_topic(clean_q, single_dict):
                            return tid
        except Exception:
            pass
    return None


async def get_all_target_forum_topics(userbot, app, tgt_chat_id):
    """
    Scans ALL existing forum topics in target supergroup using raw RPC GetForumTopics with pagination.
    Returns: (topics_by_normalized_title, topics_by_id)
    """
    topics_by_norm_title = {}
    topics_by_id = {}

    clients_to_try = []
    if app:
        clients_to_try.append(app)
    if userbot and userbot not in clients_to_try:
        clients_to_try.append(userbot)

    for client in clients_to_try:
        try:
            peer = await client.resolve_peer(tgt_chat_id)
            offset_date = 0
            offset_id = 0
            offset_topic = 0
            seen_topic_ids = set()

            while True:
                res = await client.invoke(raw.functions.messages.GetForumTopics(
                    peer=peer,
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_topic=offset_topic,
                    limit=100
                ))
                topics = getattr(res, "topics", [])
                if not topics:
                    break

                new_count = 0
                for t in topics:
                    tid = getattr(t, "id", None)
                    if not tid or tid in seen_topic_ids:
                        continue
                    seen_topic_ids.add(tid)
                    new_count += 1
                    t_title = getattr(t, "title", "") or ""

                    _register_topic(topics_by_norm_title, topics_by_id, t_title, tid)

                    offset_date = getattr(t, "date", offset_date)
                    top_msg = getattr(t, "top_message", 0)
                    offset_id = top_msg if top_msg else tid
                    offset_topic = tid

                if new_count == 0:
                    break
        except Exception as scan_err:
            print(f"[TopicMirror] get_all_target_forum_topics scan notice: {scan_err}")

        if topics_by_norm_title:
            break

    return topics_by_norm_title, topics_by_id


async def get_all_source_forum_topics(userbot, src_chat_id: int):
    """
    Scans ALL forum topics from the source group using raw RPC GetForumTopics with pagination.
    Falls back to deep history scanning if needed.
    Returns: list of dicts [{"id": tid, "title": title, "icon_color": ..., "icon_emoji_id": ...}]
    """
    source_topics = []
    seen_ids = set()

    # 1. Primary Strategy: Raw RPC GetForumTopics with pagination
    try:
        peer = await userbot.resolve_peer(src_chat_id)
        offset_date = 0
        offset_id = 0
        offset_topic = 0
        while True:
            res = await userbot.invoke(raw.functions.messages.GetForumTopics(
                peer=peer,
                offset_date=offset_date,
                offset_id=offset_id,
                offset_topic=offset_topic,
                limit=100
            ))
            topics_list = getattr(res, "topics", [])
            if not topics_list:
                break
            new_found = 0
            for t in topics_list:
                tid = getattr(t, "id", None)
                if not tid or tid in seen_ids:
                    continue
                seen_ids.add(tid)
                new_found += 1
                source_topics.append({
                    "id": tid,
                    "title": getattr(t, "title", f"Topic {tid}") or f"Topic {tid}",
                    "icon_color": getattr(t, "icon_color", None),
                    "icon_emoji_id": getattr(t, "icon_emoji_id", None)
                })
                offset_date = getattr(t, "date", offset_date)
                top_msg = getattr(t, "top_message", 0)
                offset_id = top_msg if top_msg else tid
                offset_topic = tid
            if new_found == 0:
                break
        if source_topics:
            print(f"[TopicMirror] ✅ Discovered {len(source_topics)} source topics via raw RPC GetForumTopics")
    except Exception as rpc_err:
        print(f"[TopicMirror] Raw RPC GetForumTopics source scan notice: {rpc_err}")

    # 2. Fallback: Deep chat history topic discovery if RPC failed or returned nothing
    if not source_topics:
        discovered_tids = set()
        try:
            async for m in userbot.get_chat_history(src_chat_id, limit=600):
                if not m:
                    continue
                m_thread = getattr(m, "message_thread_id", None)
                reply_to = getattr(m, "reply_to_message_id", None)
                reply_top_id = getattr(getattr(m, "reply_to_message", None), "reply_to_top_id", None)
                for tid in (m_thread, reply_to, reply_top_id):
                    if tid and isinstance(tid, int) and tid > 1 and tid not in seen_ids:
                        discovered_tids.add(tid)

            for tid in sorted(discovered_tids):
                t_title = f"Topic {tid}"
                try:
                    async for rep in userbot.get_discussion_replies(src_chat_id, tid, limit=3):
                        if getattr(rep, "forum_topic_created", None) and getattr(rep.forum_topic_created, "title", None):
                            t_title = rep.forum_topic_created.title
                            break
                except Exception:
                    pass
                seen_ids.add(tid)
                source_topics.append({"id": tid, "title": t_title, "icon_color": None, "icon_emoji_id": None})
        except Exception as hist_err:
            print(f"[TopicMirror] Deep History Topic Discovery notice: {hist_err}")

    return source_topics



async def fetch_all_messages_for_topic(userbot, src_chat_id, topic_id: int, min_msg_id: int = 0, max_limit: int = 4000):
    """
    Fetches all pending messages for a specific forum topic up to max_limit (default 4000).
    Returns messages sorted oldest→newest (ascending by id).
    Only messages strictly > min_msg_id are returned (checkpoint resume).
    Guarantees messages belong ONLY to this topic — zero cross-topic leakage.
    """
    collected_messages = []
    seen_ids = set()

    # ─── Strategy 1: get_discussion_replies (Pyrogram high-level, most accurate) ───
    if topic_id and topic_id != 1:
        try:
            async for m in userbot.get_discussion_replies(src_chat_id, topic_id, limit=max_limit):
                if not m or m.id in seen_ids:
                    continue
                # Verify thread consistency (never pull messages belonging to another topic)
                m_thread = getattr(m, "message_thread_id", None)
                if m_thread and m_thread != topic_id and m_thread != 1:
                    continue
                seen_ids.add(m.id)
                collected_messages.append(m)
            if collected_messages:
                collected_messages = [m for m in collected_messages if m.id > min_msg_id]
                collected_messages.sort(key=lambda x: x.id)
                return collected_messages
        except Exception as disc_err:
            print(f"[TopicMirror] get_discussion_replies notice for topic {topic_id}: {disc_err}")
            collected_messages.clear()
            seen_ids.clear()

    # ─── Strategy 2: Raw RPC GetReplies (fallback when Strategy 1 fails) ───
    if topic_id and topic_id != 1:
        try:
            peer = await userbot.resolve_peer(src_chat_id)
            offset_id = 0
            while len(collected_messages) < max_limit:
                res = await userbot.invoke(raw.functions.messages.GetReplies(
                    peer=peer,
                    msg_id=topic_id,
                    offset_id=offset_id,
                    offset_date=0,
                    add_offset=0,
                    limit=100,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))
                raw_msgs = getattr(res, "messages", [])
                if not raw_msgs:
                    break
                users_map = {u.id: u for u in getattr(res, "users", [])}
                chats_map = {c.id: c for c in getattr(res, "chats", [])}
                new_found = 0
                for rm in raw_msgs:
                    mid = getattr(rm, "id", None)
                    if not mid or mid in seen_ids:
                        continue
                    try:
                        parsed_m = await types.Message._parse(userbot, rm, users_map, chats_map)
                        if parsed_m:
                            seen_ids.add(mid)
                            collected_messages.append(parsed_m)
                            new_found += 1
                    except Exception:
                        pass
                if new_found == 0 or len(raw_msgs) < 100:
                    break
                offset_id = raw_msgs[-1].id
            if collected_messages:
                collected_messages = [m for m in collected_messages if m.id > min_msg_id]
                collected_messages.sort(key=lambda x: x.id)
                return collected_messages
        except Exception as rpc_err:
            print(f"[TopicMirror] Raw GetReplies notice for topic {topic_id}: {rpc_err}")
            collected_messages.clear()
            seen_ids.clear()

    # ─── Strategy 3: Chat history scan — for General topic or fallback ───
    try:
        topic_msg_ids: set = set()
        all_scanned = []

        async for m in userbot.get_chat_history(src_chat_id, limit=min(max_limit * 2, 8000)):
            if not m:
                continue
            all_scanned.append(m)

            m_thread = getattr(m, "message_thread_id", None)
            reply_to = getattr(m, "reply_to_message_id", None)
            reply_top = None
            rt_msg = getattr(m, "reply_to_message", None)
            if rt_msg:
                reply_top = getattr(rt_msg, "reply_to_top_id", None) or getattr(rt_msg, "message_thread_id", None)

            if topic_id == 1:
                # General topic ONLY: messages with no thread assignment and no thread reply
                if (m_thread in (None, 1)) and (reply_top in (None, 1)) and (reply_to in (None, 1)):
                    topic_msg_ids.add(m.id)
            else:
                # Specific topic thread ONLY:
                if m_thread == topic_id or (m_thread is None and (reply_top == topic_id or reply_to == topic_id or m.id == topic_id)):
                    topic_msg_ids.add(m.id)

        for m in all_scanned:
            if m.id in topic_msg_ids and m.id > min_msg_id and m.id not in seen_ids:
                seen_ids.add(m.id)
                collected_messages.append(m)

    except Exception as scan_err:
        print(f"[TopicMirror] get_chat_history scan notice for topic {topic_id}: {scan_err}")

    # Sort chronologically oldest→newest
    collected_messages.sort(key=lambda x: x.id)
    return collected_messages




def extract_topic_id_from_result(created) -> int:
    if not created:
        return None
    if hasattr(created, "id") and isinstance(created.id, int) and created.id > 0:
        return created.id
    if hasattr(created, "message_thread_id") and isinstance(created.message_thread_id, int) and created.message_thread_id > 0:
        return created.message_thread_id
    if hasattr(created, "top_message_id") and isinstance(created.top_message_id, int) and created.top_message_id > 0:
        return created.top_message_id

    updates = getattr(created, "updates", []) or []
    for upd in updates:
        msg_obj = getattr(upd, "message", None)
        if msg_obj and getattr(msg_obj, "id", None):
            return msg_obj.id
        uid = getattr(upd, "id", None)
        if uid and isinstance(uid, int) and uid > 1:
            return uid
        
    raw_msgs = getattr(created, "messages", []) or []
    for m in raw_msgs:
        if getattr(m, "id", None):
            return m.id

    return None


async def transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id: int):
    """
    Transfers a single message using the fastest available method:
      1. Direct forward_messages (zero-bandwidth, instant — if forward allowed or bot is member)
      2. Server-side copy_message (no download/upload — removes forward tag)
      3. Download → Upload full pipeline (protected/restricted content fallback)
    Checks user media filters and settings. Filters service/empty messages.
    """
    # Instant Cancellation Check
    if user_id in active_mirrors:
        state = active_mirrors[user_id]
        if (isinstance(state, dict) and not state.get("running", True)) or (isinstance(state, bool) and not state):
            return False, "cancelled", None

    # 0. Skip Service, Action, Topic-Created, Pinned & Empty Messages
    if (getattr(msg, "service", False) or 
        getattr(msg, "empty", False) or 
        getattr(msg, "action", None) or 
        getattr(msg, "forum_topic_created", None) or 
        getattr(msg, "pinned_message", None) or 
        (not msg.text and not msg.media and not getattr(msg, 'video', None) and not getattr(msg, 'document', None) and not getattr(msg, 'photo', None) and not getattr(msg, 'audio', None) and not getattr(msg, 'voice', None) and not getattr(msg, 'sticker', None) and not getattr(msg, 'animation', None))):
        return True, "service_skipped", None

    user_data = await db.get_data(user_id) or {}

    # Check Media Filters from Settings
    if msg.video and not is_media_type_enabled(user_data, "video"):
        return False, "skipped_filter", None
    if msg.document and not is_media_type_enabled(user_data, "document"):
        return False, "skipped_filter", None
    if msg.photo and not is_media_type_enabled(user_data, "photo"):
        return False, "skipped_filter", None
    if msg.audio and not is_media_type_enabled(user_data, "audio"):
        return False, "skipped_filter", None
    if msg.sticker and not is_media_type_enabled(user_data, "sticker"):
        return False, "skipped_filter", None
    if msg.text and not is_media_type_enabled(user_data, "text"):
        return False, "skipped_filter", None

    # ── Helper: log copy to LOG_GROUP ──────────────────────────────
    async def _log_msg(sent_m):
        log_chat = get_log_group()
        if log_chat and sent_m:
            try:
                await (sent_m[0] if isinstance(sent_m, list) else sent_m).copy(log_chat)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────
    # METHOD 1: Direct forward_messages (zero-bandwidth, instant)
    # Works when: bot/userbot is admin/member of source and target
    # ─────────────────────────────────────────────────────────────
    fwd_kwargs = {"chat_id": tgt_chat_id, "from_chat_id": src_chat_id, "message_ids": msg.id}
    if tgt_topic_id:
        fwd_kwargs["message_thread_id"] = tgt_topic_id

    for fwd_client in [app, userbot]:
        try:
            fwd_result = await fwd_client.forward_messages(**fwd_kwargs)
            sent_list = fwd_result if isinstance(fwd_result, list) else [fwd_result]
            sent_id = sent_list[0].id if sent_list and hasattr(sent_list[0], 'id') else None
            if sent_id:
                await _log_msg(sent_list[0])
                return True, "forwarded", sent_id
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
        except Exception as fwd_err:
            print(f"[Transfer] Direct forward notice ({fwd_client.__class__.__name__}): {fwd_err}")
            continue  # Try next client (userbot / app)

    # ─────────────────────────────────────────────────────────────
    # METHOD 2: Server-side copy (no download/upload, removes forward header)
    # Works when forward is restricted but bot/userbot has read access
    # ─────────────────────────────────────────────────────────────
    for copy_client in [app, userbot]:
        try:
            copied_m = await copy_client.copy_message(
                chat_id=tgt_chat_id,
                from_chat_id=src_chat_id,
                message_id=msg.id,
                reply_to_message_id=tgt_topic_id
            )
            sent_id = getattr(copied_m, 'id', None)
            if sent_id:
                await _log_msg(copied_m)
                return True, "copied", sent_id
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)
        except Exception as copy_err:
            print(f"[Transfer] Server copy notice ({copy_client.__class__.__name__}): {copy_err}")
            continue  # Try next client

    # ─────────────────────────────────────────────────────────────
    # METHOD 3: Download via userbot → Upload (protected/restricted content)
    # Full pipeline: download, thumbnail, watermark, caption clean, upload
    # ─────────────────────────────────────────────────────────────
    if msg.text:
        try:
            raw_text = msg.text.markdown if hasattr(msg.text, 'markdown') and msg.text.markdown else (msg.text or "")
            final_text = await clean_and_brand_caption(user_id, raw_text)
            html_text = format_caption_to_html(final_text) if final_text else None
            sent_txt = await app.send_message(
                chat_id=tgt_chat_id,
                text=html_text if html_text else (final_text or msg.text),
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            sent_id = getattr(sent_txt, 'id', None)
            await _log_msg(sent_txt)
            return True, "text_sent", sent_id
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)
        except Exception as txt_err:
            print(f"[TopicMirror] Failed to send text msg {msg.id}: {txt_err}")
            return False, str(txt_err), None

    # Media download/upload pipeline
    temp_file = None
    auto_thumb_file = None
    try:
        temp_dir = os.path.join("downloads", str(user_id))
        os.makedirs(temp_dir, exist_ok=True)

        # Download media via userbot
        temp_file = await userbot.download_media(
            msg,
            file_name=f"{temp_dir}/"
        )

        if not temp_file or not os.path.isfile(temp_file):
            return False, "Download failed", None

        # Prepare caption with advanced cleaning & branding (retaining source blockquotes)
        orig_cap = msg.caption.markdown if hasattr(msg.caption, 'markdown') and msg.caption.markdown else (msg.caption or "")
        final_caption = await clean_and_brand_caption(user_id, orig_cap)
        caption_html = format_caption_to_html(final_caption) if final_caption else None

        # Check custom thumbnail from settings
        thumb_path = thumbnail(user_id)
        file_extension = str(temp_file).split('.')[-1].lower()

        # If no custom thumbnail, try downloading original thumbnail from source message
        if not thumb_path:
            if msg.video and getattr(msg.video, 'thumbs', None) and len(msg.video.thumbs) > 0:
                try:
                    thumb_path = await userbot.download_media(msg.video.thumbs[0].file_id, file_name=f"{temp_dir}/orig_thumb_{msg.id}.jpg")
                    auto_thumb_file = thumb_path
                except Exception:
                    thumb_path = None
            elif msg.document and getattr(msg.document, 'thumbs', None) and len(msg.document.thumbs) > 0:
                try:
                    thumb_path = await userbot.download_media(msg.document.thumbs[0].file_id, file_name=f"{temp_dir}/orig_thumb_{msg.id}.jpg")
                    auto_thumb_file = thumb_path
                except Exception:
                    thumb_path = None

        sent_media = None
        file_size = os.path.getsize(temp_file)
        if file_size > 1.99 * 1024 * 1024 * 1024:
            from toxic.core.get_func import split_and_upload_file
            await split_and_upload_file(app, user_id, tgt_chat_id, temp_file, final_caption, tgt_topic_id, thumb=thumb_path)
            return True, "split_uploaded", None

        # Video metadata & thumbnail handling
        if msg.video or file_extension in VIDEO_EXTENSIONS:
            # Format and rename video file to remove @mentions and add ⚝ before extension
            raw_filename = (msg.video.file_name if msg.video and msg.video.file_name else os.path.basename(temp_file)) or "video.mp4"
            clean_formatted_name = format_media_filename(raw_filename, media_type="video")
            renamed_path = os.path.join(os.path.dirname(temp_file), clean_formatted_name)
            if renamed_path != temp_file:
                try:
                    if os.path.exists(renamed_path):
                        os.remove(renamed_path)
                    os.rename(temp_file, renamed_path)
                    temp_file = renamed_path
                except Exception as ren_err:
                    print(f"[TopicMirror] Video rename notice: {ren_err}")

            # Extract original dimensions and duration from msg.video if available
            duration = msg.video.duration if (msg.video and msg.video.duration) else 0
            width = msg.video.width if (msg.video and msg.video.width) else 0
            height = msg.video.height if (msg.video and msg.video.height) else 0

            # Fallback to file metadata if missing
            if not duration or not width or not height:
                metadata = video_metadata(temp_file)
                if not duration and metadata.get('duration', 0) > 0:
                    duration = metadata.get('duration', 0)
                if not width and metadata.get('width', 0) > 0:
                    width = metadata.get('width', 0)
                if not height and metadata.get('height', 0) > 0:
                    height = metadata.get('height', 0)

            # Generate screenshot thumbnail if still missing
            if not thumb_path:
                try:
                    thumb_path = await screenshot(temp_file, duration or 10, user_id)
                    auto_thumb_file = thumb_path
                except Exception as ss_err:
                    print(f"[TopicMirror] Screenshot generation error: {ss_err}")
                    thumb_path = None

            if thumb_path and os.path.isfile(thumb_path):
                thumb_path = optimize_thumbnail(thumb_path)

            has_spoiler = get_user_spoiler_preference(user_id)

            sent_media = await app.send_video(
                chat_id=tgt_chat_id,
                video=temp_file,
                caption=caption_html,
                duration=duration if duration > 0 else None,
                width=width if width > 0 else None,
                height=height if height > 0 else None,
                thumb=thumb_path,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML,
                supports_streaming=True,
                has_spoiler=has_spoiler
            )
        elif msg.document or file_extension == 'pdf':
            # Apply PDF watermark if set in user settings
            if file_extension == 'pdf':
                watermark_txt = user_data.get("watermark_text")
                if watermark_txt:
                    temp_file = add_pdf_watermark(temp_file, watermark_txt)

            # Format and rename document file with 📙 prefix and ⚝ before extension
            raw_filename = (msg.document.file_name if msg.document and msg.document.file_name else os.path.basename(temp_file)) or "document.pdf"
            clean_formatted_name = format_media_filename(raw_filename, media_type="document")

            # Rename the downloaded temp file on disk so Pyrogram uploads with the clean name
            renamed_path = os.path.join(os.path.dirname(temp_file), clean_formatted_name)
            if renamed_path != temp_file:
                try:
                    if os.path.exists(renamed_path):
                        os.remove(renamed_path)
                    os.rename(temp_file, renamed_path)
                    temp_file = renamed_path
                except Exception as ren_err:
                    print(f"[TopicMirror] File rename notice: {ren_err}")

            # If no original caption, generate clean blockquote caption with formatted filename & branding
            if not orig_cap:
                branding_tag = get_user_branding_tag(user_id) or "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝"
                final_caption = f"> **{clean_formatted_name}**\n\n> **{branding_tag}**"
                final_caption = make_caption_bold(final_caption)
                caption_html = format_caption_to_html(final_caption)

            if thumb_path and os.path.isfile(thumb_path):
                thumb_path = optimize_thumbnail(thumb_path)

            sent_media = await app.send_document(
                chat_id=tgt_chat_id,
                document=temp_file,
                caption=caption_html,
                thumb=thumb_path,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML
            )
        elif msg.photo:
            has_spoiler = get_user_spoiler_preference(user_id)
            sent_media = await app.send_photo(
                chat_id=tgt_chat_id,
                photo=temp_file,
                caption=caption_html,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML,
                has_spoiler=has_spoiler
            )
        elif msg.audio:
            raw_filename = (msg.audio.file_name if msg.audio and msg.audio.file_name else os.path.basename(temp_file)) or "audio.mp3"
            clean_formatted_name = format_media_filename(raw_filename, media_type="audio")
            renamed_path = os.path.join(os.path.dirname(temp_file), clean_formatted_name)
            if renamed_path != temp_file:
                try:
                    if os.path.exists(renamed_path):
                        os.remove(renamed_path)
                    os.rename(temp_file, renamed_path)
                    temp_file = renamed_path
                except Exception as ren_err:
                    print(f"[TopicMirror] Audio rename notice: {ren_err}")

            clean_performer = re.sub(r'@\w+', '', msg.audio.performer or '').strip() if msg.audio.performer else None
            clean_title = re.sub(r'@\w+', '', msg.audio.title or '').strip() if msg.audio.title else None

            if thumb_path and os.path.isfile(thumb_path):
                thumb_path = optimize_thumbnail(thumb_path)
            sent_media = await app.send_audio(
                chat_id=tgt_chat_id,
                audio=temp_file,
                caption=caption_html,
                duration=msg.audio.duration or 0,
                performer=clean_performer,
                title=clean_title,
                thumb=thumb_path,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML
            )
        elif msg.voice:
            sent_media = await app.send_voice(
                chat_id=tgt_chat_id,
                voice=temp_file,
                caption=caption_html,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML
            )
        elif msg.animation:
            sent_media = await app.send_animation(
                chat_id=tgt_chat_id,
                animation=temp_file,
                caption=caption_html,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML
            )
        elif msg.sticker:
            sent_media = await app.send_sticker(
                chat_id=tgt_chat_id,
                sticker=temp_file,
                reply_to_message_id=tgt_topic_id
            )
        else:
            if thumb_path and os.path.isfile(thumb_path):
                thumb_path = optimize_thumbnail(thumb_path)
            sent_media = await app.send_document(
                chat_id=tgt_chat_id,
                document=temp_file,
                caption=caption_html,
                thumb=thumb_path,
                reply_to_message_id=tgt_topic_id,
                parse_mode=ParseMode.HTML
            )

        # Send copy of uploaded media to LOG_GROUP
        await _log_msg(sent_media)

        sent_id = getattr(sent_media, 'id', None)
        return True, "download_uploaded", sent_id

    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)
    except Exception as dl_up_err:
        print(f"[TopicMirror] Save-Restricted extraction error for msg {msg.id}: {dl_up_err}")
        return False, str(dl_up_err), None

    finally:
        if temp_file and os.path.isfile(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass
        if auto_thumb_file and os.path.isfile(auto_thumb_file):
            try:
                os.remove(auto_thumb_file)
            except Exception:
                pass


def build_mirror_hub_keyboard(user_id: int, saved_sessions: list) -> InlineKeyboardMarkup:
    """Builds interactive inline keyboard of saved mirror sessions."""
    buttons = []
    for s in saved_sessions:
        src_id = s.get("src_chat_id")
        tgt_id = s.get("tgt_chat_id")
        if not src_id or not tgt_id:
            raw_id = s.get("_id", "")
            if "_" in raw_id:
                parts = raw_id.split("_")
                src_id, tgt_id = parts[0], parts[1]
        if not src_id or not tgt_id:
            continue
        
        src_t = (s.get("src_title") or f"{src_id}").strip()
        tgt_t = (s.get("tgt_title") or f"{tgt_id}").strip()
        if len(src_t) > 13:
            src_t = src_t[:11] + ".."
        if len(tgt_t) > 13:
            tgt_t = tgt_t[:11] + ".."
            
        buttons.append([InlineKeyboardButton(f"📁 {src_t} ➔ {tgt_t}", callback_data=f"tm_opt_{src_id}_{tgt_id}")])
        
    buttons.append([
        InlineKeyboardButton("➕ Start Group Mirror", callback_data="tm_new"),
        InlineKeyboardButton("🔗 Link Mirror (Topic ➔ Topic)", callback_data="tm_topiclink")
    ])
    buttons.append([InlineKeyboardButton("🗑️ Clear All Saved Sessions", callback_data="tm_clear")])
    return InlineKeyboardMarkup(buttons)


def build_session_action_keyboard(src_chat_id: int, tgt_chat_id: int, topic_count: int = 0) -> InlineKeyboardMarkup:
    """Builds action options for a selected saved mirror session."""
    topic_btn_text = f"📂 View & Manage Topics ({topic_count})" if topic_count > 0 else "📂 View & Manage Topics"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(topic_btn_text, callback_data=f"tm_topics_{src_chat_id}_{tgt_chat_id}_0")],
        [InlineKeyboardButton("⚡ 𝟭-𝗖𝗹𝗶𝗰𝗸 𝗦𝘆𝗻𝗰 & 𝗨𝗽𝗱𝗮𝘁𝗲", callback_data=f"tm_sync_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("🔎 𝗟𝗶𝘃𝗲 𝗦𝗰𝗮𝗻 & 𝗖𝗼𝗺𝗽𝗮𝗿𝗲", callback_data=f"tm_scan_{src_chat_id}_{tgt_chat_id}")],
        [
            InlineKeyboardButton("🎯 Mirror 1 Topic", callback_data=f"tm_picktopic_{src_chat_id}_{tgt_chat_id}"),
            InlineKeyboardButton("🔄 Re-Upload Topic", callback_data=f"tm_reuploadtopic_{src_chat_id}_{tgt_chat_id}")
        ],
        [InlineKeyboardButton("🔗 Mirror via Topic Links (Link ➔ Link)", callback_data="tm_topiclink")],
        [InlineKeyboardButton("▶️ Continue Mirroring", callback_data=f"tm_res_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("✏️ Modify Target Chat ID", callback_data=f"tm_edittgt_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("🗑️ Delete This Session", callback_data=f"tm_delsess_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("🔙 Back to Sessions Hub", callback_data="tm_hub")]
    ])



async def scan_and_compare_session(user_id: int, src_chat_id: int, tgt_chat_id: int):
    """
    Scans source and target groups, compares total content per topic,
    and returns a clean comparative report with pending message counts.
    """
    userbot, is_temp_userbot = await get_working_userbot(user_id)
    if not userbot:
        return "❌ **No working userbot session!** Please login via `/login` first."

    try:
        # Resolve chat titles
        try:
            src_chat = await userbot.get_chat(src_chat_id)
            src_title = src_chat.title or str(src_chat_id)
        except Exception:
            src_title = str(src_chat_id)

        try:
            tgt_chat = await app.get_chat(tgt_chat_id)
            tgt_title = tgt_chat.title or str(tgt_chat_id)
        except Exception:
            tgt_title = str(tgt_chat_id)

        saved_session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
        saved_topics = saved_session.get("topics", {})

        # Fetch all source topics
        source_topics = await get_all_source_forum_topics(userbot, src_chat_id)
        if not source_topics:
            source_topics = [{"id": 1, "title": "General", "icon_color": None, "icon_emoji_id": None}]

        total_src_msgs = 0
        total_synced_msgs = 0
        total_pending_msgs = 0

        topic_lines = []

        for st in source_topics:
            st_id = st["id"]
            st_title = st["title"].strip()
            
            # Check saved checkpoint in MongoDB (with cross-session failsafe)
            topic_info = saved_topics.get(str(st_id), {})
            last_msg_id = topic_info.get("last_msg_id", 0)
            highest_ckpt = await get_highest_topic_checkpoint(src_chat_id, st_id, tgt_chat_id, last_msg_id)
            if highest_ckpt > last_msg_id:
                last_msg_id = highest_ckpt

            # Rapidly fetch messages for topic
            messages = await fetch_all_messages_for_topic(userbot, src_chat_id, st_id, min_msg_id=0, max_limit=5000)
            
            # Filter non-service messages
            content_msgs = [m for m in messages if not (getattr(m, "service", False) or getattr(m, "empty", False) or getattr(m, "action", None) or getattr(m, "forum_topic_created", None) or getattr(m, "pinned_message", None) or not (m.text or m.media or getattr(m, "document", None) or getattr(m, "video", None) or getattr(m, "photo", None) or getattr(m, "audio", None)))]
            
            t_total = len(content_msgs)
            
            if last_msg_id > 0:
                t_synced = len([m for m in content_msgs if m.id <= last_msg_id])
            else:
                t_synced = 0
                
            t_pending = max(0, t_total - t_synced)

            total_src_msgs += t_total
            total_synced_msgs += t_synced
            total_pending_msgs += t_pending

            if t_pending == 0 and t_total > 0:
                status_str = "🌐 **Complete**"
            elif t_pending > 0:
                status_str = f"⏳ **Pending:** `{t_pending}` msgs"
            else:
                status_str = "ℹ️ **Empty**"

            topic_lines.append(f"• **{st_title}**: Total: `{t_total}` | Synced: `{t_synced}` | {status_str}")

        sync_percent = int((total_synced_msgs / total_src_msgs) * 100) if total_src_msgs > 0 else 100
        bar_blocks = int(sync_percent // 10)
        progress_bar = "▰" * bar_blocks + "▱" * (10 - bar_blocks)

        breakdown_str = "\n".join(topic_lines[:30])
        if len(topic_lines) > 30:
            breakdown_str += f"\n*...and {len(topic_lines) - 30} more topics*"

        report = (
            f"<blockquote><b>🔍 TOPIC MIRROR — LIVE SCAN & COMPARISON REPORT</b></blockquote>\n\n"
            f"📤 **Source:** `{src_title}`\n"
            f"📥 **Target:** `{tgt_title}`\n\n"
            f"<blockquote><b>📊 OVERALL CONTENT SYNC METRICS:</b>\n"
            f"• 📁 <b>Source Topics:</b> <code>{len(source_topics)}</code>\n"
            f"• ✉️ <b>Total Source Messages:</b> <code>{total_src_msgs}</code>\n"
            f"• ✅ <b>Synced in Target:</b> <code>{total_synced_msgs}</code>\n"
            f"• ⏳ <b>Pending / Remaining:</b> <code>{total_pending_msgs}</code>\n"
            f"• 📊 <b>Overall Sync Progress:</b> {progress_bar} <code>{sync_percent}%</code></blockquote>\n\n"
            f"<blockquote><b>📂 TOPIC COMPARISON BREAKDOWN:</b>\n"
            f"{breakdown_str}</blockquote>\n\n"
            f"<i>Click <b>Sync & Update Pending Content</b> below to immediately copy all remaining content!</i>"
        )
        return report

    finally:
        if is_temp_userbot and userbot:
            try:
                await userbot.stop()
            except Exception:
                pass


@app.on_callback_query(filters.regex(r"^tm_scan_(-?\d+)_(-?\d+)$"))
async def scan_session_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the Topic Mirror Plan!", show_alert=True)
        return

    match = re.search(r"^tm_scan_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))

    await query.answer("🔍 Scanning groups and comparing content... Please wait...")
    
    try:
        await query.message.edit_text("🔍 **Scanning Source & Target groups... Comparing message counts per topic...**")
    except Exception:
        pass
    
    report = await scan_and_compare_session(user_id, src_chat_id, tgt_chat_id)
    html_text = format_caption_to_html(report)

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ 𝟭-𝗖𝗹𝗶𝗰𝗸 𝗦𝘆𝗻𝗰 & 𝗨𝗽𝗱𝗮𝘁𝗲", callback_data=f"tm_sync_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("🔎 𝗟𝗶𝘃𝗲 𝗦𝗰𝗮𝗻 & 𝗖𝗼𝗺𝗽𝗮𝗿𝗲", callback_data=f"tm_scan_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("▶️ Continue Mirroring", callback_data=f"tm_res_{src_chat_id}_{tgt_chat_id}")],
        [InlineKeyboardButton("🔙 Back to Sessions Hub", callback_data="tm_hub")]
    ])

    await query.message.edit_text(
        html_text if html_text else report,
        parse_mode=ParseMode.HTML,
        reply_markup=buttons
    )


@app.on_callback_query(filters.regex(r"^tm_sync_(-?\d+)_(-?\d+)$"))
async def sync_session_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the Topic Mirror Plan!", show_alert=True)
        return

    match = re.search(r"^tm_sync_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))

    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ A mirror task is already running!", show_alert=True)
        return

    await query.answer("🔄 Starting Sync & Update process...")
    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=True,
        detected_topic_id=None,
        status_msg=query.message,
        force_sync=True
    )


@app.on_message(filters.command(["cancel_mirror", "cancelmirror"]))
async def cancel_mirror_cmd(_, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    if user_id in active_mirrors:
        if isinstance(active_mirrors[user_id], dict):
            active_mirrors[user_id]["running"] = False
        else:
            active_mirrors[user_id] = False
        await message.reply("🛑 **Cancellation signal sent.** Topic mirror operation will stop shortly.")
    else:
        await message.reply("ℹ️ You have no active topic mirroring process running.")


@app.on_message(filters.command(["skip_topic", "skiptopic"]))
async def skip_topic_cmd(_, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        active_mirrors[user_id]["skip_topic"] = True
        await message.reply("⏭ **Topic skip signal sent.** Moving to the next topic shortly.")
    else:
        await message.reply("ℹ️ No active topic mirroring process in progress to skip.")


@app.on_callback_query(filters.regex(r"^tmirror_cancel_(\d+)$"))
async def cancel_mirror_callback(_, query: CallbackQuery):
    req_uid = int(query.data.split("_")[2])
    user_id = query.from_user.id
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    if user_id == req_uid or str(user_id) in [str(o) for o in owner_list]:
        if req_uid in active_mirrors:
            if isinstance(active_mirrors[req_uid], dict):
                active_mirrors[req_uid]["running"] = False
            else:
                active_mirrors[req_uid] = False
        await query.answer("🛑 Cancelling topic mirror process...", show_alert=True)
    else:
        await query.answer("❌ You are not authorized to cancel this task.", show_alert=True)


@app.on_callback_query(filters.regex(r"^tmirror_skip_(\d+)$"))
async def skip_topic_callback(_, query: CallbackQuery):
    req_uid = int(query.data.split("_")[2])
    user_id = query.from_user.id
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    if user_id == req_uid or str(user_id) in [str(o) for o in owner_list]:
        if req_uid in active_mirrors and isinstance(active_mirrors[req_uid], dict) and active_mirrors[req_uid].get("running"):
            active_mirrors[req_uid]["skip_topic"] = True
            await query.answer("⏭ Skipping current topic... Moving to next topic!", show_alert=True)
        else:
            await query.answer("ℹ️ No active topic is running.", show_alert=True)
    else:
        await query.answer("❌ You are not authorized to skip this topic.", show_alert=True)


@app.on_callback_query(filters.regex(r"^tm_opt_(-?\d+)_(-?\d+)$"))
async def session_options_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the Topic Mirror Plan! Use /plans.", show_alert=True)
        return
    match = re.search(r"^tm_opt_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
    src_title = session.get("src_title") or str(src_chat_id)
    tgt_title = session.get("tgt_title") or str(tgt_chat_id)
    topic_count = len(session.get("topics", {}))
    
    text = (
        f"🎛️ **Mirror Session Options**\n\n"
        f"> 📤 **Source Group:** `{src_title}` (`{src_chat_id}`)\n"
        f"> 📥 **Target Group:** `{tgt_title}` (`{tgt_chat_id}`)\n"
        f"> 📂 **Saved Topic Checkpoints:** `{topic_count}` topic(s) mapped\n\n"
        f"Choose an option below to view/manage individual topics, sync, rename, or continue mirroring:"
    )
    html_text = format_caption_to_html(text)
    await query.message.edit_text(
        html_text if html_text else text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_session_action_keyboard(src_chat_id, tgt_chat_id, topic_count)
    )


def make_topic_link(chat_id: int, topic_id: int) -> str:
    """Generates a direct clickable Telegram link to a topic in a supergroup."""
    cid_str = str(chat_id)
    if cid_str.startswith("-100"):
        cid_clean = cid_str[4:]
    elif cid_str.startswith("-"):
        cid_clean = cid_str[1:]
    else:
        cid_clean = cid_str
    
    tid = topic_id if (topic_id and topic_id > 1) else 1
    return f"https://t.me/c/{cid_clean}/{tid}"


@app.on_callback_query(filters.regex(r"^tm_topics_(-?\d+)_(-?\d+)_(\d+)$"))
async def list_topics_paginated_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
    
    match = re.search(r"^tm_topics_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    page = int(match.group(3))
    
    session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
    topics_dict = session.get("topics", {})
    src_title = session.get("src_title") or str(src_chat_id)
    tgt_title = session.get("tgt_title") or str(tgt_chat_id)
    
    if not topics_dict:
        await query.answer("ℹ️ No topics mapped yet! Run Sync & Update to initialize.", show_alert=True)
        return
        
    topic_items = []
    for s_id_str, info in topics_dict.items():
        try:
            s_id = int(s_id_str)
            t_id = info.get("tgt_topic_id", s_id)
            title = info.get("title", f"Topic {s_id}")
            last_msg = info.get("last_msg_id", 0)
            topic_items.append({"src_id": s_id, "tgt_id": t_id, "title": title, "last_msg": last_msg})
        except Exception:
            pass
            
    topic_items.sort(key=lambda x: x["src_id"])
    
    PAGE_SIZE = 10
    total_topics = len(topic_items)
    total_pages = max(1, math.ceil(total_topics / PAGE_SIZE))
    page = min(max(0, page), total_pages - 1)
    
    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_topics)
    current_page_topics = topic_items[start_idx:end_idx]
    
    keyboard = []
    for t in current_page_topics:
        btn_text = f"📁 {t['title'][:25]}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"tm_topinfo_{src_chat_id}_{tgt_chat_id}_{t['src_id']}")])
        
    # Pagination row
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"tm_topics_{src_chat_id}_{tgt_chat_id}_{page-1}"))
    nav_row.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data=f"tm_topics_{src_chat_id}_{tgt_chat_id}_{page}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"tm_topics_{src_chat_id}_{tgt_chat_id}_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    # Global Action buttons
    keyboard.append([
        InlineKeyboardButton("⚡ Update All Topics", callback_data=f"tm_sync_{src_chat_id}_{tgt_chat_id}"),
        InlineKeyboardButton("➕ Sync New Topics", callback_data=f"tm_syncnew_{src_chat_id}_{tgt_chat_id}")
    ])
    keyboard.append([InlineKeyboardButton("🔙 Back to Session Options", callback_data=f"tm_opt_{src_chat_id}_{tgt_chat_id}")])
    
    text = (
        f"📂 **Topic Management & Links Browser**\n\n"
        f"> 📤 **Source:** `{src_title}`\n"
        f"> 📥 **Target:** `{tgt_title}`\n"
        f"> 📊 **Total Topics:** `{total_topics}` | **Page:** `{page+1}/{total_pages}`\n\n"
        f"Tap any topic below to view **Source & Target links**, **Update**, **Rename**, or **Delete**:"
    )
    html_text = format_caption_to_html(text)
    await query.message.edit_text(
        html_text if html_text else text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )


@app.on_callback_query(filters.regex(r"^tm_topinfo_(-?\d+)_(-?\d+)_(\d+)$"))
async def single_topic_info_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
        
    match = re.search(r"^tm_topinfo_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    src_topic_id = int(match.group(3))
    
    session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
    topics_dict = session.get("topics", {})
    topic_info = topics_dict.get(str(src_topic_id), {})
    
    tgt_topic_id = topic_info.get("tgt_topic_id", src_topic_id)
    title = topic_info.get("title", f"Topic {src_topic_id}")
    last_msg = topic_info.get("last_msg_id", 0)
    
    src_link = make_topic_link(src_chat_id, src_topic_id)
    tgt_link = make_topic_link(tgt_chat_id, tgt_topic_id)
    
    text = (
        f"📁 **Topic Details & Actions**\n\n"
        f"> 🏷️ **Topic Name:** `{title}`\n"
        f"> 🔢 **Source Topic ID:** `{src_topic_id}`\n"
        f"> 🎯 **Target Topic ID:** `{tgt_topic_id}`\n"
        f"> 📌 **Last Synced Checkpoint:** Post `#{last_msg}`\n\n"
        f"🔗 **Direct Clickable Topic Links:**\n"
        f"• 📤 [Open Source Topic]({src_link})\n"
        f"• 📥 [Open Target Topic]({tgt_link})\n\n"
        f"Choose an action below for this topic:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Update This Topic", callback_data=f"tm_sync1_{src_chat_id}_{tgt_chat_id}_{src_topic_id}")],
        [
            InlineKeyboardButton("✏️ Rename Topic", callback_data=f"tm_rentop_{src_chat_id}_{tgt_chat_id}_{src_topic_id}"),
            InlineKeyboardButton("🗑️ Delete Topic", callback_data=f"tm_deltop_{src_chat_id}_{tgt_chat_id}_{src_topic_id}")
        ],
        [InlineKeyboardButton("🔙 Back to Topics List", callback_data=f"tm_topics_{src_chat_id}_{tgt_chat_id}_0")]
    ])
    
    html_text = format_caption_to_html(text)
    await query.message.edit_text(
        html_text if html_text else text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True
    )


@app.on_callback_query(filters.regex(r"^tm_sync1_(-?\d+)_(-?\d+)_(\d+)$"))
async def update_single_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
        
    match = re.search(r"^tm_sync1_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    src_topic_id = int(match.group(3))
    
    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ A mirror task is already running!", show_alert=True)
        return
        
    await query.answer("⚡ Starting Update for this Topic...")
    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=False,
        detected_topic_id=src_topic_id,
        status_msg=query.message,
        force_sync=True
    )


@app.on_callback_query(filters.regex(r"^tm_rentop_(-?\d+)_(-?\d+)_(\d+)$"))
async def rename_single_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
        
    match = re.search(r"^tm_rentop_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    src_topic_id = int(match.group(3))
    
    session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
    topics_dict = session.get("topics", {})
    topic_info = topics_dict.get(str(src_topic_id), {})
    tgt_topic_id = topic_info.get("tgt_topic_id", src_topic_id)
    old_title = topic_info.get("title", f"Topic {src_topic_id}")
    
    await query.answer()
    try:
        prompt = await app.ask(
            user_id,
            f"✏️ **Rename Topic:** `{old_title}`\n\n"
            f"Send the **NEW title** for this topic:\n*(Send `/cancel` to abort)*",
            timeout=120
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Request timed out: {e}")
        return
        
    if not prompt or prompt.text == "/cancel":
        await app.send_message(user_id, "❌ Renaming cancelled.")
        return
        
    new_title = clean_topic_title(prompt.text.strip())
    if not new_title:
        await app.send_message(user_id, "❌ Invalid title.")
        return
        
    # Rename in Telegram target supergroup
    renamed_tg = False
    for client in [app]:
        try:
            peer = await client.resolve_peer(tgt_chat_id)
            await client.invoke(raw.functions.messages.EditForumTopic(
                peer=peer,
                topic_id=tgt_topic_id,
                title=new_title
            ))
            renamed_tg = True
            break
        except Exception as e:
            print(f"[TopicMirror] Rename topic in TG notice: {e}")
            
    # Update title in MongoDB
    await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, src_topic_id, tgt_topic_id, new_title)
    
    status_note = "✅ Renamed in Target Group & Database!" if renamed_tg else "✅ Updated in Database (Ensure bot has 'Manage Topics' admin rights in group)!"
    res_text = (
        f"🎉 **Topic Renamed Successfully!**\n\n"
        f"> 🏷️ **Old Title:** `{old_title}`\n"
        f"> ✨ **New Title:** `{new_title}`\n\n"
        f"{status_note}"
    )
    await app.send_message(
        user_id,
        res_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Topics", callback_data=f"tm_topics_{src_chat_id}_{tgt_chat_id}_0")]])
    )


@app.on_callback_query(filters.regex(r"^tm_deltop_(-?\d+)_(-?\d+)_(\d+)$"))
async def delete_single_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
        
    match = re.search(r"^tm_deltop_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    src_topic_id = int(match.group(3))
    
    session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
    topics_dict = session.get("topics", {})
    topic_info = topics_dict.get(str(src_topic_id), {})
    tgt_topic_id = topic_info.get("tgt_topic_id", src_topic_id)
    title = topic_info.get("title", f"Topic {src_topic_id}")
    
    # Try deleting topic history in Telegram target supergroup
    for client in [app]:
        try:
            peer = await client.resolve_peer(tgt_chat_id)
            await client.invoke(raw.functions.channels.DeleteTopicHistory(
                channel=peer,
                top_msg_id=tgt_topic_id
            ))
        except Exception as del_err:
            print(f"[TopicMirror] Delete topic TG notice: {del_err}")
            
    # Unset from MongoDB
    await db.mirror_db.update_one(
        {"_id": f"{src_chat_id}_{tgt_chat_id}"},
        {"$unset": {f"topics.{str(src_topic_id)}": ""}}
    )
    
    await query.answer(f"🗑️ Deleted topic '{title}'!", show_alert=True)
    # Refresh topics list
    await list_topics_paginated_callback(_, query)


@app.on_callback_query(filters.regex(r"^tm_syncnew_(-?\d+)_(-?\d+)$"))
async def sync_new_topics_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
        
    match = re.search(r"^tm_syncnew_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    
    await query.answer("➕ Scanning source group for new topics...")
    # Trigger full mirror scan which auto-discovers new source topics, maps/creates them in target, and syncs
    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=True,
        detected_topic_id=None,
        status_msg=query.message,
        force_sync=True
    )


@app.on_callback_query(filters.regex(r"^tm_edittgt_(-?\d+)_(-?\d+)$"))
async def edit_target_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the Topic Mirror Plan! Use /plans.", show_alert=True)
        return
    match = re.search(r"^tm_edittgt_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    old_tgt_chat_id = int(match.group(2))
    await query.answer()
    
    try:
        prompt = await app.ask(
            user_id,
            f"📥 **Send the NEW Target Supergroup ID:**\n\n"
            f"*(Must start with `-100`, e.g. `-100987654321`)*\n\n"
            f"Send `/cancel` to abort.",
            timeout=120
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Request timed out: {e}")
        return
        
    if prompt.text == "/cancel":
        await app.send_message(user_id, "❌ Target modification cancelled.")
        return
        
    try:
        new_tgt_chat_id = int(prompt.text.strip().split('/')[0])
    except ValueError:
        await app.send_message(user_id, "❌ **Invalid ID.** Must be an integer starting with `-100`.")
        return
        
    new_tgt_title = str(new_tgt_chat_id)
    try:
        tgt_obj = await app.get_chat(new_tgt_chat_id)
        if tgt_obj and tgt_obj.title:
            new_tgt_title = tgt_obj.title
    except Exception:
        pass
        
    await db.update_mirror_session_target(src_chat_id, old_tgt_chat_id, new_tgt_chat_id, new_tgt_title)
    
    success_text = (
        f"✅ **Target Group Updated Successfully!**\n\n"
        f"> 📥 **New Target:** `{new_tgt_title}` (`{new_tgt_chat_id}`)\n\n"
        f"You can now click below to continue mirroring into the updated group:"
    )
    html_text = format_caption_to_html(success_text)
    await app.send_message(
        user_id,
        html_text if html_text else success_text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_session_action_keyboard(src_chat_id, new_tgt_chat_id)
    )


@app.on_callback_query(filters.regex(r"^tm_delsess_(-?\d+)_(-?\d+)$"))
async def delete_single_session_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the ₹299 Topic Mirror Plan!", show_alert=True)
        return
    match = re.search(r"^tm_delsess_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    await db.delete_mirror_session(src_chat_id, tgt_chat_id)
    await query.answer("🗑️ Session deleted!", show_alert=True)
    
    saved_sessions = await db.get_user_mirror_sessions(user_id)
    if saved_sessions:
        hub_kb = build_mirror_hub_keyboard(user_id, saved_sessions)
        await query.message.edit_text(
            f"🎛️ **Topic Mirroring Hub**\n\n"
            f"Found **{len(saved_sessions)}** saved group session(s).\n"
            f"Click any saved session to manage, continue, or start a new mirror:",
            reply_markup=hub_kb
        )
    else:
        await query.message.edit_text(
            "ℹ️ **No saved mirror sessions remaining.**\n\nUse `/mirror` to start a fresh mirror anytime.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Start New Mirror", callback_data="tm_new")]])
        )


@app.on_callback_query(filters.regex(r"^tm_hub$"))
async def back_to_hub_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return
    saved_sessions = await db.get_user_mirror_sessions(user_id)
    if saved_sessions:
        hub_kb = build_mirror_hub_keyboard(user_id, saved_sessions)
        await query.message.edit_text(
            f"🎛️ **Topic Mirroring Hub**\n\n"
            f"Found **{len(saved_sessions)}** saved group session(s).\n"
            f"Click any saved session to manage, continue, or start a new mirror:",
            reply_markup=hub_kb
        )
    else:
        await query.message.edit_text(
            "ℹ️ **No saved mirror sessions found.**\n\nClick below to start a new mirror:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Start New Mirror", callback_data="tm_new")]])
        )


@app.on_callback_query(filters.regex(r"^tm_res_(-?\d+)_(-?\d+)$"))
async def resume_session_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the ₹299 Topic Mirror Plan! Upgrade via /plans.", show_alert=True)
        return
        
    match = re.search(r"^tm_res_(-?\d+)_(-?\d+)$", query.data)
    if not match:
        await query.answer("❌ Invalid session data.", show_alert=True)
        return
        
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    
    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ A mirror task is already running!", show_alert=True)
        return
        
    await query.answer("🚀 Resuming mirror session...")
    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=True,
        detected_topic_id=None,
        status_msg=query.message
    )


@app.on_callback_query(filters.regex(r"^tm_new$"))
async def new_mirror_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the ₹299 Topic Mirror Plan! Upgrade via /plans.", show_alert=True)
        return
    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ A mirror task is already running!", show_alert=True)
        return
    await query.answer()
    await start_new_mirror_flow(user_id, query.message, is_callback=True)


@app.on_callback_query(filters.regex(r"^tm_clear$"))
async def clear_sessions_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the ₹299 Topic Mirror Plan! Upgrade via /plans.", show_alert=True)
        return
    saved = await db.get_user_mirror_sessions(user_id)
    for s in saved:
        raw_id = s.get("_id", "")
        if "_" in raw_id:
            p = raw_id.split("_")
            await db.delete_mirror_session(p[0], p[1])
    await query.answer("🗑️ All saved mirror sessions cleared!", show_alert=True)
    await query.message.edit_text(
        "🗑️ **All saved mirror sessions have been cleared.**\n\nUse `/mirror` to start a new mirror session anytime.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Start New Mirror", callback_data="tm_new")]])
    )


async def start_new_mirror_flow(user_id: int, message, is_callback: bool = False):
    """Interactive flow to configure and launch a new topic mirror session."""
    # Check Topic Mirror Authorization
    if await chk_mirror_user(user_id) != 0:
        err_msg = (
            "<blockquote>🔒 <b>Access Denied — Topic Mirror Plan Required</b>\n\n"
            "The <b>Topic Mirroring & Auto-Folder/Topic Creation</b> feature is exclusively reserved for users with the <b>Topic Mirror Plan</b>.\n\n"
            "Standard Premium subscribers & Free users do not have access to topic cloning.\n\n"
            "💬 <b>Contact Admin:</b> @CHOSEN_ONEx_bot to purchase or upgrade your plan!</blockquote>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Buy Topic Mirror Plan", url="https://t.me/CHOSEN_ONEx_bot")]])
        if is_callback:
            await app.send_message(user_id, err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await message.reply(err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # STEP 1: Ask for Source Message/Topic Link
    try:
        prompt_1 = await app.ask(
            user_id,
            "🔗 **Send any message link from the SOURCE Topics group / channel:**\n\n"
            "*(e.g., `https://t.me/c/1234567890/164/500` or `https://t.me/username/100`)*\n\n"
            "Send `/cancel` to abort.",
            timeout=180
        )
    except Exception as e:
        err_text = "❌ **Interactive Prompt Failed:**\nPlease start the bot first in private DM (@" + (await app.get_me()).username + ") to configure prompts!"
        if is_callback:
            await app.send_message(user_id, err_text)
        else:
            await message.reply(err_text)
        return

    if prompt_1.text == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    src_link = prompt_1.text.strip()
    src_chat_id, detected_topic_id, src_msg_id = parse_source_link(src_link)

    if not src_chat_id:
        await app.send_message(user_id, "❌ **Invalid Telegram link format.** Please provide a valid message link.")
        return

    # STEP 2: Ask for Target Supergroup ID
    user_db_data = await db.get_data(user_id)
    saved_target = user_db_data.get("chat_id") if user_db_data else None

    default_prompt_text = f"\n*(Default from settings: `{saved_target}` — send `ok` to use it)*" if saved_target else ""
    try:
        prompt_2 = await app.ask(
            user_id,
            f"📥 **Send the TARGET Supergroup ID:**\n\n"
            f"*(Must start with `-100`, e.g. `-100987654321`)*{default_prompt_text}\n\n"
            f"Send `/cancel` to abort.",
            timeout=180
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Session timed out or error: {e}")
        return

    if prompt_2.text == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    target_input = prompt_2.text.strip()
    if target_input.lower() == "ok" and saved_target:
        tgt_chat_id = int(str(saved_target).split('/')[0])
    else:
        try:
            tgt_chat_id = int(target_input.split('/')[0])
        except ValueError:
            await app.send_message(user_id, "❌ **Invalid target chat ID.** Must be an integer starting with `-100`.")
            return

    # STEP 3: Ask Mirror Mode (All Topics vs Single Topic)
    mirror_all_topics = True
    if detected_topic_id:
        try:
            prompt_3 = await app.ask(
                user_id,
                f"🎛️ **Topic Selection Detected:**\n\n"
                f"• Source Topic ID detected: `{detected_topic_id}`\n\n"
                f"Reply with:\n"
                f"**1** — 🌐 Mirror **ALL Topics** from the source group (Recommended)\n"
                f"**2** — 🎯 Mirror **ONLY Topic `{detected_topic_id}`**\n\n"
                f"Send `/cancel` to abort.",
                timeout=180
            )
            if prompt_3.text == "/cancel":
                await app.send_message(user_id, "❌ Operation cancelled.")
                return
            if prompt_3.text.strip() == "2":
                mirror_all_topics = False
        except Exception:
            mirror_all_topics = True

    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=mirror_all_topics,
        detected_topic_id=detected_topic_id
    )


async def start_topic_link_flow(user_id: int, message, is_callback: bool = False):
    """Interactive prompt flow for mirroring from ONE specific topic link to ANOTHER topic link."""
    if await chk_mirror_user(user_id) != 0:
        err_msg = (
            "<blockquote>🔒 <b>Access Denied — Topic Mirror Plan Required</b>\n\n"
            "The <b>Topic Mirroring</b> feature is exclusively reserved for users with the <b>Topic Mirror Plan</b>.\n\n"
            "💬 <b>Contact Admin:</b> @CHOSEN_ONEx_bot to purchase or upgrade your plan!</blockquote>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Buy Topic Mirror Plan", url="https://t.me/CHOSEN_ONEx_bot")]])
        if is_callback:
            await app.send_message(user_id, err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await message.reply(err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        err_active = "⚠️ <b>A mirroring operation is already running!</b>\nSend <code>/cancel_mirror</code> to abort it first."
        if is_callback:
            await app.send_message(user_id, err_active, parse_mode=ParseMode.HTML)
        else:
            await message.reply(err_active, parse_mode=ParseMode.HTML)
        return

async def run_single_link_mirror(
    user_id: int,
    src_chat_id: int,
    src_topic_id: int,
    tgt_chat_id: int,
    tgt_topic_id: int = None,
    src_start_id: int = None,
    src_end_id: int = None,
    status_msg = None
):
    """
    Dedicated Link-to-Link Topic/Channel Mirror Engine.
    Uses independent MongoDB storage (link_mirror_db) so single topic copies
    never interfere with each other or with full group mirroring sessions.
    """
    if await chk_mirror_user(user_id) != 0:
        err_msg = (
            "<blockquote>🔒 <b>Access Denied — Topic Mirror Plan Required</b>\n\n"
            "You need an active <b>Topic Mirror Plan</b> to run Topic Mirroring. Contact @CHOSEN_ONEx_bot to purchase access.</blockquote>"
        )
        if status_msg:
            try:
                await status_msg.edit(err_msg, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            await app.send_message(user_id, err_msg, parse_mode=ParseMode.HTML)
        return

    userbot, is_temp_userbot = await get_working_userbot(user_id)
    if not userbot:
        err_ub = "❌ <b>No working userbot session!</b>\nPlease use `/login` to login your account first."
        if status_msg:
            try:
                await status_msg.edit(err_ub, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            await app.send_message(user_id, err_ub, parse_mode=ParseMode.HTML)
        return

    active_mirrors[user_id] = {
        "running": True,
        "skip_topic": False,
        "current_topic": f"Topic {src_topic_id or 1}"
    }

    try:
        # Check if source is a broadcast channel
        # Check if source is a broadcast channel or if explicit post range is provided
        try:
            from pyrogram import enums
            src_chat = await userbot.get_chat(src_chat_id)
            if src_chat.type == enums.ChatType.CHANNEL or not getattr(src_chat, "is_forum", False):
                if src_topic_id and src_topic_id > 1:
                    if not src_start_id or src_start_id == 0:
                        src_start_id = src_topic_id
                    src_topic_id = 0
        except Exception as e:
            print(f"[SingleLinkMirror] Source chat check notice: {e}")

        if src_start_id and src_end_id and src_end_id >= src_start_id:
            # Explicit post range provided (e.g. 5494 -> 6541)
            src_topic_id = 0

        # Check independent checkpoint from link_mirror_db
        saved_checkpoint = await db.get_link_mirror_checkpoint(src_chat_id, src_topic_id or 0, tgt_chat_id, tgt_topic_id or 0)

        # Determine effective start bound (explicit user start_id takes precedence over checkpoint)
        if src_start_id and src_start_id > 0:
            effective_start = max(0, src_start_id - 1)
        elif saved_checkpoint > 0:
            effective_start = saved_checkpoint
        else:
            effective_start = 0

        # Fetch messages for source topic or channel
        all_messages = []
        messages_to_copy = []

        if src_topic_id and src_topic_id > 1:
            # Forum topic — use discussion replies (already fetches everything properly)
            all_messages = await fetch_all_messages_for_topic(userbot, src_chat_id, src_topic_id, min_msg_id=effective_start)
            if src_end_id and src_end_id > 0:
                messages_to_copy = [m for m in all_messages if m.id <= src_end_id]
            else:
                messages_to_copy = all_messages
        else:
            # Channel / non-topic group fetch — fetch EXACT range using chunked get_messages
            # Determine the maximum message ID to fetch up to
            max_limit_id = src_end_id
            if not max_limit_id or max_limit_id <= 0:
                try:
                    async for m in userbot.get_chat_history(src_chat_id, limit=1):
                        if m:
                            max_limit_id = m.id
                except Exception:
                    max_limit_id = effective_start + 4000  # Fallback buffer if history fails

            if max_limit_id and max_limit_id > effective_start:
                # Cap batch to 4000 messages per command invocation to prevent excessive memory/API time
                fetch_end = min(max_limit_id, effective_start + 4000)
                msg_ids_to_fetch = list(range(effective_start + 1, fetch_end + 1))

                chunk_size = 200
                chunks = [msg_ids_to_fetch[i:i + chunk_size] for i in range(0, len(msg_ids_to_fetch), chunk_size)]

                for fetch_client in [userbot, app]:
                    temp_collected = []
                    try:
                        for chk in chunks:
                            fetched_msgs = await fetch_client.get_messages(src_chat_id, message_ids=chk)
                            msg_list = fetched_msgs if isinstance(fetched_msgs, list) else [fetched_msgs]
                            for m in msg_list:
                                if m and not getattr(m, "empty", False) and getattr(m, "id", None):
                                    temp_collected.append(m)
                        if temp_collected:
                            messages_to_copy = sorted(temp_collected, key=lambda x: x.id)
                            break  # Successfully fetched with this client
                    except Exception as e:
                        print(f"[SingleLinkMirror] Range fetch notice ({fetch_client.__class__.__name__}): {e}")

        total_count = len(messages_to_copy)

        if total_count == 0:
            msg_empty = (
                f"ℹ️ <b>No new pending messages to mirror!</b>\n\n"
                f"• <b>Saved Checkpoint:</b> Post #{saved_checkpoint}\n"
                f"• <b>Total fetched:</b> {len(all_messages)}"
            )
            if status_msg:
                try:
                    await status_msg.edit(msg_empty, parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            else:
                await app.send_message(user_id, msg_empty, parse_mode=ParseMode.HTML)
            return

        # Start copying loop
        start_time = time.time()
        last_edit_time = start_time
        copied_count = 0
        failed_count = 0
        pin_first_msg_id = None  # Track first successfully sent message for pinning

        control_kb = get_mirror_keyboard(user_id)

        for idx, msg in enumerate(messages_to_copy, 1):
            if not active_mirrors.get(user_id, {}).get("running", True):
                await app.send_message(user_id, "🛑 <b>Link Mirror stopped by user!</b>", parse_mode=ParseMode.HTML)
                break

            # Skip service / empty messages
            if getattr(msg, "service", False) or getattr(msg, "empty", False) or getattr(msg, "action", None):
                await db.save_link_mirror_checkpoint(src_chat_id, src_topic_id or 0, tgt_chat_id, tgt_topic_id or 0, msg.id)
                continue

            # Process & Copy message using full transfer pipeline
            success = False
            method = "failed"
            sent_msg_id = None
            for retry in range(1, 4):
                try:
                    await ensure_userbot_connected(userbot)
                    effective_tgt_topic_id = None if (tgt_topic_id == 1) else tgt_topic_id
                    success, method, sent_msg_id = await transfer_single_message(
                        userbot=userbot,
                        app=app,
                        src_chat_id=src_chat_id,
                        tgt_chat_id=tgt_chat_id,
                        tgt_topic_id=effective_tgt_topic_id,
                        msg=msg,
                        user_id=user_id
                    )
                    if success or method in ("service_skipped", "skipped_filter"):
                        break
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 1)
                except Exception as err:
                    print(f"[SingleLinkMirror] Msg {msg.id} transfer attempt {retry}/3 error: {err}")
                    await asyncio.sleep(1)

            if success:
                if method != "service_skipped":
                    copied_count += 1
                    # Track first message for pin
                    if pin_first_msg_id is None and sent_msg_id:
                        pin_first_msg_id = sent_msg_id
            else:
                if method != "skipped_filter":
                    failed_count += 1

            # Save checkpoint in independent link_mirror_db after processing message
            await db.save_link_mirror_checkpoint(src_chat_id, src_topic_id or 0, tgt_chat_id, tgt_topic_id or 0, msg.id)

            # Live UI Dashboard Update
            now = time.time()
            if now - last_edit_time > 3.5:
                last_edit_time = now
                pct = int((idx / total_count) * 100)
                filled = int(pct / 10)
                bar = "█" * filled + "░" * (10 - filled)
                elapsed = now - start_time
                speed = copied_count / max(elapsed, 0.1)
                eta = int((total_count - idx) / speed) if speed > 0 else 0

                dashboard_text = (
                    f"⚡ <b>Topic Link Mirror Progress</b>\n\n"
                    f"┌ <b>Progress:</b> [{bar}] <b>{pct}%</b>\n"
                    f"├ <b>Downloaded:</b> <code>{copied_count}</code> / <code>{total_count}</code>\n"
                    f"├ <b>Failed:</b> <code>{failed_count}</code>\n"
                    f"├ <b>Speed:</b> <code>{speed:.1f}</code> msgs/s\n"
                    f"└ <b>ETA:</b> <code>{TimeFormatter(eta*1000)}</code>"
                )
                if status_msg:
                    try:
                        await status_msg.edit(dashboard_text, parse_mode=ParseMode.HTML, reply_markup=control_kb)
                    except Exception:
                        pass

        # Auto-pin first transferred message in target topic
        if pin_first_msg_id and tgt_topic_id:
            try:
                await app.pin_chat_message(
                    chat_id=tgt_chat_id,
                    message_id=pin_first_msg_id,
                    disable_notification=True,
                    both_sides=False
                )
                print(f"[SingleLinkMirror] 📌 Pinned first message {pin_first_msg_id} in target topic {tgt_topic_id}")
                # Auto-delete the "pinned a message" service message
                async for sys_m in app.get_chat_history(tgt_chat_id, limit=5):
                    if getattr(sys_m, "service", False) and getattr(sys_m, "pinned_message", None):
                        try:
                            await sys_m.delete()
                        except Exception:
                            pass
            except Exception as pin_err:
                print(f"[SingleLinkMirror] Pin notice: {pin_err}")

        # Send Completion Message DIRECTLY to target topic inside blockquote
        elapsed_total = time.time() - start_time
        completion_msg = (
            "<blockquote><b>✅ 𝗖ꪮ𝗺𝗽𝗹𝗲𝘁𝗲 𝗛ꪮ 𝗚𝗮𝘆𝗮 𝗕ꪮ$$ 😎</b>\n\n"
            f"📁 <b>Total Downloaded:</b> <code>{copied_count}</code> files\n"
            f"❌ <b>Failed:</b> <code>{failed_count}</code>\n"
            f"⏱ <b>Time Taken:</b> <code>{TimeFormatter(int(elapsed_total)*1000)}</code></blockquote>"
        )
        try:
            if tgt_topic_id:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=completion_msg,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=tgt_topic_id
                )
            else:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=completion_msg,
                    parse_mode=ParseMode.HTML
                )
        except Exception as send_err:
            print(f"[SingleLinkMirror] Failed sending completion msg to target: {send_err}")

        # Update User Status DM
        final_summary = (
            f"✅ <b>Topic Link Mirror Complete!</b>\n\n"
            f"📁 <b>Transferred:</b> <code>{copied_count}</code> files\n"
            f"❌ <b>Failed:</b> <code>{failed_count}</code>\n"
            f"⏱ <b>Time:</b> <code>{TimeFormatter(int(elapsed_total)*1000)}</code>\n"
            f"📍 <b>Target:</b> <code>{tgt_chat_id}</code>" + (f" › Topic <code>{tgt_topic_id}</code>" if tgt_topic_id else "")
        )
        if status_msg:
            try:
                await status_msg.edit(final_summary, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    except Exception as exec_err:
        print(f"[SingleLinkMirror] Execution error: {exec_err}")
        if status_msg:
            try:
                await status_msg.edit(f"❌ <b>Link Mirror Error:</b> `{exec_err}`")
            except Exception:
                pass
    finally:
        active_mirrors.pop(user_id, None)
        if is_temp_userbot and userbot:
            try:
                await userbot.stop()
            except Exception:
                pass


async def start_topic_link_flow(user_id: int, message, is_callback: bool = False):
    """Interactive prompt flow for mirroring from ONE specific topic link to ANOTHER topic link with range support."""
    if await chk_mirror_user(user_id) != 0:
        err_msg = (
            "<blockquote>🔒 <b>Access Denied — Topic Mirror Plan Required</b>\n\n"
            "The <b>Topic Mirroring</b> feature is exclusively reserved for users with the <b>Topic Mirror Plan</b>.\n\n"
            "💬 <b>Contact Admin:</b> @CHOSEN_ONEx_bot to purchase or upgrade your plan!</blockquote>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Buy Topic Mirror Plan", url="https://t.me/CHOSEN_ONEx_bot")]])
        if is_callback:
            await app.send_message(user_id, err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await message.reply(err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        err_active = "⚠️ <b>A mirroring operation is already running!</b>\nSend <code>/cancel_mirror</code> to abort it first."
        if is_callback:
            await app.send_message(user_id, err_active, parse_mode=ParseMode.HTML)
        else:
            await message.reply(err_active, parse_mode=ParseMode.HTML)
        return

    # STEP 1: SOURCE Link (Topic link / Post link / Channel link)
    try:
        prompt_1 = await app.ask(
            user_id,
            "📌 <b>TOPIC LINK MIRROR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📥 <b>Step 1 of 3 — Source Link</b>\n"
            "<i>Jis topic/channel se copy karna hai uska link bhejo.</i>\n\n"
            "<b>Formats:</b>\n"
            "• 📂 Topic link: <code>https://t.me/c/123/50</code>\n"
            "• 🎯 Post link: <code>https://t.me/c/123/50/100</code>\n"
            "• 📣 Channel link: <code>https://t.me/channel/100</code>\n\n"
            "❌ Send <code>/cancel</code> to abort.",
            timeout=300,
            parse_mode=ParseMode.HTML
        )
    except Exception:
        err_text = "⏱ <b>Prompt timed out!</b>\n\nPlease start the bot in your private DM first."
        if is_callback:
            await app.send_message(user_id, err_text, parse_mode=ParseMode.HTML)
        else:
            await message.reply(err_text, parse_mode=ParseMode.HTML)
        return

    if prompt_1.text.strip() == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    src_link = prompt_1.text.strip()
    src_chat_id, src_topic_id, src_post_id = parse_topic_and_post_link(src_link)

    if not src_chat_id:
        await app.send_message(
            user_id,
            "❌ <b>Invalid Source link!</b>\n\nCould not extract Group / Channel ID.\n\n"
            "Example: <code>https://t.me/c/1234567890/50</code>",
            parse_mode=ParseMode.HTML
        )
        return

    src_start_id = src_post_id if src_post_id else (src_topic_id if src_topic_id else 0)

    # STEP 2: End Post Link or Count (Optional)
    try:
        prompt_2 = await app.ask(
            user_id,
            "📌 <b>TOPIC LINK MIRROR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📥 <b>Step 2 of 3 — Range Limit</b>\n"
            "<i>Kahan tak copy karna hai? (Sab copy karna ho to 0 bhejo)</i>\n\n"
            "<b>Options:</b>\n"
            "• 🏁 End post link: <code>https://t.me/c/123/50/200</code>\n"
            "• 🔢 Message count: <code>50</code>\n"
            "• ♾️ All pending: <code>0</code> or <code>all</code>\n\n"
            "❌ Send <code>/cancel</code> to abort.",
            timeout=300,
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await app.send_message(user_id, "⏱ <b>Prompt timed out.</b>", parse_mode=ParseMode.HTML)
        return

    if prompt_2.text.strip() == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    src_end_id = 0
    val2 = prompt_2.text.strip()
    if val2.isdigit():
        count_or_id = int(val2)
        if count_or_id > 0:
            if src_start_id > 0 and count_or_id < 10000 and count_or_id < src_start_id:
                src_end_id = src_start_id + count_or_id - 1
            else:
                src_end_id = count_or_id
    else:
        _, end_tid, end_pid = parse_topic_and_post_link(val2)
        src_end_id = end_pid or end_tid or 0

    # STEP 3: TARGET Topic Link / Group Link
    try:
        prompt_3 = await app.ask(
            user_id,
            "📌 <b>TOPIC LINK MIRROR</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "📥 <b>Step 3 of 3 — Target Destination</b>\n"
            "<i>Jahan content dalna hai uska link bhejo (Bot Admin hona chahiye).</i>\n\n"
            "<b>Formats:</b>\n"
            "• 📂 Topic link: <code>https://t.me/c/987/200</code>\n"
            "• 🆔 Group ID: <code>-1009876543</code>\n"
            "• 👤 Username: <code>@my_channel</code>\n\n"
            "❌ Send <code>/cancel</code> to abort.",
            timeout=300,
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await app.send_message(user_id, "❌ <b>Prompt timed out.</b>", parse_mode=ParseMode.HTML)
        return

    if prompt_3.text.strip() == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    tgt_link = prompt_3.text.strip()
    tgt_chat_id, tgt_topic_id, _ = parse_topic_and_post_link(tgt_link)

    if not tgt_chat_id:
        await app.send_message(
            user_id,
            "❌ <b>Invalid Target link!</b>\nExample: <code>https://t.me/c/9876543210/200</code>",
            parse_mode=ParseMode.HTML
        )
        return

    # Resolve usernames to numeric IDs
    userbot, _ = await get_working_userbot(user_id)
    if isinstance(src_chat_id, str) and userbot:
        try:
            c = await userbot.get_chat(src_chat_id)
            src_chat_id = c.id
        except Exception:
            pass

    if isinstance(tgt_chat_id, str):
        try:
            c = await app.get_chat(tgt_chat_id)
            tgt_chat_id = c.id
        except Exception:
            pass

    start_str = f"#{src_start_id}" if src_start_id > 0 else "Beginning"
    end_str = f"#{src_end_id}" if src_end_id > 0 else "End"

    control_kb = get_mirror_keyboard(user_id)
    status_msg = await app.send_message(
        user_id,
        f"🚀 <b>Single Topic Link Mirror Starting...</b>\n\n"
        f"📤 <b>Source:</b> <code>{src_chat_id}</code>" + (f" | Topic: <code>{src_topic_id}</code>" if src_topic_id else "") + "\n"
        f"📥 <b>Target:</b> <code>{tgt_chat_id}</code>" + (f" | Topic: <code>{tgt_topic_id}</code>" if tgt_topic_id else "") + "\n"
        f"📊 <b>Range:</b> {start_str} ➔ {end_str}",
        parse_mode=ParseMode.HTML,
        reply_markup=control_kb
    )

    await run_single_link_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        src_topic_id=src_topic_id,
        tgt_chat_id=tgt_chat_id,
        tgt_topic_id=tgt_topic_id,
        src_start_id=src_start_id if src_start_id > 0 else None,
        src_end_id=src_end_id if src_end_id > 0 else None,
        status_msg=status_msg
    )


@app.on_message(filters.command(["topiclink", "linkmirror", "topicmirrorlink"]))
async def topic_link_cmd(client, message):
    if not message.from_user:
        await message.reply("❌ **Error:** This command must be sent by a user.")
        return
    user_id = message.from_user.id
    await start_topic_link_flow(user_id, message, is_callback=False)


@app.on_callback_query(filters.regex(r"^tm_topiclink$"))
async def topic_link_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirroring requires the ₹299 Topic Mirror Plan!", show_alert=True)
        return
    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ A mirror task is already running!", show_alert=True)
        return
    await query.answer()
    await start_topic_link_flow(user_id, query.message, is_callback=True)


@app.on_callback_query(filters.regex(r"^tm_picktopic_(-?\d+)_(-?\d+)$"))
async def pick_single_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return

    match = re.search(r"^tm_picktopic_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))

    await query.answer("🔍 Fetching topics...")
    userbot, is_temp = await get_working_userbot(user_id)
    if not userbot:
        await query.message.reply("❌ No userbot session available!")
        return

    topics = []
    try:
        peer = await userbot.resolve_peer(src_chat_id)
        res = await userbot.invoke(raw.functions.messages.GetForumTopics(
            peer=peer, offset_date=0, offset_id=0, offset_topic=0, limit=100
        ))
        for t in getattr(res, "topics", []):
            if getattr(t, "id", None):
                topics.append((t.id, getattr(t, "title", f"Topic {t.id}")))
    except Exception:
        topics = [(1, "General")]

    if is_temp and userbot:
        try:
            await userbot.stop()
        except Exception:
            pass

    if not topics:
        topics = [(1, "General")]

    buttons = []
    for tid, ttitle in topics[:40]:
        t_label = ttitle[:20] if len(ttitle) > 20 else ttitle
        buttons.append([InlineKeyboardButton(f"🎯 {t_label}", callback_data=f"tm_dosingle_{src_chat_id}_{tgt_chat_id}_{tid}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"tm_opt_{src_chat_id}_{tgt_chat_id}")])

    await query.message.edit_text(
        "🎯 **Select the single topic you want to mirror:**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^tm_dosingle_(-?\d+)_(-?\d+)_(\d+)$"))
async def do_single_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return

    match = re.search(r"^tm_dosingle_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    topic_id = int(match.group(3))

    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ Mirror task already running!", show_alert=True)
        return

    await query.answer("🚀 Starting single topic mirror...")
    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=False,
        detected_topic_id=topic_id,
        status_msg=query.message
    )


@app.on_callback_query(filters.regex(r"^tm_reuploadtopic_(-?\d+)_(-?\d+)$"))
async def reupload_single_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return

    match = re.search(r"^tm_reuploadtopic_(-?\d+)_(-?\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))

    await query.answer("🔍 Fetching topics for re-upload...")
    userbot, is_temp = await get_working_userbot(user_id)
    if not userbot:
        await query.message.reply("❌ No userbot session available!")
        return

    topics = []
    try:
        peer = await userbot.resolve_peer(src_chat_id)
        res = await userbot.invoke(raw.functions.messages.GetForumTopics(
            peer=peer, offset_date=0, offset_id=0, offset_topic=0, limit=100
        ))
        for t in getattr(res, "topics", []):
            if getattr(t, "id", None):
                topics.append((t.id, getattr(t, "title", f"Topic {t.id}")))
    except Exception:
        topics = [(1, "General")]


    if is_temp and userbot:
        try:
            await userbot.stop()
        except Exception:
            pass

    if not topics:
        topics = [(1, "General")]

    buttons = []
    for tid, ttitle in topics[:40]:
        t_label = ttitle[:20] if len(ttitle) > 20 else ttitle
        buttons.append([InlineKeyboardButton(f"🔄 Re-upload {t_label}", callback_data=f"tm_doreupload_{src_chat_id}_{tgt_chat_id}_{tid}")])

    buttons.append([InlineKeyboardButton("🔙 Back", callback_data=f"tm_opt_{src_chat_id}_{tgt_chat_id}")])

    await query.message.edit_text(
        "🔄 **Select the topic to RE-UPLOAD from scratch (resets checkpoint to 0):**",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


@app.on_callback_query(filters.regex(r"^tm_doreupload_(-?\d+)_(-?\d+)_(\d+)$"))
async def do_reupload_topic_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if await chk_mirror_user(user_id) != 0:
        await query.answer("🔒 Topic Mirror Plan required!", show_alert=True)
        return

    match = re.search(r"^tm_doreupload_(-?\d+)_(-?\d+)_(\d+)$", query.data)
    src_chat_id = int(match.group(1))
    tgt_chat_id = int(match.group(2))
    topic_id = int(match.group(3))

    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await query.answer("⚠️ Mirror task already running!", show_alert=True)
        return

    await query.answer("🔄 Resetting topic checkpoint & re-uploading from post #1...")
    await db.update_mirror_topic_checkpoint(src_chat_id, tgt_chat_id, topic_id, 0)

    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=False,
        detected_topic_id=topic_id,
        status_msg=query.message,
        force_sync=True
    )



@app.on_message(filters.command(["topicmirror", "tmirror", "mirror"]))
async def topic_mirror_cmd(client, message):
    if not message.from_user:
        await message.reply("❌ **Error:** This command must be sent by a user.")
        return

    user_id = message.from_user.id

    # Check Topic Mirror Authorization
    if await chk_mirror_user(user_id) != 0:
        err_msg = (
            "<blockquote>🔒 <b>Access Denied — Topic Mirror Plan Required</b>\n\n"
            "The <b>Topic Mirroring & Auto-Folder/Topic Creation</b> feature is exclusively reserved for users with the <b>Topic Mirror Plan</b>.\n\n"
            "Standard Premium subscribers & Free users do not have access to topic cloning.\n\n"
            "💬 <b>Contact Admin:</b> @CHOSEN_ONEx_bot to purchase or upgrade your plan!</blockquote>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Buy Topic Mirror Plan", url="https://t.me/CHOSEN_ONEx_bot")]])
        await message.reply(err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if user_id in active_mirrors and isinstance(active_mirrors[user_id], dict) and active_mirrors[user_id].get("running"):
        await message.reply("⚠️ **A mirroring operation is already running!** Send `/cancel_mirror` to abort it first.")
        return

    # Check for existing saved mirror sessions
    saved_sessions = await db.get_user_mirror_sessions(user_id)
    if saved_sessions:
        hub_kb = build_mirror_hub_keyboard(user_id, saved_sessions)
        await message.reply(
            f"🎛️ **Topic Mirroring Hub**\n\n"
            f"Found **{len(saved_sessions)}** saved group session(s).\n"
            f"Click a button below to **instantly resume/update pending topics**, or start a new mirror:",
            reply_markup=hub_kb
        )
    else:
        await start_new_mirror_flow(user_id, message)


async def run_topic_mirror(user_id: int, src_chat_id: int, tgt_chat_id: int, mirror_all_topics: bool = True, detected_topic_id: int = None, forced_tgt_topic_id: int = None, status_msg=None, force_sync: bool = False, src_start_id: int = None, src_end_id: int = None):
    """Core execution engine for topic mirroring with instant resume, rapid extraction, force sync, and range support."""
    # Check Topic Mirror Authorization
    if await chk_mirror_user(user_id) != 0:
        err_msg = (
            "<blockquote>🔒 <b>Access Denied — Topic Mirror Plan Required</b>\n\n"
            "You need an active <b>Topic Mirror Plan</b> to run Topic Mirroring. Contact @CHOSEN_ONEx_bot to purchase access.</blockquote>"
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Buy Topic Mirror Plan", url="https://t.me/CHOSEN_ONEx_bot")]])
        if status_msg:
            try:
                await status_msg.edit(err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
        else:
            await app.send_message(user_id, err_msg, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    control_kb = get_mirror_keyboard(user_id)

    if status_msg:
        try:
            await status_msg.edit(
                "🔄 **Initializing Userbot Session & Verifying Group Access...**",
                reply_markup=control_kb
            )
        except Exception:
            status_msg = await app.send_message(
                user_id,
                "🔄 **Initializing Userbot Session & Verifying Group Access...**",
                reply_markup=control_kb
            )
    else:
        status_msg = await app.send_message(
            user_id,
            "🔄 **Initializing Userbot Session & Verifying Group Access...**",
            reply_markup=control_kb
        )

    userbot, is_temp_userbot = await get_working_userbot(user_id)
    if not userbot:
        await status_msg.edit(
            "❌ **No working userbot session available!**\n\n"
            "Please use `/login` in the bot to login your Telegram account session so the bot can access private source groups."
        )
        return

    active_mirrors[user_id] = {
        "running": True,
        "skip_topic": False,
        "current_topic": ""
    }

    try:
        # Resolve source chat
        try:
            src_chat = await userbot.get_chat(src_chat_id)
            src_title = src_chat.title or str(src_chat_id)
        except Exception as e:
            await status_msg.edit(
                f"❌ **Could not access source group (`{src_chat_id}`):**\n`{e}`\n\n"
                f"Make sure your logged-in userbot account is a **member** of this group!"
            )
            return

        # Resolve target chat
        try:
            tgt_chat = await app.get_chat(tgt_chat_id)
            tgt_title = tgt_chat.title or str(tgt_chat_id)
        except Exception as e:
            await status_msg.edit(
                f"❌ **Could not access target group (`{tgt_chat_id}`):**\n`{e}`\n\n"
                f"Make sure the bot is an **Admin** in the target group!"
            )
            return

        # Ensure Topics / Forum is enabled in Target Supergroup
        try:
            await app.invoke(raw.functions.channels.ToggleForum(
                channel=await app.resolve_peer(tgt_chat_id),
                enabled=True,
                tabs=False
            ))
        except Exception as tf_err:
            pass

        # Save session metadata for instant resume buttons
        await db.save_mirror_session_info(user_id, src_chat_id, tgt_chat_id, src_title, tgt_title)

        # Auto-update target group bio / description with disclaimer & contact info
        try:
            from toxic.core.mongo.db import get_custom_group_bio, add_joined_chat
            target_bio = await get_custom_group_bio()
            await app.set_chat_description(tgt_chat_id, target_bio)
            await add_joined_chat(tgt_chat_id, tgt_title)
        except Exception as bio_err:
            print(f"[TopicMirror] Target group bio update notice: {bio_err}")

        await status_msg.edit(
            f"🔍 **Phase 1: Scanning Topics & Checking Existing Mappings...**\n\n"
            f"📤 **Source:** `{src_title}`\n"
            f"📥 **Target:** `{tgt_title}`",
            reply_markup=control_kb
        )

        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # PHASE 1: DISCOVER SOURCE TOPICS & MAP WITHOUT DUPLICATES
        # -------------------------------------------------------------
        # Save session metadata to MongoDB FIRST
        await db.save_mirror_session_info(user_id, src_chat_id, tgt_chat_id, src_title, tgt_title)
        saved_session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
        saved_topics = saved_session.get("topics", {}) if saved_session else {}

        topic_map = {}   # src_topic_id -> tgt_topic_id
        topic_names = {} # src_topic_id -> title

        # Scan existing target topics in supergroup
        target_topics_by_title, target_topics_by_id = await get_all_target_forum_topics(userbot, app, tgt_chat_id)

        # Pre-populate already mapped topics from MongoDB and lock them in lookup dicts
        if saved_topics:
            for st_id_str, info in saved_topics.items():
                try:
                    s_id = int(st_id_str)
                    tgt_id = info.get("tgt_topic_id")
                    t_title = info.get("title", f"Topic {s_id}")
                    if tgt_id:
                        tgt_id_int = int(tgt_id)
                        if tgt_id_int == 1:
                            if s_id == 1 or normalize_topic_title(t_title) in ("general", "1", "main"):
                                topic_map[s_id] = 1
                                topic_names[s_id] = t_title
                        else:
                            actual_tgt_title = target_topics_by_id.get(tgt_id_int)
                            if actual_tgt_title:
                                if match_existing_target_topic(t_title, {actual_tgt_title: tgt_id_int}):
                                    topic_map[s_id] = tgt_id_int
                                    topic_names[s_id] = t_title
                                    _register_topic(target_topics_by_title, target_topics_by_id, t_title, tgt_id_int)
                                else:
                                    print(f"[TopicMirror] ⚠️ Saved mapping for src '{t_title}' pointed to mismatched tgt topic '{actual_tgt_title}' ({tgt_id_int}). Unbinding.")
                            else:
                                topic_map[s_id] = tgt_id_int
                                topic_names[s_id] = t_title
                except Exception:
                    pass

        # If forced_tgt_topic_id is set (Direct Topic Link Mirroring)
        if forced_tgt_topic_id is not None and detected_topic_id is not None:
            st_title = f"Topic {detected_topic_id}"
            try:
                peer = await userbot.resolve_peer(src_chat_id)
                res = await userbot.invoke(raw.functions.messages.GetForumTopics(
                    peer=peer, offset_date=0, offset_id=0, offset_topic=0, limit=100
                ))
                for t in getattr(res, "topics", []):
                    if getattr(t, "id", None) == detected_topic_id:
                        st_title = getattr(t, "title", st_title)
                        break
            except Exception:
                pass

            topic_map[detected_topic_id] = forced_tgt_topic_id
            topic_names[detected_topic_id] = st_title
            _register_topic(target_topics_by_title, target_topics_by_id, st_title, forced_tgt_topic_id)
            await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, detected_topic_id, forced_tgt_topic_id, st_title)

        # Fetch all source topics with complete pagination & deep history fallback
        source_topics = await get_all_source_forum_topics(userbot, src_chat_id)

        # Include any historically saved topics from MongoDB not returned by live scan
        if saved_topics:
            existing_src_ids = {t["id"] for t in source_topics}
            for st_id_str, info in saved_topics.items():
                try:
                    s_id = int(st_id_str)
                    if s_id not in existing_src_ids:
                        t_title = info.get("title", f"Topic {s_id}")
                        source_topics.append({"id": s_id, "title": t_title, "icon_color": None, "icon_emoji_id": None})
                except Exception:
                    pass

        if not source_topics and detected_topic_id:
            source_topics.append({"id": detected_topic_id, "title": f"Topic {detected_topic_id}", "icon_color": None, "icon_emoji_id": None})

        if not mirror_all_topics and detected_topic_id:
            source_topics = [t for t in source_topics if t["id"] == detected_topic_id]
            if not source_topics:
                source_topics = [{"id": detected_topic_id, "title": f"Topic {detected_topic_id}", "icon_color": None, "icon_emoji_id": None}]

        if not source_topics:
            source_topics = [{"id": 1, "title": "General", "icon_color": None, "icon_emoji_id": None}]

        for st in source_topics:
            st_id = st["id"]
            st_title = st["title"].strip()
            topic_names[st_id] = st_title
            norm_title = normalize_topic_title(st_title)

            # 1. Already mapped in topic_map
            if st_id in topic_map and topic_map[st_id]:
                continue

            # 2. General topic (id 1) always maps to target General topic (1)
            if st_id == 1 or norm_title in ("general", "1", "main"):
                topic_map[st_id] = 1
                _register_topic(target_topics_by_title, target_topics_by_id, st_title, 1)
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, 1, st_title)
                continue

            # 3. Check persistent MongoDB session (validate target title matches before reusing)
            saved_info = saved_topics.get(str(st_id))
            if saved_info and saved_info.get("tgt_topic_id"):
                try:
                    existing_tgt_id = int(saved_info["tgt_topic_id"])
                    if existing_tgt_id > 1:
                        actual_tgt_title = target_topics_by_id.get(existing_tgt_id)
                        if not actual_tgt_title or match_existing_target_topic(st_title, {actual_tgt_title: existing_tgt_id}):
                            topic_map[st_id] = existing_tgt_id
                            _register_topic(target_topics_by_title, target_topics_by_id, st_title, existing_tgt_id)
                            print(f"[TopicMirror] ✅ Reusing verified Mongo mapped tgt_topic_id {existing_tgt_id} for '{st_title}'")
                            continue
                        else:
                            print(f"[TopicMirror] ⚠️ Saved Mongo mapping for '{st_title}' was mismatched with tgt '{actual_tgt_title}'. Creating/finding correct topic.")
                except Exception as e:
                    print(f"[TopicMirror] Saved info parse notice for '{st_title}': {e}")

            # 4. Check if target group already has a topic with matching title (Multi-level match)
            existing_tgt_id = match_existing_target_topic(st_title, target_topics_by_title)
            if existing_tgt_id:
                topic_map[st_id] = existing_tgt_id
                _register_topic(target_topics_by_title, target_topics_by_id, st_title, existing_tgt_id)
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, existing_tgt_id, st_title)
                print(f"[TopicMirror] ✅ Found existing matching target topic {existing_tgt_id} for '{st_title}'")
                continue

            # 5. Direct Telegram Server RPC Query (q=st_title) to guarantee no duplicate created if scan missed it
            rpc_matched_id = await search_target_topic_by_rpc(userbot, app, tgt_chat_id, st_title)
            if rpc_matched_id:
                topic_map[st_id] = rpc_matched_id
                _register_topic(target_topics_by_title, target_topics_by_id, st_title, rpc_matched_id)
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, rpc_matched_id, st_title)
                print(f"[TopicMirror] ✅ Direct Telegram RPC server query found '{st_title}' → tgt topic {rpc_matched_id}")
                continue

            # 6. Fresh re-scan right before creating a new topic as extra safeguard
            fresh_target_topics, fresh_target_by_id = await get_all_target_forum_topics(userbot, app, tgt_chat_id)
            target_topics_by_title.update(fresh_target_topics)
            target_topics_by_id.update(fresh_target_by_id)
            existing_tgt_id = match_existing_target_topic(st_title, fresh_target_topics) or match_existing_target_topic(clean_topic_title(st_title), fresh_target_topics)
            if existing_tgt_id:
                topic_map[st_id] = existing_tgt_id
                _register_topic(target_topics_by_title, target_topics_by_id, st_title, existing_tgt_id)
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, existing_tgt_id, st_title)
                print(f"[TopicMirror] ✅ Fresh scan found '{st_title}' → tgt topic {existing_tgt_id}")
                continue

            # ─────────────────────────────────────────────────────────────
            # STEP 7: Create topic ONLY if confirmed absent everywhere
            # ─────────────────────────────────────────────────────────────
            clean_st_title = clean_topic_title(st_title)
            src_icon_color = st.get("icon_color") or 0x6FB9F0
            src_icon_emoji_id = st.get("icon_emoji_id") or None

            # Final check against clean title
            existing_tgt_id = (
                match_existing_target_topic(clean_st_title, fresh_target_topics)
                or match_existing_target_topic(st_title, fresh_target_topics)
                or await search_target_topic_by_rpc(userbot, app, tgt_chat_id, clean_st_title)
            )
            if existing_tgt_id:
                topic_map[st_id] = existing_tgt_id
                _register_topic(target_topics_by_title, target_topics_by_id, clean_st_title, existing_tgt_id)
                _register_topic(target_topics_by_title, target_topics_by_id, st_title, existing_tgt_id)
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, existing_tgt_id, st_title)
                print(f"[TopicMirror] ✅ Pre-create scan/RPC found '{clean_st_title}' → tgt topic {existing_tgt_id}")
                continue

            # ── Single create attempt (high-level Pyrogram first, raw RPC on failure) ──
            new_tgt_topic_id = None

            # Attempt 1: high-level API
            try:
                create_kwargs = {"chat_id": tgt_chat_id, "title": clean_st_title, "icon_color": src_icon_color}
                if src_icon_emoji_id:
                    create_kwargs["icon_emoji_id"] = src_icon_emoji_id
                created = await app.create_forum_topic(**create_kwargs)
                new_tgt_topic_id = extract_topic_id_from_result(created)
                if new_tgt_topic_id:
                    print(f"[TopicMirror] ✅ Created brand new topic '{clean_st_title}' (ID: {new_tgt_topic_id}) via high-level API")
            except Exception as hl_err:
                print(f"[TopicMirror] create_forum_topic notice for '{clean_st_title}': {hl_err}")

            # Attempt 2: Raw RPC ONLY if Attempt 1 failed to produce a topic ID
            if not new_tgt_topic_id:
                try:
                    peer = await app.resolve_peer(tgt_chat_id)
                    rpc_kwargs = dict(
                        peer=peer,
                        title=clean_st_title,
                        icon_color=src_icon_color,
                        random_id=random.randint(1000000, 9999999)
                    )
                    if src_icon_emoji_id:
                        rpc_kwargs["icon_emoji_id"] = src_icon_emoji_id
                    res = await app.invoke(raw.functions.messages.CreateForumTopic(**rpc_kwargs))
                    new_tgt_topic_id = extract_topic_id_from_result(res)
                    if new_tgt_topic_id:
                        print(f"[TopicMirror] ✅ Created brand new topic '{clean_st_title}' (ID: {new_tgt_topic_id}) via raw RPC")
                except Exception as rpc_create_err:
                    print(f"[TopicMirror] ⚠️ CreateForumTopic RPC failed for '{clean_st_title}': {rpc_create_err}")

            verified_id = new_tgt_topic_id
            if not verified_id:
                await asyncio.sleep(1.5)
                verify_topics, verify_by_id = await get_all_target_forum_topics(userbot, app, tgt_chat_id)
                target_topics_by_title.update(verify_topics)
                target_topics_by_id.update(verify_by_id)
                verified_id = (
                    match_existing_target_topic(clean_st_title, verify_topics)
                    or match_existing_target_topic(st_title, verify_topics)
                )

                # Post-RPC-create scan
                if new_tgt_topic_id:
                    await asyncio.sleep(1.5)
                    verify_topics2, verify_by_id2 = await get_all_target_forum_topics(userbot, app, tgt_chat_id)
                    target_topics_by_title.update(verify_topics2)
                    target_topics_by_id.update(verify_by_id2)
                    verified_id = (
                        match_existing_target_topic(clean_st_title, verify_topics2)
                        or match_existing_target_topic(st_title, verify_topics2)
                        or new_tgt_topic_id
                    )

            if verified_id:
                topic_map[st_id] = verified_id
                _register_topic(target_topics_by_title, target_topics_by_id, clean_st_title, verified_id)
                _register_topic(target_topics_by_title, target_topics_by_id, st_title, verified_id)
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, verified_id, st_title)
                print(f"[TopicMirror] 📌 Mapped src topic '{clean_st_title}' ({st_id}) → tgt topic ({verified_id})")
            else:
                if st_id == 1 or norm_title in ("general", "1"):
                    topic_map[st_id] = 1
                    await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, 1, clean_st_title)
                else:
                    print(f"[TopicMirror] ⚠️ Topic '{clean_st_title}' FAILED to create — ensure bot has 'Manage Topics' admin rights in target!")











            # If single topic mode is active, strictly filter topic_map so ONLY detected_topic_id is processed
        if not mirror_all_topics and detected_topic_id:
            topic_map = {k: v for k, v in topic_map.items() if k == detected_topic_id}
            if forced_tgt_topic_id:
                topic_map[detected_topic_id] = forced_tgt_topic_id

        total_topics_count = len(topic_map)

        await status_msg.edit(
            f"✅ **Phase 1 Complete:** Mapped `{total_topics_count}` Topics (0 Duplicates)!\n\n"
            f"⚡ **Starting Rapid Extraction:** Mirroring pending messages...\n\n"
            f"*(Use buttons below to Skip Topic or Cancel Mirror)*",
            reply_markup=control_kb
        )

        # Send Session Start Log to LOG_GROUP
        log_chat = get_log_group()
        if log_chat:
            try:
                await app.send_message(
                    chat_id=log_chat,
                    text=(
                        f"🚀 **[TOPIC MIRROR SESSION STARTED]**\n\n"
                        f"👤 **User ID:** `{user_id}`\n"
                        f"📤 **Source Group:** `{src_title}` (`{src_chat_id}`)\n"
                        f"📥 **Target Group:** `{tgt_title}` (`{tgt_chat_id}`)\n"
                        f"📁 **Total Topics Discovered:** `{len(topic_map)}`"
                    )
                )
            except Exception as log_err:
                print(f"[TopicMirror] Start log notice: {log_err}")

        # -------------------------------------------------------------
        # PHASE 2: EXTRACT & MIRROR MESSAGES TOPIC BY TOPIC (WITH RESUME)
        # -------------------------------------------------------------
        overall_copied = 0
        overall_failed = 0
        overall_skipped = 0
        overall_transferred_bytes = 0
        topic_stats = {}

        current_topic_index = 0
        start_overall_time = time.time()

        for src_topic_id, tgt_topic_id in list(topic_map.items()):
            if not tgt_topic_id:
                continue
            if tgt_topic_id == 1 and src_topic_id != 1 and normalize_topic_title(topic_names.get(src_topic_id, "")) not in ("general", "1"):
                print(f"[TopicMirror] ⚠️ Skipping extraction for topic '{topic_names.get(src_topic_id)}' mapped improperly to General topic.")
                continue
            current_state = active_mirrors.get(user_id, {})
            if not current_state.get("running", False):
                break

            current_topic_index += 1
            topic_title = topic_names.get(src_topic_id, f"Topic {src_topic_id}")
            current_state["current_topic"] = topic_title
            current_state["skip_topic"] = False
            topic_stats[src_topic_id] = {"copied": 0, "failed": 0, "skipped": 0, "title": topic_title}

            try:
                # Ensure userbot client is connected before fetching topic messages
                await ensure_userbot_connected(userbot)

                # Always fetch FRESH checkpoint from MongoDB per-topic (not stale startup snapshot)
                # This guarantees accurate resume even after bot restart mid-mirror
                fresh_session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
                fresh_topics_data = fresh_session.get("topics", {})
                saved_checkpoint = fresh_topics_data.get(str(src_topic_id), {}).get("last_msg_id", 0)
                highest_ckpt = await get_highest_topic_checkpoint(src_chat_id, src_topic_id, tgt_chat_id, saved_checkpoint)
                if highest_ckpt > saved_checkpoint:
                    saved_checkpoint = highest_ckpt

                print(f"[TopicMirror] Topic '{topic_title}' → checkpoint: {saved_checkpoint}, target topic: {tgt_topic_id}")

                # Rapidly fetch messages for this topic with checkpoint cutoff
                if src_start_id is not None and src_start_id > 0:
                    fetch_cutoff = max(0, src_start_id - 1)
                else:
                    fetch_cutoff = saved_checkpoint
                all_topic_messages = await fetch_all_messages_for_topic(userbot, src_chat_id, src_topic_id, min_msg_id=fetch_cutoff)

                # Filter pending messages to copy (respecting range + checkpoint)
                effective_start = max(saved_checkpoint, src_start_id - 1 if src_start_id else 0)
                if src_end_id and src_end_id > 0:
                    messages_to_copy = [m for m in all_topic_messages if m.id > effective_start and m.id <= src_end_id]
                else:
                    messages_to_copy = [m for m in all_topic_messages if m.id > effective_start]
                already_done_count = len(all_topic_messages) - len(messages_to_copy)
                topic_stats[src_topic_id]["skipped"] = already_done_count
                overall_skipped += already_done_count

                total_msgs_in_topic = len(messages_to_copy)

                if total_msgs_in_topic == 0:
                    print(f"[TopicMirror] Topic '{topic_title}' already up to date ({already_done_count} msgs). Skipping.")
                    continue

                # Scan target topic content IDs for smart deduplication & zero-skip continuation
                synced_caption_ids = await scan_target_topic_content_ids(app, userbot, tgt_chat_id, tgt_topic_id)


                # Instant Extraction Start without heavy pre-loop file sizing
                topic_copied_bytes = 0
                last_edit_time = time.time()
                topic_start_time = time.time()

                for idx, msg in enumerate(messages_to_copy, 1):
                    # Check cancellation or skip signal
                    current_state = active_mirrors.get(user_id, {})
                    if not current_state.get("running", False):
                        break
                    if current_state.get("skip_topic", False):
                        print(f"[TopicMirror] User requested skipping topic '{topic_title}' at msg {idx}/{total_msgs_in_topic}")
                        current_state["skip_topic"] = False
                        break

                    # Skip service/action messages
                    if getattr(msg, "service", False) or getattr(msg, "empty", False) or getattr(msg, "action", None) or getattr(msg, "forum_topic_created", None) or getattr(msg, "pinned_message", None):
                        await db.update_mirror_topic_checkpoint(src_chat_id, tgt_chat_id, src_topic_id, msg.id)
                        continue

                    # Check caption content ID match (PDF ID, Video ID, etc.) for seamless continuation
                    msg_cap = (msg.caption or msg.text or "") if msg else ""
                    src_content_ids = extract_caption_content_ids(msg_cap)
                    if src_content_ids and synced_caption_ids and src_content_ids.issubset(synced_caption_ids):
                        print(f"[TopicMirror] Source msg {msg.id} content IDs {src_content_ids} already synced in target topic {tgt_topic_id}. Resuming next.")
                        topic_stats[src_topic_id]["skipped"] += 1
                        overall_skipped += 1
                        await db.update_mirror_topic_checkpoint(src_chat_id, tgt_chat_id, src_topic_id, msg.id)
                        continue

                    msg_size = get_msg_size(msg)

                    # Auto-retry transfer up to 5 times on transient errors or FloodWaits
                    success = False
                    method = "failed"
                    sent_msg_id = None

                    for attempt in range(1, 6):
                        try:
                            await ensure_userbot_connected(userbot)
                            # CRITICAL: Never pass None as tgt_topic_id — it sends to General
                            # Only pass None for the actual General topic (id=1), otherwise always pass the real topic ID
                            effective_tgt_topic_id = None if (tgt_topic_id == 1) else tgt_topic_id
                            if effective_tgt_topic_id is None and tgt_topic_id not in (1, None):
                                # tgt_topic_id is some non-1 value but became None — this is a bug guard
                                print(f"[TopicMirror] ⚠️ tgt_topic_id={tgt_topic_id} invalid for topic '{topic_title}'. Skipping msg {msg.id}.")
                                success, method, sent_msg_id = False, "invalid_topic", None
                                break
                            success, method, sent_msg_id = await transfer_single_message(
                                userbot=userbot,
                                app=app,
                                src_chat_id=src_chat_id,
                                tgt_chat_id=tgt_chat_id,
                                tgt_topic_id=effective_tgt_topic_id,
                                msg=msg,
                                user_id=user_id
                            )
                            if success or method in ("service_skipped", "skipped_filter"):
                                break

                        except FloodWait as fw:
                            print(f"[TopicMirror] FloodWait {fw.value}s on msg {msg.id}. Sleeping...")
                            await asyncio.sleep(fw.value + 1)
                        except Exception as transfer_err:
                            print(f"[TopicMirror] Message {msg.id} transfer attempt {attempt}/5 error: {transfer_err}")
                            if attempt < 5:
                                await asyncio.sleep(2)
                            else:
                                success, method, sent_msg_id = False, str(transfer_err), None


                    if success:
                        if method != "service_skipped":
                            overall_copied += 1
                            topic_stats[src_topic_id]["copied"] += 1
                            topic_copied_bytes += msg_size
                            overall_transferred_bytes += msg_size

                            # Auto-pin the FIRST transferred message of this topic
                            if topic_stats[src_topic_id]["copied"] == 1 and sent_msg_id:
                                try:
                                    await app.pin_chat_message(
                                        chat_id=tgt_chat_id,
                                        message_id=sent_msg_id,
                                        disable_notification=True
                                    )
                                    await asyncio.sleep(1)
                                    # Auto-delete the "pinned a message" service message inside topic thread
                                    try:
                                        async for sys_m in userbot.get_discussion_replies(tgt_chat_id, tgt_topic_id, limit=5):
                                            if getattr(sys_m, "service", False) or getattr(sys_m, "action", None) or getattr(sys_m, "pinned_message", None):
                                                try:
                                                    await userbot.delete_messages(tgt_chat_id, sys_m.id)
                                                except Exception:
                                                    try:
                                                        await app.delete_messages(tgt_chat_id, sys_m.id)
                                                    except Exception:
                                                        pass
                                    except Exception:
                                        async for sys_m in app.get_chat_history(tgt_chat_id, limit=5):
                                            if getattr(sys_m, "service", False) or getattr(sys_m, "action", None) or getattr(sys_m, "pinned_message", None):
                                                try:
                                                    await app.delete_messages(tgt_chat_id, sys_m.id)
                                                except Exception:
                                                    pass
                                except Exception as pin_err:
                                    print(f"[TopicMirror] First message auto-pin notice for topic {tgt_topic_id}: {pin_err}")
                    else:
                        if method != "skipped_filter":
                            overall_failed += 1
                            topic_stats[src_topic_id]["failed"] += 1

                    # Update checkpoint in MongoDB immediately after message is processed
                    await db.update_mirror_topic_checkpoint(src_chat_id, tgt_chat_id, src_topic_id, msg.id)

                    # Update live high-speed status UI every 3.5 seconds
                    now = time.time()
                    if now - last_edit_time > 3.5:
                        last_edit_time = now
                        topic_elapsed = now - topic_start_time
                        
                        # Calculate real data speed (MB/s / KB/s)
                        speed_bytes_sec = (topic_copied_bytes / topic_elapsed) if topic_elapsed > 0 else 0
                        if speed_bytes_sec > 1024:
                            speed_str = f"{humanbytes(speed_bytes_sec)}/s"
                        else:
                            speed_msgs = (idx / topic_elapsed) if topic_elapsed > 0 else 0
                            speed_str = f"{speed_msgs:.2f} msg/s"
                        
                        percent = int((idx / total_msgs_in_topic) * 100) if total_msgs_in_topic > 0 else 0
                        bar_blocks = int(percent // 10)
                        progress_bar_str = "▰" * bar_blocks + "▱" * (10 - bar_blocks)
                        
                        # Dynamic ETA calculation based on messages processed
                        remaining_msgs = total_msgs_in_topic - idx
                        speed_msgs = (idx / topic_elapsed) if topic_elapsed > 0 else 0
                        eta_seconds = (remaining_msgs / speed_msgs) if speed_msgs > 0 else 0
                        eta_str = TimeFormatter(int(eta_seconds * 1000)) if eta_seconds > 0 else "00:00:00"

                        status_text = (
                            f"⚡️ <b>Xtracting...</b>\n\n"
                            f"📁 <b>Topic [{current_topic_index}/{total_topics_count}]:</b> <code>{topic_title}</code>\n"
                            f"📥 <b>Target:</b> <code>{tgt_title}</code>\n\n"
                            f"📊 <b>Progress:</b> [{progress_bar_str}] {percent}%\n"
                            f"🔢 <b>Pending:</b> <code>{idx}/{total_msgs_in_topic}</code>\n"
                            f"🚀 <b>Speed:</b> <code>{speed_str}</code>\n"
                            f"⏳ <b>ETA:</b> <code>{eta_str}</code>\n\n"
                            f"✅ Downloaded: {overall_copied} | ⏩ Skipped: {overall_skipped}\n"
                            f"❌ Failed: {overall_failed}"
                        )
                        try:
                            await status_msg.edit(status_text, parse_mode=ParseMode.HTML, reply_markup=control_kb)
                        except Exception:
                            pass

                    await asyncio.sleep(0.1)

            except Exception as topic_err:
                print(f"[TopicMirror] Error processing topic '{topic_title}': {topic_err}. Continuing to next topic...")


        # -------------------------------------------------------------
        # FINAL REPORT DASHBOARD
        # -------------------------------------------------------------
        breakdown_lines = []
        for tid, stat in topic_stats.items():
            breakdown_lines.append(f"• **{stat['title']}**: ✅ `{stat['copied']}` | ⏩ `{stat['skipped']}` | ❌ `{stat['failed']}`")

        breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "No messages processed."
        is_cancelled = not active_mirrors.get(user_id, {}).get("running", True)
        status_label = "🛑 **Mirror Cancelled by User**" if is_cancelled else "🎉 **Mirror Complete!**"
        total_time_taken = TimeFormatter(int((time.time() - start_overall_time) * 1000))

        final_report = (
            f"{status_label}\n\n"
            f"📤 **From:** `{src_title}`\n"
            f"📥 **To:** `{tgt_title}`\n\n"
            f"📊 **Overall Stats:**\n"
            f"• **Topics Processed:** `{len(topic_stats)}/{total_topics_count}`\n"
            f"• **Total New Downloaded:** ✅ `{overall_copied}`\n"
            f"• **Total Resumed/Skipped:** ⏩ `{overall_skipped}`\n"
            f"• **Total Failed:** ❌ `{overall_failed}`\n"
            f"• **Total Data:** 💾 `{humanbytes(overall_transferred_bytes)}`\n"
            f"• **Total Time:** ⏱️ `{total_time_taken}`\n\n"
            f"📂 **Per-Topic Breakdown:**\n"
            f"{breakdown_text}\n\n"
            f"⚝__**"
        )

        final_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚡ 𝟭-𝗖𝗹𝗶𝗰𝗸 𝗦𝘆𝗻𝗰 & 𝗨𝗽𝗱𝗮𝘁𝗲", callback_data=f"tm_sync_{src_chat_id}_{tgt_chat_id}")],
            [InlineKeyboardButton("🔎 𝗟𝗶𝘃𝗲 𝗦𝗰𝗮𝗻 & 𝗖𝗼𝗺𝗽𝗮𝗿𝗲", callback_data=f"tm_scan_{src_chat_id}_{tgt_chat_id}")],
            [InlineKeyboardButton("🔙 Back to Sessions Hub", callback_data="tm_hub")]
        ])

        final_html = format_caption_to_html(final_report)
        try:
            await status_msg.edit(final_html if final_html else final_report, parse_mode=ParseMode.HTML, reply_markup=final_kb)
        except Exception:
            await app.send_message(user_id, final_html if final_html else final_report, parse_mode=ParseMode.HTML, reply_markup=final_kb)

        # Send Completion Report to LOG_GROUP
        log_chat = get_log_group()
        if log_chat:
            try:
                await app.send_message(
                    chat_id=log_chat,
                    text=f"📋 **[TOPIC MIRROR FINAL REPORT]**\n\n{final_report}"
                )
            except Exception as log_err:
                print(f"[TopicMirror] Finish log notice: {log_err}")

        # Send Clean Completion Message to Target Forum Group (General Topic only)
        try:
            elapsed_total = time.time() - start_time
            target_group_msg = (
                "<blockquote><b>✅ 𝗖ꪮ𝗺𝗽𝗹𝗲𝘁𝗲 𝗛ꪮ 𝗚𝗮𝘆𝗮 𝗕ꪮ$$ 😎</b>\n\n"
                f"📁 <b>New Files Downloaded:</b> <code>{overall_copied}</code> files\n"
                f"⏩ <b>Already Up-to-date:</b> <code>{overall_skipped}</code> files\n"
                f"⏱ <b>Time Taken:</b> <code>{TimeFormatter(int(elapsed_total)*1000)}</code></blockquote>"
            )
            
            # Send STRICTLY to General Topic (reply_to_message_id=1 or direct)
            sent_to_gen = False
            try:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=target_group_msg,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=1
                )
                sent_to_gen = True
            except Exception:
                pass

            if not sent_to_gen:
                try:
                    await app.send_message(
                        chat_id=tgt_chat_id,
                        text=target_group_msg,
                        parse_mode=ParseMode.HTML
                    )
                except Exception as e:
                    print(f"[TopicMirror] Could not send completion msg to general topic: {e}")

            print(f"[TopicMirror] Sent completion message to General topic in target group {tgt_chat_id}")
        except Exception as tgt_msg_err:
            print(f"[TopicMirror] Failed to send target group completion msg: {tgt_msg_err}")



    except Exception as general_err:
        print(f"[TopicMirror] General error: {general_err}")
        try:
            await status_msg.edit(f"❌ **Topic Mirror Failed with Error:**\n`{general_err}`")
        except Exception:
            pass
    finally:
        active_mirrors.pop(user_id, None)
        if is_temp_userbot and userbot:
            try:
                await userbot.stop()
            except Exception:
                pass


@app.on_message(filters.service)
async def auto_delete_group_service_messages(_, message):
    """
    Auto-deletes all group service messages:
    - New Member Join / Leave notifications (new_chat_members, left_chat_member)
    - Pinned Message notifications
    - Forum Topic created / edited / closed / reopened notifications
    - Group title / photo change notifications
    """
    try:
        if message and message.chat and message.chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            await message.delete()
            print(f"[ServiceMsgDelete] ✅ Auto-deleted service message {getattr(message, 'id', None)} in chat {message.chat.id}")
    except Exception as e:
        pass




@app.on_chat_member_updated()
async def on_group_member_update(_, event):
    """
    Automatically tracks when bot joins or is made Admin in a group,
    logging the group and updating active target sessions in MongoDB.
    """
    try:
        if not event or not event.chat:
            return
        chat = event.chat
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
            chat_id = chat.id
            title = chat.title or str(chat_id)
            new_member = event.new_chat_member
            if new_member and new_member.user and new_member.user.is_self:
                if new_member.status in (enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER):
                    await db.add_joined_chat(chat_id, title)
                    # Check if group bio auto-update is applicable
                    try:
                        from toxic.core.mongo.db import get_custom_group_bio
                        target_bio = await get_custom_group_bio()
                        await app.set_chat_description(chat_id, target_bio)
                    except Exception:
                        pass
                    print(f"[GroupEvents] ✅ Bot active in group: '{title}' ({chat_id})")
    except Exception as e:
        print(f"[GroupEvents] on_group_member_update notice: {e}")


