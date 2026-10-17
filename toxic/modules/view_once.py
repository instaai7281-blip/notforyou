# ---------------------------------------------------
# File Name: view_once.py
# Description: Automatic View-Once (Self-Destructing Media) Saver Module for Userbot & Bot
# Author: Antigravity
# ---------------------------------------------------

import os
import time
import asyncio
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from toxic import app
from toxic.core.mongo import db
from config import API_ID, API_HASH

logger = logging.getLogger(__name__)

# Active background listener userbots for view-once saver: user_id -> Client
active_viewonce_listeners = {}

async def is_view_once_enabled(user_id: int) -> bool:
    """Check if view-once auto-saving is enabled for this user."""
    data = await db.get_data(user_id)
    if data:
        return data.get("view_once_saver", True) # Default enabled once logged in
    return True

async def set_view_once_setting(user_id: int, enabled: bool):
    """Toggle view-once saving setting."""
    data = await db.get_data(user_id)
    if data and data.get("_id"):
        await db.db.update_one({"_id": user_id}, {"$set": {"view_once_saver": enabled}}, upsert=True)
    else:
        await db.db.insert_one({"_id": user_id, "view_once_saver": enabled})

async def format_sender_caption(message: Message, media_type: str = "Photo") -> str:
    """Creates a beautiful, clean caption with sender info."""
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

    orig_caption = message.caption or ""
    orig_caption_text = f"\n\n💬 <b>Original Caption:</b>\n<i>{orig_caption}</i>" if orig_caption else ""

    bot_name = app.me.username if app.me else "Bot"
    caption = (
        f"🔥 <b>Saved View-Once {media_type}!</b> ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Sender Name:</b> <code>{sender_name}</code>\n"
        f"🔗 <b>Username:</b> {sender_user}\n"
        f"🆔 <b>User ID:</b> <code>{sender_id}</code>\n"
        f"🕒 <b>Received At:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S')}</code>"
        f"{orig_caption_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ <i>Saved permanently by @{bot_name}</i>"
    )
    return caption

