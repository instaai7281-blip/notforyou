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


def parse_topic_link(link: str):
    """
    Parses a Telegram topic link to extract (chat_id, topic_id).
    Supports:
    - https://t.me/c/1234567890/100/500 -> (-1001234567890, 100)
    - https://t.me/c/1234567890/100 -> (-1001234567890, 100)
    - https://t.me/username/100/500 -> ('username', 100)
    - https://t.me/username/100 -> ('username', 100)
    - tg://openmessage?chat_id=-1001234567890&topic_id=100 -> (-1001234567890, 100)
    """
    if not link:
        return None, None
    try:
        clean_link = link.strip()
        if "tg://openmessage" in clean_link:
            chat_match = re.search(r'chat_id=(-?\d+)', clean_link)
            topic_match = re.search(r'topic_id=(\d+)', clean_link)
            msg_match = re.search(r'message_id=(\d+)', clean_link)
            chat_id = int(chat_match.group(1)) if chat_match else None
            topic_id = int(topic_match.group(1)) if topic_match else (int(msg_match.group(1)) if msg_match else 1)
            return chat_id, topic_id

        clean_link = re.sub(r'https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', clean_link)
        parts = [p for p in clean_link.split('/') if p]
        if not parts:
            return None, None

        if parts[0] == 'c':
            chat_id = int("-100" + parts[1])
            if len(parts) >= 4:
                return chat_id, int(parts[2])
            elif len(parts) == 3:
                return chat_id, int(parts[2])
            elif len(parts) == 2:
                return chat_id, 1
        else:
            chat_id = parts[0]
            if len(parts) >= 3 and parts[1].isdigit():
                return chat_id, int(parts[1])
            elif len(parts) == 2 and parts[1].isdigit():
                return chat_id, int(parts[1])
    except Exception as e:
        print(f"[TopicMirror] parse_topic_link error: {e}")
    return None, None


DIAMOND_EMOJI_ID = 5312389333909511107

def clean_topic_title(title: str) -> str:
    """Cleans topic title by removing leading diamond emoji prefixes or clutter, preserving the pure title text."""
    if not title:
        return "Topic"
    clean = str(title).strip()
    clean = re.sub(r'^[💎\s]+', '', clean).strip()
    return clean or "Topic"

format_topic_title_with_diamond = clean_topic_title



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
    """Extracts purely letters and numbers for fail-safe topic matching."""
    if not title:
        return ""
    return re.sub(r'[^a-zA-Z0-9]+', '', str(title)).lower()


def match_existing_target_topic(st_title: str, target_topics_by_title: dict) -> int:
    """Matches a source topic title against existing target topics using multi-level matching."""
    if not st_title or not target_topics_by_title:
        return None
    
    exact = st_title.strip().lower()
    norm = normalize_topic_title(st_title)
    alpha = alphanumeric_topic_title(st_title)

    # 1. Exact match
    if exact in target_topics_by_title:
        return target_topics_by_title[exact]
    
    # 2. Normalized match
    if norm in target_topics_by_title:
        return target_topics_by_title[norm]
    
    # 3. Alphanumeric match
    if alpha and alpha in target_topics_by_title:
        return target_topics_by_title[alpha]
    
    # 4. Partial word-set match
    st_words = set(re.findall(r'\w+', st_title.lower()))
    if len(st_words) >= 2:
        for key, tid in target_topics_by_title.items():
            key_words = set(re.findall(r'\w+', str(key).lower()))
            if st_words == key_words or (len(key_words) >= 2 and st_words.issubset(key_words)):
                return tid

    return None


async def get_highest_topic_checkpoint(src_chat_id: int, src_topic_id: int, current_saved_checkpoint: int = 0) -> int:
    """
    Finds the highest last_msg_id checkpoint for a source topic across ALL MongoDB sessions
    for this source chat ID, ensuring extraction never duplicates already copied posts.
    """
    highest = current_saved_checkpoint
    try:
        from toxic.core.mongo.db import mirror_db
        async for doc in mirror_db.find({"src_chat_id": src_chat_id}):
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


