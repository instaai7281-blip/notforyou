# ---------------------------------------------------
# File Name: login.py
# Description: Interactive Userbot Authentication & Session Management Module
# ---------------------------------------------------

import os
import random
import string
import asyncio
import logging
from pyrogram import filters, Client, errors

logger = logging.getLogger(__name__)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    ApiIdInvalid,
    PhoneNumberInvalid,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    SessionPasswordNeeded,
    PasswordHashInvalid,
    FloodWait
)

from toxic import app
from toxic.core.mongo import db
from toxic.core.func import subscribe, chk_user
from config import API_ID as api_id, API_HASH as api_hash


def generate_random_name(length=7):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


async def delete_session_files(user_id: int) -> bool:
    session_file = f"session_{user_id}.session"
    memory_file = f"session_{user_id}.session-journal"

    session_file_exists = os.path.exists(session_file)
    memory_file_exists = os.path.exists(memory_file)

    if session_file_exists:
        try:
            os.remove(session_file)
        except Exception:
            pass

    if memory_file_exists:
        try:
            os.remove(memory_file)
        except Exception:
            pass

    try:
        from toxic.core.userbot_manager import close_userbot
        await close_userbot(user_id)
    except Exception:
        pass

    try:
        from toxic.core.userbot_manager import get_current_bot_username
        from toxic.core.mongo.db import remove_user_session
        bot_uname = get_current_bot_username()
        await remove_user_session(user_id, bot_name=bot_uname)
    except Exception:
        pass

    try:
        from toxic.modules.topic_mirror import userbot_sessions
        ub = userbot_sessions.pop(user_id, None)
        if ub:
            try:
                await ub.stop()
            except Exception:
                pass
    except Exception:
        pass

    try:
        from toxic.modules.view_once import active_viewonce_listeners
        vo_ub = active_viewonce_listeners.pop(user_id, None)
        if vo_ub:
            try:
                await vo_ub.stop()
            except Exception:
                pass
    except Exception:
        pass

    return True


def get_login_status_keyboard(is_logged_in: bool):
    if is_logged_in:
        buttons = [
            [
                InlineKeyboardButton("🔄 Switch / Re-Login Account", callback_data="login_relogin"),
                InlineKeyboardButton("🚪 Logout Session", callback_data="login_logout_cb")
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="login_close_cb")
            ]
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("📲 Start Userbot Login", callback_data="login_start_cb")
            ],
            [
                InlineKeyboardButton("❌ Close Panel", callback_data="login_close_cb")
            ]
        ]
    return InlineKeyboardMarkup(buttons)


@app.on_message(filters.command(["logout", "clear_session"]))
async def clear_db(client, message: Message):
    user_id = message.chat.id
    await delete_session_files(user_id)
    
    logout_text = (
        "🚪 <b>LOGOUT SUCCESSFUL!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Your Telegram Userbot session string and temporary files have been permanently cleared from memory and disk.\n\n"
        "<i>Use <code>/login</code> anytime to authenticate a new account session!</i>"
    )
    await message.reply_text(logout_text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["login", "myaccount", "account"]))