async def register_view_once_listener(user_id: int, session_string: str):
    """Starts a dedicated Pyrogram listener on the user's account to capture incoming or self-sent view-once media."""
    if user_id in active_viewonce_listeners:
        existing = active_viewonce_listeners[user_id]
        if getattr(existing, "is_connected", False):
            return existing

    try:
        ub = Client(
            f"viewonce_ub_{user_id}",
            api_id=API_ID,
            api_hash=API_HASH,
            session_string=session_string,
            in_memory=True,
            no_updates=False # MUST receive live updates to catch incoming view-once messages
        )

        @ub.on_message((filters.private | filters.chat("me")) & (filters.photo | filters.video | filters.voice | filters.video_note | filters.document))
        async def on_private_incoming_media(client: Client, message: Message):
            try:
                # 1. Check if user turned setting off
                if not await is_view_once_enabled(user_id):
                    return

                # 2. Check if view-once / expiring media (TTL > 0)
                has_ttl = (
                    getattr(getattr(message, "photo", None), "ttl_seconds", None) or
                    getattr(getattr(message, "video", None), "ttl_seconds", None) or
                    getattr(getattr(message, "voice", None), "ttl_seconds", None) or
                    getattr(getattr(message, "video_note", None), "ttl_seconds", None) or
                    getattr(getattr(message, "document", None), "ttl_seconds", None) or
                    getattr(message, "ttl_period", None)
                )

                # Skip normal permanent media (only process self-destructing / view-once media)
                if not has_ttl:
                    return

                # Prevent infinite loops if media was already tagged/saved
                if message.caption and "Saved permanently by" in message.caption:
                    return

                # Determine media type
                if message.photo:
                    media_type = "Photo"
                elif message.video:
                    media_type = "Video"
                elif message.voice:
                    media_type = "Voice"
                elif getattr(message, "video_note", None):
                    media_type = "Video Note"
                else:
                    media_type = "Document"

                sender_id_str = str(message.from_user.id) if message.from_user else "unknown"
                logger.info(f"[VIEW-ONCE] 🎯 Detected view-once {media_type} for user {user_id} (TTL: {has_ttl}s) from {sender_id_str}")

                caption = await format_sender_caption(message, media_type)

                # Download media immediately before it expires
                temp_dir = os.path.join("downloads", f"vo_{user_id}")
                os.makedirs(temp_dir, exist_ok=True)

                downloaded_file = await client.download_media(message, file_name=f"{temp_dir}/")
                if not downloaded_file or not os.path.exists(downloaded_file) or os.path.getsize(downloaded_file) == 0:
                    logger.error(f"[VIEW-ONCE] ❌ Failed to download view-once media for user {user_id}")
                    return

                logger.info(f"[VIEW-ONCE] 📥 Downloaded view-once file: {downloaded_file} ({os.path.getsize(downloaded_file)} bytes)")

                # 1. Send permanently to User's Saved Messages ("me") without any TTL!
                try:
                    target_dest = "me"
                    if message.photo:
                        await client.send_photo(target_dest, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif message.video:
                        await client.send_video(target_dest, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif message.voice:
                        await client.send_voice(target_dest, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif getattr(message, "video_note", None):
                        await client.send_video_note(target_dest, downloaded_file)
                    else:
                        await client.send_document(target_dest, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    logger.info(f"[VIEW-ONCE] ✅ Saved view-once {media_type} to Saved Messages for user {user_id}")
                except Exception as save_err:
                    logger.error(f"[VIEW-ONCE] Failed to send to 'me', retrying with numeric id: {save_err}")
                    try:
                        me_obj = await client.get_me()
                        if message.photo:
                            await client.send_photo(me_obj.id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                        elif message.video:
                            await client.send_video(me_obj.id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                        elif message.voice:
                            await client.send_voice(me_obj.id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                        elif getattr(message, "video_note", None):
                            await client.send_video_note(me_obj.id, downloaded_file)
                        else:
                            await client.send_document(me_obj.id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                        logger.info(f"[VIEW-ONCE] ✅ Saved view-once {media_type} via numeric id for user {user_id}")
                    except Exception as fallback_err:
                        logger.error(f"[VIEW-ONCE] Fallback send to userbot id failed: {fallback_err}")

                # 2. ALSO deliver a copy directly to User via Bot DM so they never miss it!
                try:
                    if message.photo:
                        await app.send_photo(user_id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif message.video:
                        await app.send_video(user_id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif message.voice:
                        await app.send_voice(user_id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    elif getattr(message, "video_note", None):
                        await app.send_video_note(user_id, downloaded_file)
                    else:
                        await app.send_document(user_id, downloaded_file, caption=caption, parse_mode=enums.ParseMode.HTML)
                    logger.info(f"[VIEW-ONCE] ✅ Delivered view-once {media_type} to Bot DM for user {user_id}")
                except Exception as bot_send_err:
                    logger.error(f"[VIEW-ONCE] Bot DM delivery notice: {bot_send_err}")

                # Clean up local downloaded file
                try:
                    if os.path.exists(downloaded_file):
                        os.remove(downloaded_file)
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"[VIEW-ONCE] Error processing incoming view-once media: {e}")

        await ub.start()
        active_viewonce_listeners[user_id] = ub
        logger.info(f"✅ View-Once auto-saver started for user {user_id}")
        return ub

    except Exception as e:
        logger.error(f"Failed to start View-Once listener for user {user_id}: {e}")
        return None


async def load_all_view_once_listeners():
    """Scans all users with saved sessions on startup and registers their view-once listeners."""
    try:
        from toxic.core.mongo.db import db as user_db
        cursor = user_db.find({"session": {"$exists": True, "$ne": None}})
        count = 0
        async for doc in cursor:
            uid = doc.get("_id")
            s_str = doc.get("session")
            is_enabled = doc.get("view_once_saver", True)
            if uid and s_str and is_enabled:
                try:
                    asyncio.create_task(register_view_once_listener(uid, s_str))
                    count += 1
                except Exception as e:
                    logger.error(f"Error restoring view-once listener for {uid}: {e}")
        print(f"[VIEW-ONCE] Successfully restored {count} view-once auto-saver listeners on boot!")
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
    if is_enabled and user_id not in active_viewonce_listeners:
        asyncio.create_task(register_view_once_listener(user_id, session_str))

    panel_text = (
        "🔥 <b>TELEGRAM VIEW-ONCE AUTO-SAVER</b> ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>Status:</b> <code>{status_text}</code>\n"
        "🛡️ <b>Destination:</b> <code>Your Saved Messages + Bot DM</code>\n\n"
        "✨ <b>Features:</b>\n"
        "• Koi bhi private DM ya Saved Messages me <b>View-Once Photo/Video</b> bhejega, to wo expire hone se pehle auto-download ho jayegi.\n"
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
        asyncio.create_task(register_view_once_listener(user_id, session_str))
    elif not new_status:
        ub = active_viewonce_listeners.pop(user_id, None)
        if ub:
            try:
                await ub.stop()
            except Exception:
                pass

    await callback_query.answer(f"View-Once Saver {'Activated ✅' if new_status else 'Deactivated ❌'}", show_alert=True)
    status_text = "🟢 ACTIVE & RUNNING" if new_status else "🔴 TURNED OFF"
    toggle_btn_text = "🔴 Turn OFF Saver" if new_status else "🟢 Turn ON Saver"

    panel_text = (
        "🔥 <b>TELEGRAM VIEW-ONCE AUTO-SAVER</b> ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ <b>Status:</b> <code>{status_text}</code>\n"
        "🛡️ <b>Destination:</b> <code>Your Saved Messages + Bot DM</code>\n\n"
        "✨ <b>Features:</b>\n"
        "• Koi bhi private DM ya Saved Messages me <b>View-Once Photo/Video</b> bhejega, to wo expire hone se pehle auto-download ho jayegi.\n"
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
    
    # Try auto-connecting if session exists but not in active map
    if user_id not in active_viewonce_listeners:
        user_data = await db.get_data(user_id) or {}
        session_str = user_data.get("session")
        if session_str and await is_view_once_enabled(user_id):
            await register_view_once_listener(user_id, session_str)

    is_active = user_id in active_viewonce_listeners and getattr(active_viewonce_listeners[user_id], "is_connected", False)
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