async def get_all_target_forum_topics(userbot, app, tgt_chat_id):
    """
    Scans ALL existing forum topics in target supergroup trying both userbot and app.
    Returns: (topics_by_normalized_title, topics_by_id)
    """
    topics_by_norm_title = {}
    topics_by_id = {}

    clients_to_try = []
    if userbot:
        clients_to_try.append(userbot)
    if app and app not in clients_to_try:
        clients_to_try.append(app)

    for client in clients_to_try:
        try:
            async for t in client.get_forum_topics(tgt_chat_id):
                if t and getattr(t, "title", None) and getattr(t, "message_thread_id", None):
                    t_title = t.title
                    tid = t.message_thread_id
                    norm = normalize_topic_title(t_title)
                    alpha = alphanumeric_topic_title(t_title)
                    exact = t_title.strip().lower()

                    topics_by_norm_title[norm] = tid
                    topics_by_norm_title[exact] = tid
                    if alpha:
                        topics_by_norm_title[alpha] = tid
                    topics_by_id[tid] = t_title
        except Exception as e:
            print(f"[TopicMirror] client.get_forum_topics scan notice: {e}")

        try:
            peer = await client.resolve_peer(tgt_chat_id)
            offset_date = 0
            offset_id = 0
            offset_topic = 0
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
                for t in topics:
                    if not getattr(t, "id", None):
                        continue
                    t_title = getattr(t, "title", "")
                    tid = t.id
                    norm = normalize_topic_title(t_title)
                    alpha = alphanumeric_topic_title(t_title)
                    exact = t_title.strip().lower()

                    topics_by_norm_title[norm] = tid
                    topics_by_norm_title[exact] = tid
                    if alpha:
                        topics_by_norm_title[alpha] = tid
                    topics_by_id[tid] = t_title
                    offset_date = getattr(t, "date", 0)
                    offset_id = tid
                    offset_topic = tid
                if len(topics) < 100:
                    break
        except Exception as rpc_err:
            print(f"[TopicMirror] Raw GetForumTopics pagination notice: {rpc_err}")

        if topics_by_norm_title:
            break

    return topics_by_norm_title, topics_by_id


async def fetch_all_messages_for_topic(userbot, src_chat_id, topic_id: int, min_msg_id: int = 0, max_limit: int = 5000):
    """
    Rapidly fetches pending messages for a topic.
    If min_msg_id > 0 (resuming from checkpoint), stops scanning immediately once older messages are reached.
    """
    collected_messages = []
    seen_ids = set()

    # Strategy 1: get_discussion_replies (Fastest for forum topics)
    if topic_id and topic_id != 1:
        try:
            async for m in userbot.get_discussion_replies(src_chat_id, topic_id, limit=max_limit):
                if not m or m.id in seen_ids:
                    continue
                # If resuming and reached older/already-saved message, stop immediately!
                if min_msg_id > 0 and m.id <= min_msg_id:
                    break
                seen_ids.add(m.id)
                collected_messages.append(m)
        except Exception as disc_err:
            print(f"[TopicMirror] get_discussion_replies notice for topic {topic_id}: {disc_err}")

    # Strategy 2: Raw RPC GetReplies (Fallback)
    if not collected_messages and topic_id and topic_id != 1:
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
                    min_id=min_msg_id if min_msg_id > 0 else 0,
                    hash=0
                ))
                raw_msgs = getattr(res, "messages", [])
                if not raw_msgs:
                    break
                new_found = 0
                reached_min = False
                for rm in raw_msgs:
                    if min_msg_id > 0 and getattr(rm, 'id', 0) <= min_msg_id:
                        reached_min = True
                        break
                    parsed_m = await types.Message._parse(userbot, rm, {u.id: u for u in getattr(res, "users", [])}, {c.id: c for c in getattr(res, "chats", [])})
                    if parsed_m and parsed_m.id not in seen_ids:
                        seen_ids.add(parsed_m.id)
                        collected_messages.append(parsed_m)
                        new_found += 1
                if reached_min or new_found == 0:
                    break
                offset_id = raw_msgs[-1].id
        except Exception as rpc_err:
            print(f"[TopicMirror] Raw GetReplies notice for topic {topic_id}: {rpc_err}")

    # Strategy 3: General topic or Fallback get_chat_history scan
    if not collected_messages:
        try:
            async for m in userbot.get_chat_history(src_chat_id, limit=max_limit):
                if not m or m.id in seen_ids:
                    continue
                if min_msg_id > 0 and m.id <= min_msg_id:
                    break
                if topic_id == 1:
                    m_thread = getattr(m, "message_thread_id", None)
                    reply_to = getattr(m, "reply_to_message_id", None)
                    if m_thread in (None, 1) and (not reply_to or reply_to == 1):
                        seen_ids.add(m.id)
                        collected_messages.append(m)
                else:
                    m_thread = getattr(m, "message_thread_id", None)
                    reply_to = getattr(m, "reply_to_message_id", None)
                    if m_thread == topic_id or reply_to == topic_id:
                        seen_ids.add(m.id)
                        collected_messages.append(m)
        except Exception as scan_err:
            print(f"[TopicMirror] get_chat_history scan notice for topic {topic_id}: {scan_err}")

    # Sort messages chronologically (oldest first)
    collected_messages.sort(key=lambda x: x.id)
    return collected_messages