async def generate_session(client, message: Message):
    user_id = message.chat.id

    joined = await subscribe(client, message)
    if joined == 1:
        return

    # Check if user is already logged in for THIS specific bot
    try:
        from toxic.core.userbot_manager import get_current_bot_username
        bot_uname = get_current_bot_username()
    except Exception:
        bot_uname = "default_bot"

    session_string = await db.get_user_session(user_id, bot_name=bot_uname, allow_fallback=False)

    if session_string:
        # Retrieve live details of the connected userbot account
        from toxic.core.userbot_manager import get_active_userbot_sync, get_or_create_userbot
        ub = get_active_userbot_sync(user_id)
        if not ub:
            try:
                ub = await get_or_create_userbot(user_id, session_string)
            except Exception:
                pass

        ub_me = None
        if ub and getattr(ub, "is_connected", False):
            try:
                ub_me = await ub.get_me()
            except Exception:
                pass

        user_doc = await db.get_data(user_id) or {}
        sessions_dict = user_doc.get("sessions") or {}

        if ub_me:
            acc_name = f"{ub_me.first_name} {ub_me.last_name or ''}".strip()
            acc_uname = f"@{ub_me.username}" if ub_me.username else "<i>No Username</i>"
            acc_id = ub_me.id
            raw_phone = getattr(ub_me, "phone_number", None) or user_doc.get("phone")
            acc_phone = f"+{raw_phone}" if raw_phone else "<i>Hidden / Protected</i>"
            acc_type = "Telegram Premium ⭐" if getattr(ub_me, "is_premium", False) else "Standard Account"
        else:
            acc_name = "Connected Account"
            acc_uname = "<i>Active</i>"
            acc_id = user_id
            raw_phone = user_doc.get("phone")
            acc_phone = f"+{raw_phone}" if raw_phone else "<i>Protected Session</i>"
            acc_type = "Active Session"

        # Check all bots connected for this user
        other_bots_lines = []
        if isinstance(sessions_dict, dict):
            for b_name in sessions_dict.keys():
                status_icon = "🟢" if b_name == bot_uname else "🤖"
                is_curr = " (Current Bot)" if b_name == bot_uname else ""
                other_bots_lines.append(f"{status_icon} <b>@{b_name}</b>{is_curr} ➔ <code>Dedicated Active Session</code>")
        if not other_bots_lines:
            other_bots_lines.append(f"🟢 <b>@{bot_uname}</b> ➔ <code>Active Dedicated Session</code>")

        other_bots_block = "\n".join(other_bots_lines)

        status_card = (
            "📱 <b>USERBOT ACCOUNT DETAILS & CONTROL PANEL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>Connected Account:</b> <code>{acc_name}</code>\n"
            f"🆔 <b>Userbot Telegram ID:</b> <code>{acc_id}</code>\n"
            f"📞 <b>Phone Number:</b> <code>{acc_phone}</code>\n"
            f"🏷️ <b>Username:</b> {acc_uname}\n"
            f"⭐ <b>Account Type:</b> <code>{acc_type}</code>\n"
            f"🤖 <b>Operating On:</b> <code>@{bot_uname}</code>\n"
            f"⚡ <b>Session Status:</b> <code>CONNECTED & ACTIVE ✅</code>\n\n"
            "🌐 <b>Multi-Bot Sessions Overview:</b>\n"
            f"{other_bots_block}\n\n"
            "ℹ️ <i>Each bot operates completely isolated with its own dedicated session. No session conflicts!</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Manage your account session using the buttons below:"
        )
        await message.reply_text(
            status_card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_login_status_keyboard(is_logged_in=True)
        )
        return

    # If not logged in on this bot, check if another bot has a session to show helpful notice
    other_bot_session = await db.get_user_session(user_id, bot_name=bot_uname, allow_fallback=True)
    if other_bot_session:
        notice_card = (
            f"📱 <b>USERBOT SETUP FOR @{bot_uname}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "ℹ️ <b>Multi-Bot Account Support:</b>\n"
            "Aapka dusre bot me already ek account logged in hai.\n"
            "Is bot (@" + bot_uname + ") me aap <b>koi bhi alag number</b> se login kar sakte hain!\n\n"
            "👉 Niche <b>📲 Start Userbot Login</b> par click karke is bot ke liye alag account number connect karein:"
        )
        await message.reply_text(
            notice_card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_login_status_keyboard(is_logged_in=False)
        )
        return

    # If completely not logged in anywhere, proceed to login flow directly
    await start_login_flow(client, user_id, message)


@app.on_callback_query(filters.regex(r"^login_(relogin|start_cb|logout_cb|close_cb)$"))
async def login_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "login_close_cb":
        await query.message.delete()
        return

    if data == "login_logout_cb":
        try:
            from toxic.core.userbot_manager import close_userbot
            await close_userbot(user_id)
        except Exception:
            pass
        await delete_session_files(user_id)
        await query.answer("🚪 Session logged out successfully!", show_alert=True)
        logout_card = (
            "🚪 <b>USERBOT LOGGED OUT</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "✅ Your session string has been deleted.\n\n"
            "Click below to login a new account anytime:"
        )
        await query.message.edit_text(
            logout_card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_login_status_keyboard(is_logged_in=False)
        )
        return

    if data in ("login_relogin", "login_start_cb"):
        await query.answer("🚀 Starting Userbot Login...")
        await query.message.delete()
        await start_login_flow(client, user_id, query.message)