async def transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id: int):
    """
    Transfers a single message using server-side copy first, with full extraction fallback
    (download, metadata extraction, auto-thumbnail, watermark, caption cleaning, and upload).
    Checks user media filters and settings. Filters service/empty messages.
    """
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

    # 1. First Attempt: Fast server-side copy via userbot or app
    try:
        try:
            copied_m = await userbot.copy_message(
                chat_id=tgt_chat_id,
                from_chat_id=src_chat_id,
                message_id=msg.id,
                reply_to_message_id=tgt_topic_id
            )
            sent_id = getattr(copied_m, 'id', None)
            log_chat = get_log_group()
            if log_chat:
                try:
                    await app.copy_message(chat_id=log_chat, from_chat_id=src_chat_id, message_id=msg.id)
                except Exception:
                    pass
            return True, "copied", sent_id
        except Exception as forward_err:
            err_str = str(forward_err).upper()
            if "CHAT_FORWARDS_RESTRICTED" not in err_str and "CHATFORWARDSRESTRICTED" not in err_str:
                try:
                    copied_m = await app.copy_message(
                        chat_id=tgt_chat_id,
                        from_chat_id=src_chat_id,
                        message_id=msg.id,
                        reply_to_message_id=tgt_topic_id
                    )
                    sent_id = getattr(copied_m, 'id', None)
                    log_chat = get_log_group()
                    if log_chat:
                        try:
                            await app.copy_message(chat_id=log_chat, from_chat_id=src_chat_id, message_id=msg.id)
                        except Exception:
                            pass
                    return True, "copied", sent_id
                except Exception:
                    pass
            raise forward_err

    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)

    except Exception as e:
        # 2. Restricted / Protected Content Fallback: Download via userbot & Upload to target topic
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
                log_chat = get_log_group()
                if log_chat and sent_txt:
                    try:
                        await sent_txt.copy(log_chat)
                    except Exception:
                        pass
                return True, "text_sent", sent_id
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)
            except Exception as txt_err:
                print(f"[TopicMirror] Failed to send text msg {msg.id}: {txt_err}")
                return False, str(txt_err), None


        # If message contains media:
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
                return False, "Download failed"

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
            log_chat = get_log_group()
            if log_chat and sent_media:
                try:
                    await sent_media.copy(log_chat)
                except Exception as log_err:
                    print(f"[TopicMirror] Media log copy notice: {log_err}")

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


def build_session_action_keyboard(src_chat_id: int, tgt_chat_id: int) -> InlineKeyboardMarkup:
    """Builds action options for a selected saved mirror session."""
    return InlineKeyboardMarkup([
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
        source_topics = []
        try:
            async for forum_topic in userbot.get_forum_topics(src_chat_id):
                source_topics.append({
                    "id": forum_topic.message_thread_id,
                    "title": forum_topic.title
                })
        except Exception:
            try:
                peer = await userbot.resolve_peer(src_chat_id)
                res = await userbot.invoke(raw.functions.messages.GetForumTopics(
                    peer=peer, offset_date=0, offset_id=0, offset_topic=0, limit=100
                ))
                for t in getattr(res, "topics", []):
                    source_topics.append({"id": t.id, "title": t.title})
            except Exception:
                source_topics = [{"id": 1, "title": "General"}]

        if not source_topics:
            source_topics = [{"id": 1, "title": "General"}]

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
            highest_ckpt = await get_highest_topic_checkpoint(src_chat_id, st_id, last_msg_id)
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
        f"Choose an option below to continue mirroring, change target chat ID, or delete this session:"
    )
    html_text = format_caption_to_html(text)
    await query.message.edit_text(
        html_text if html_text else text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_session_action_keyboard(src_chat_id, tgt_chat_id)
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
        err_active = "⚠️ **A mirroring operation is already running!** Send `/cancel_mirror` to abort it first."
        if is_callback:
            await app.send_message(user_id, err_active)
        else:
            await message.reply(err_active)
        return

    # STEP 1: Ask for SOURCE Topic Link
    try:
        prompt_1 = await app.ask(
            user_id,
            "🔗 **Send the SOURCE Topic link:**\n\n"
            "*(e.g., `https://t.me/c/1234567890/100/500` or `https://t.me/c/1234567890/100`)*\n\n"
            "Send `/cancel` to abort.",
            timeout=180
        )
    except Exception as e:
        err_text = "❌ **Interactive Prompt Failed:**\nPlease start the bot first in private DM (@" + (await app.get_me()).username + ")!"
        if is_callback:
            await app.send_message(user_id, err_text)
        else:
            await message.reply(err_text)
        return

    if prompt_1.text == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    src_link = prompt_1.text.strip()
    src_chat_id, src_topic_id = parse_topic_link(src_link)

    if not src_chat_id or not src_topic_id:
        await app.send_message(user_id, "❌ **Invalid Source Topic link format.** Could not extract Group ID or Topic ID.")
        return

    # STEP 2: Ask for TARGET Topic Link
    try:
        prompt_2 = await app.ask(
            user_id,
            "🎯 **Send the TARGET Topic link (where content should be sent):**\n\n"
            "*(e.g., `https://t.me/c/9876543210/200/50` or `https://t.me/c/9876543210/200`)*\n\n"
            "Send `/cancel` to abort.",
            timeout=180
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Session timed out or error: {e}")
        return

    if prompt_2.text == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    tgt_link = prompt_2.text.strip()
    tgt_chat_id, tgt_topic_id = parse_topic_link(tgt_link)

    if not tgt_chat_id or not tgt_topic_id:
        await app.send_message(user_id, "❌ **Invalid Target Topic link format.** Could not extract Target Group ID or Topic ID.")
        return

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

    await app.send_message(
        user_id,
        f"🚀 **Direct Topic-to-Topic Link Mirror Initialized!**\n\n"
        f"📤 **Source Chat:** `{src_chat_id}` | **Topic ID:** `{src_topic_id}`\n"
        f"📥 **Target Chat:** `{tgt_chat_id}` | **Topic ID:** `{tgt_topic_id}`\n\n"
        f"Starting extraction..."
    )

    await run_topic_mirror(
        user_id=user_id,
        src_chat_id=src_chat_id,
        tgt_chat_id=tgt_chat_id,
        mirror_all_topics=False,
        detected_topic_id=src_topic_id,
        forced_tgt_topic_id=tgt_topic_id
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
        async for t in userbot.get_forum_topics(src_chat_id):
            topics.append((t.message_thread_id, t.title))
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
        async for t in userbot.get_forum_topics(src_chat_id):
            topics.append((t.message_thread_id, t.title))
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


async def run_topic_mirror(user_id: int, src_chat_id: int, tgt_chat_id: int, mirror_all_topics: bool = True, detected_topic_id: int = None, forced_tgt_topic_id: int = None, status_msg=None, force_sync: bool = False):
    """Core execution engine for topic mirroring with instant resume, rapid extraction, and force sync."""
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
        # PHASE 1: DISCOVER SOURCE TOPICS & MAP WITHOUT DUPLICATES
        # -------------------------------------------------------------
        saved_session = await db.get_mirror_session(src_chat_id, tgt_chat_id)
        saved_topics = saved_session.get("topics", {})

        topic_map = {}   # src_topic_id -> tgt_topic_id
        topic_names = {} # src_topic_id -> title

        # Pre-populate already mapped topics from MongoDB (rejecting invalid fallback 1s for non-general topics)
        if saved_topics:
            for st_id_str, info in saved_topics.items():
                try:
                    s_id = int(st_id_str)
                    tgt_id = info.get("tgt_topic_id")
                    t_title = info.get("title", f"Topic {s_id}")
                    # Only pre-populate if valid AND non-general topic is NOT mapped to 1
                    if tgt_id and (s_id == 1 or normalize_topic_title(t_title) in ("general", "1") or tgt_id != 1):
                        topic_map[s_id] = tgt_id
                        topic_names[s_id] = t_title
                except Exception:
                    pass

        # If forced_tgt_topic_id is set (Direct Topic Link Mirroring)
        if forced_tgt_topic_id is not None and detected_topic_id is not None:
            st_title = f"Topic {detected_topic_id}"
            try:
                async for forum_topic in userbot.get_forum_topics(src_chat_id):
                    if forum_topic.message_thread_id == detected_topic_id:
                        st_title = forum_topic.title
                        break
            except Exception:
                pass
            topic_map[detected_topic_id] = forced_tgt_topic_id
            topic_names[detected_topic_id] = st_title
            await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, detected_topic_id, forced_tgt_topic_id, st_title)

        source_topics = []
        # Strategy 1: Userbot get_forum_topics
        try:
            async for forum_topic in userbot.get_forum_topics(src_chat_id):
                source_topics.append({
                    "id": forum_topic.message_thread_id,
                    "title": forum_topic.title,
                    "icon_color": getattr(forum_topic, "icon_color", None),
                    "icon_emoji_id": getattr(forum_topic, "icon_emoji_id", None)
                })
        except Exception as scan_err:
            print(f"[TopicMirror] Userbot get_forum_topics scan notice: {scan_err}")

        # Strategy 2: App get_forum_topics or Raw RPC GetForumTopics
        if not source_topics:
            try:
                async for forum_topic in app.get_forum_topics(src_chat_id):
                    source_topics.append({
                        "id": forum_topic.message_thread_id,
                        "title": forum_topic.title,
                        "icon_color": getattr(forum_topic, "icon_color", None),
                        "icon_emoji_id": getattr(forum_topic, "icon_emoji_id", None)
                    })
            except Exception:
                try:
                    peer = await userbot.resolve_peer(src_chat_id)
                    res = await userbot.invoke(raw.functions.messages.GetForumTopics(
                        peer=peer,
                        offset_date=0,
                        offset_id=0,
                        offset_topic=0,
                        limit=100
                    ))
                    for t in getattr(res, "topics", []):
                        source_topics.append({
                            "id": t.id,
                            "title": t.title,
                            "icon_color": getattr(t, "icon_color", None),
                            "icon_emoji_id": getattr(t, "icon_emoji_id", None)
                        })
                except Exception as rpc_err:
                    print(f"[TopicMirror] Raw RPC GetForumTopics failed: {rpc_err}")

        # Strategy 3: Message History Topic Discovery (if get_forum_topics returned empty)
        if not source_topics and detected_topic_id:
            source_topics.append({"id": detected_topic_id, "title": f"Topic {detected_topic_id}", "icon_color": None, "icon_emoji_id": None})

        if not mirror_all_topics and detected_topic_id:
            source_topics = [t for t in source_topics if t["id"] == detected_topic_id]
            if not source_topics:
                source_topics = [{"id": detected_topic_id, "title": f"Topic {detected_topic_id}", "icon_color": None, "icon_emoji_id": None}]

        if not source_topics:
            source_topics = [{"id": 1, "title": "General", "icon_color": None, "icon_emoji_id": None}]

        # Scan target topics to match existing topics in target supergroup
        target_topics_by_title, target_topics_by_id = await get_all_target_forum_topics(userbot, app, tgt_chat_id)

        for st in source_topics:
            st_id = st["id"]
            st_title = st["title"].strip()
            topic_names[st_id] = st_title
            norm_title = normalize_topic_title(st_title)

            # 1. Already mapped from memory (only if not mapped improperly to 1 for non-general topic)
            if st_id in topic_map and (st_id == 1 or norm_title in ("general", "1") or topic_map[st_id] != 1):
                continue

            # 2. General topic (id 1) always maps to target General topic (1)
            if st_id == 1 or norm_title in ("general", "1"):
                topic_map[st_id] = 1
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, 1, st_title)
                continue

            # 3. Check persistent MongoDB session FIRST (rejecting bad fallback 1s for non-general topics)
            saved_info = saved_topics.get(str(st_id))
            if saved_info and saved_info.get("tgt_topic_id"):
                existing_tgt_id = saved_info["tgt_topic_id"]
                if existing_tgt_id == 1 and st_id != 1 and norm_title not in ("general", "1"):
                    print(f"[TopicMirror] Correcting bad saved mapping (1) for non-general topic '{st_title}'...")
                else:
                    topic_map[st_id] = existing_tgt_id
                    continue

            # 4. Check if target group already has a topic with matching title (Multi-level match)
            existing_tgt_id = match_existing_target_topic(st_title, target_topics_by_title)
            if existing_tgt_id:
                topic_map[st_id] = existing_tgt_id
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, existing_tgt_id, st_title)
                continue

            # 5. Fresh re-scan right before creating a new topic to prevent ANY duplicate topic creation
            fresh_target_topics, _ = await get_all_target_forum_topics(userbot, app, tgt_chat_id)
            existing_tgt_id = match_existing_target_topic(st_title, fresh_target_topics)
            if existing_tgt_id:
                topic_map[st_id] = existing_tgt_id
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, existing_tgt_id, st_title)
                continue

            # 6. Only if topic does NOT exist anywhere, create a NEW topic in target supergroup with clean title
            new_tgt_topic_id = None
            clean_st_title = clean_topic_title(st_title)
            try:
                created = await app.create_forum_topic(
                    chat_id=tgt_chat_id,
                    title=clean_st_title,
                    icon_color=0x6FB9F0
                )
                new_tgt_topic_id = created.message_thread_id
            except Exception as create_err:
                try:
                    peer = await app.resolve_peer(tgt_chat_id)
                    res = await app.invoke(raw.functions.messages.CreateForumTopic(
                        peer=peer,
                        title=clean_st_title,
                        icon_color=0x6FB9F0,
                        random_id=random.randint(1000000, 9999999)
                    ))
                    for upd in getattr(res, "updates", []):
                        if hasattr(upd, "message_thread_id"):
                            new_tgt_topic_id = upd.message_thread_id
                            break
                        elif hasattr(upd, "id"):
                            new_tgt_topic_id = upd.id
                            break
                except Exception as rpc_create_err:
                    print(f"[TopicMirror] CreateForumTopic failed for '{clean_st_title}': {create_err} / {rpc_create_err}")

            if new_tgt_topic_id:
                topic_map[st_id] = new_tgt_topic_id
                target_topics_by_title[norm_title] = new_tgt_topic_id
                target_topics_by_title[clean_st_title.lower()] = new_tgt_topic_id
                await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, new_tgt_topic_id, clean_st_title)
            else:
                if st_id == 1 or norm_title in ("general", "1"):
                    topic_map[st_id] = 1
                    await db.save_mirror_topic_mapping(src_chat_id, tgt_chat_id, st_id, 1, clean_st_title)
                else:
                    print(f"[TopicMirror] ⚠️ Topic '{clean_st_title}' could not be created or mapped to target. Make sure bot has 'Manage Topics' admin rights in target group!")


        # Asynchronously update target topic titles (removing 💎 text) & setting 💎 custom emoji icon in background!
        async def background_topic_icon_update():
            for s_id, t_id in topic_map.items():
                if t_id and t_id != 1:
                    t_title = clean_topic_title(topic_names.get(s_id, f"Topic {s_id}"))
                    try:
                        peer = await app.resolve_peer(tgt_chat_id)
                        await app.invoke(raw.functions.messages.EditForumTopic(
                            peer=peer,
                            topic_id=t_id,
                            title=t_title,
                            icon_emoji_id=DIAMOND_EMOJI_ID
                        ))
                    except Exception:
                        try:
                            await app.edit_forum_topic(
                                chat_id=tgt_chat_id,
                                message_thread_id=t_id,
                                title=t_title,
                                icon_emoji_id=DIAMOND_EMOJI_ID
                            )
                        except Exception as py_err:
                            print(f"[TopicMirror] Topic {t_id} icon update notice: {py_err}")
                    await asyncio.sleep(0.1)

        asyncio.create_task(background_topic_icon_update())





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

        for src_topic_id, tgt_topic_id in topic_map.items():
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

                # Check last copied message ID from MongoDB checkpoint (with cross-session failsafe)
                saved_checkpoint = saved_topics.get(str(src_topic_id), {}).get("last_msg_id", 0)
                if not force_sync:
                    highest_ckpt = await get_highest_topic_checkpoint(src_chat_id, src_topic_id, saved_checkpoint)
                    if highest_ckpt > saved_checkpoint:
                        saved_checkpoint = highest_ckpt

                # Rapidly fetch messages for this topic with checkpoint cutoff (0 if force_sync)
                fetch_cutoff = 0 if force_sync else saved_checkpoint
                all_topic_messages = await fetch_all_messages_for_topic(userbot, src_chat_id, src_topic_id, min_msg_id=fetch_cutoff)
                
                # Filter pending messages to copy
                messages_to_copy = [m for m in all_topic_messages if m.id > saved_checkpoint]
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
                            success, method, sent_msg_id = await transfer_single_message(
                                userbot=userbot,
                                app=app,
                                src_chat_id=src_chat_id,
                                tgt_chat_id=tgt_chat_id,
                                tgt_topic_id=tgt_topic_id if tgt_topic_id != 1 else None,
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
                                    print(f"[TopicMirror] 📌 Auto-pinned first message ({sent_msg_id}) in topic {tgt_topic_id}")
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
                            f"╔══━⚡️ **Topic Mirroring in Progress** ⚡️━══╗\n"
                            f" ┉━┉━┉━┉┉━┉━┉━┉┉━┉━\n"
                            f"> 📁 **Topic [{current_topic_index}/{total_topics_count}]:** `{topic_title}`\n"
                            f"> 📥 **Routing To:** `{tgt_title} → {topic_title}`\n\n"
                            f"> 📊 **Topic Progress:** {progress_bar_str} `{percent}%`\n"
                            f"> 🔢 **Pending Messages:** `{idx}/{total_msgs_in_topic}`\n"
                            f"> ⚡ **Transfer Speed:** `{speed_str}`\n"
                            f"> ⏳ **Topic ETA:** `{eta_str}`\n\n"
                            f"> ✅ **New Copied:** `{overall_copied}` | ⏩ **Resumed/Skipped:** `{overall_skipped}`\n"
                            f"> ❌ **Failed:** `{overall_failed}` | 🛡️ **Bypass & Clean:** `Active`\n"
                            f" ╚═══━━━─⚝─━━━═══╝\n\n"
                            f"⚝__**"
                        )
                        status_html = format_caption_to_html(status_text)
                        try:
                            await status_msg.edit(status_html if status_html else status_text, parse_mode=ParseMode.HTML, reply_markup=control_kb)
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
            f"• **Total New Copied:** ✅ `{overall_copied}`\n"
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

        # Send Stylish Completion Summary to Target Forum Group
        try:
            STUDY_QUOTES = [
                "📖 <i>\"Success isn't given. It's earned. In the library, on the desk, with every page turned.\"</i> 💫",
                "⚡ <i>\"Don't stop when you're tired. Stop when you're done! Keep grinding.\"</i> 🚀",
                "🎯 <i>\"The expert in anything was once a beginner. Focus on your goal!\"</i> ✨",
                "🔥 <i>\"Hard work beats talent when talent doesn't work hard. Study smart!\"</i> 💡",
                "📚 <i>\"Your future self is watching you right now through memories. Make them proud!\"</i> 👑",
                "🏆 <i>\"Push yourself, because no one else is going to do it for you.\"</i> 🌟",
                "🚀 <i>\"Dream big, work hard, stay focused, and surround yourself with good energy.\"</i> 💎",
                "🧠 <i>\"Consistency is the key to mastering any subject. Small steps daily!\"</i> 🎓",
                "📖 <i>\"Work hard in silence, let your success be your noise.\"</i> 💬",
                "🌟 <i>\"The beautiful thing about learning is that nobody can take it away from you.\"</i> ⚡",
                "🎓 <i>\"Discipline is choosing between what you want now and what you want most.\"</i> 🎯",
                "💫 <i>\"Believe in yourself and all that you are. Great things take time.\"</i> 🔮",
                "🔥 <i>\"Doubt kills more dreams than failure ever will. Believe & Achieve!\"</i> 🦁",
                "✨ <i>\"Study like there is no tomorrow, so you can live tomorrow like you always wanted!\"</i> 🚀",
                "👑 <i>\"The harder you work for something, the greater you'll feel when you achieve it.\"</i> 🏆"
            ]
            random_quote = random.choice(STUDY_QUOTES)
            target_group_msg = (
                "<blockquote><b>✅ 𝗖ꪮ𝗺𝗽𝗹𝗲𝘁𝗲 𝗛ꪮ 𝗚𝗮𝘆𝗮 𝗕ꪮ$$ 😎</b></blockquote>\n\n"
                f"• <b>Total New Uploaded/Updated:</b> ✅ <code>{overall_copied}</code> files\n"
                f"• <b>Total Topics Processed:</b> 📂 <code>{len(topic_stats)}/{total_topics_count}</code>\n"
                f"• <b>Total Data Volume:</b> 💾 <code>{humanbytes(overall_transferred_bytes)}</code>\n"
                f"• <b>Duration:</b> ⏱️ <code>{total_time_taken}</code>\n\n"
                "<blockquote><b>✅ All pending content has been successfully synced & updated!</b></blockquote>\n\n"
                f"<b>💡 Daily Motivation:</b>\n{random_quote}"
            )
            try:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=target_group_msg,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=1
                )
            except Exception:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=target_group_msg,
                    parse_mode=ParseMode.HTML
                )
            print(f"[TopicMirror] Sent completion summary to target group {tgt_chat_id}")
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