async def start_login_flow(client, user_id: int, message_or_query):
    """Interactive 3-Step Userbot Authentication Flow with Clean UI Cards."""
    
    # Step 1: Phone Number Prompt
    prompt_1_text = (
        "📱 <b>USERBOT ACCOUNT AUTHENTICATION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 <b>Step 1 of 3 — Phone Number</b>\n"
        "<i>Send your Telegram account phone number with international country code.</i>\n\n"
        "📌 <b>Example:</b> <code>+919876543210</code> or <code>+19876543210</code>\n\n"
        "⚠️ <b>Tip:</b> <i>Use a secondary or extra Telegram account for restricted content cloning.</i>\n\n"
        "❌ Send <code>/cancel</code> to abort authentication."
    )

    try:
        number = await client.ask(
            user_id,
            prompt_1_text,
            filters=filters.text,
            timeout=300,
            parse_mode=ParseMode.HTML
        )
    except errors.FloodWait as fw:
        logger.warning(f"[LOGIN] FloodWait on phone prompt for {user_id}: {fw.value}s")
        return
    except Exception:
        try:
            await app.send_message(user_id, "⏱ <b>Prompt timed out!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    if not number or number.text == "/cancel":
        try:
            await app.send_message(user_id, "❌ <b>Login process cancelled.</b>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    phone_number = number.text.strip()

    try:
        sending_msg = await app.send_message(user_id, "📲 <b>Connecting to Telegram servers & sending OTP...</b>", parse_mode=ParseMode.HTML)
    except errors.FloodWait as fw:
        logger.warning(f"[LOGIN] FloodWait sending connecting status: {fw.value}s")
        return
    
    ub_client = Client(f"session_{user_id}", api_id, api_hash, max_concurrent_transmissions=1, sleep_threshold=60)

    try:
        await ub_client.connect()
    except Exception as e:
        try:
            await sending_msg.edit(f"❌ <b>Connection failed:</b> `{e}`\n\nPlease wait a moment and try again using <code>/login</code>.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    try:
        code = await ub_client.send_code(phone_number)
    except ApiIdInvalid:
        try:
            await sending_msg.edit("❌ <b>Invalid API ID / API HASH configuration.</b> Please contact admin.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    except PhoneNumberInvalid:
        try:
            await sending_msg.edit("❌ <b>Invalid phone number!</b> Please restart using <code>/login</code> with valid country code.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    except errors.FloodWait as fw:
        try:
            await sending_msg.edit(f"⚠️ <b>Telegram Flood Wait ({fw.value}s)</b>\nTelegram server has rate-limited OTP requests on this number. Please wait {fw.value}s before trying again.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    except Exception as err:
        try:
            await sending_msg.edit(f"❌ <b>OTP Request Error:</b> `{err}`", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    # Step 2: OTP Verification Prompt
    prompt_2_text = (
        "📩 <b>USERBOT ACCOUNT AUTHENTICATION</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔑 <b>Step 2 of 3 — OTP Verification Code</b>\n"
        "<i>Check your official Telegram app for the 5-digit verification code sent by Telegram.</i>\n\n"
        "💡 <b>Format Requirement:</b>\n"
        "Please enter the OTP with <b>spaces between digits</b> to prevent Telegram auto-read.\n"
        "• <b>Example:</b> If OTP is <code>12345</code>, send: <code>1 2 3 4 5</code>\n\n"
        "❌ Send <code>/cancel</code> to abort authentication."
    )

    try:
        otp_code = await client.ask(
            user_id,
            prompt_2_text,
            filters=filters.text,
            timeout=600,
            parse_mode=ParseMode.HTML
        )
    except errors.FloodWait as fw:
        logger.warning(f"[LOGIN] FloodWait hit during OTP prompt for {user_id}: {fw.value}s")
        try:
            await app.send_message(user_id, f"⚠️ <b>Telegram Flood Wait ({fw.value}s)</b>\nTelegram server is currently rate-limiting messages. Please try again after {fw.value} seconds.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    except Exception:
        try:
            await app.send_message(user_id, "⏱ <b>OTP prompt timed out!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    if not otp_code or otp_code.text == "/cancel":
        try:
            await app.send_message(user_id, "❌ <b>Login process cancelled.</b>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    phone_code = otp_code.text.replace(" ", "").strip()

    try:
        await ub_client.sign_in(phone_number, code.phone_code_hash, phone_code)
    except PhoneCodeInvalid:
        try:
            await app.send_message(user_id, "❌ <b>Invalid OTP code entered!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    except PhoneCodeExpired:
        try:
            await app.send_message(user_id, "❌ <b>Expired OTP code!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    except SessionPasswordNeeded:
        # Step 3: 2FA Password Required
        prompt_3_text = (
            "🔐 <b>USERBOT ACCOUNT AUTHENTICATION</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🛡️ <b>Step 3 of 3 — 2FA Password Required</b>\n"
            "<i>Your Telegram account has Two-Step Verification enabled.</i>\n\n"
            "Please send your <b>2FA Password</b> below to complete authentication:\n\n"
            "❌ Send <code>/cancel</code> to abort authentication."
        )
        try:
            two_step_msg = await client.ask(
                user_id,
                prompt_3_text,
                filters=filters.text,
                timeout=300,
                parse_mode=ParseMode.HTML
            )
        except errors.FloodWait as fw:
            logger.warning(f"[LOGIN] FloodWait hit during 2FA prompt for {user_id}: {fw.value}s")
            try:
                await app.send_message(user_id, f"⚠️ <b>Telegram Flood Wait ({fw.value}s)</b>\nTelegram server is rate-limiting messages. Please try again later.", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return
        except Exception:
            try:
                await app.send_message(user_id, "⏱ <b>Password prompt timed out!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return

        if not two_step_msg or two_step_msg.text == "/cancel":
            try:
                await app.send_message(user_id, "❌ <b>Login process cancelled.</b>", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return

        try:
            password = two_step_msg.text.strip()
            await ub_client.check_password(password=password)
        except PasswordHashInvalid:
            try:
                await two_step_msg.reply_text("❌ <b>Invalid 2FA password!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return
        except Exception as pwd_err:
            try:
                await two_step_msg.reply_text(f"❌ <b>2FA Authentication Error:</b> `{pwd_err}`", parse_mode=ParseMode.HTML)
            except Exception:
                pass
            return

    # Export session string and save in MongoDB partitioned for THIS bot
    string_session = await ub_client.export_session_string()
    try:
        from toxic.core.userbot_manager import get_current_bot_username
        bot_uname = get_current_bot_username()
    except Exception:
        bot_uname = "default_bot"
    await db.set_session(user_id, string_session, bot_name=bot_uname)

    try:
        await ub_client.disconnect()
    except Exception:
        pass

    # Close any lingering old userbot first, then start unified userbot for this bot
    try:
        from toxic.core.userbot_manager import close_userbot, get_or_create_userbot
        await close_userbot(user_id)
        asyncio.create_task(get_or_create_userbot(user_id, string_session))
    except Exception as vo_err:
        print(f"Failed to auto-start unified userbot on login: {vo_err}")

    success_card = (
        "🎉 <b>USERBOT LOGIN SUCCESSFUL!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Authenticated User:</b> <code>{user_id}</code>\n"
        f"🤖 <b>Dedicated For Bot:</b> <code>@{bot_uname}</code>\n"
        "⚡ <b>Session Status:</b> <code>SAVED IN DATABASE ✅</code>\n\n"
        "🚀 <b>Multi-Bot Parallel Capabilities Unlocked:</b>\n"
        "• Ab aap is bot aur baaki bots se <b>ek sath alag-alag groups</b> me bina session conflict ke simultaneous fast clone kar sakte hain! ⚡\n"
        "• 📁 Topic-to-Topic Supergroup Cloning\n"
        "• 📥 Restricted & Private Content Downloads\n"
        "• 🔥 <b>Automatic View-Once Media Saver Active</b> ⚡\n\n"
        "<i>Ready to mirror! Send /mirror to start cloning.</i>"
    )
    await app.send_message(
        user_id,
        success_card,
        parse_mode=ParseMode.HTML,
        reply_markup=get_login_status_keyboard(is_logged_in=True)
    )
