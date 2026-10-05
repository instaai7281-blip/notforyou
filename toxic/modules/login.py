# ---------------------------------------------------
# File Name: login.py
# Description: Interactive Userbot Authentication & Session Management Module
# ---------------------------------------------------

import os
import random
import string
import asyncio
from pyrogram import filters, Client
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
        from toxic.core.mongo.db import db as user_data_db
        await user_data_db.update_one({"_id": user_id}, {"$unset": {"session": ""}})
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

    # Check if user is already logged in
    user_data = await db.get_data(user_id) or {}
    session_string = user_data.get("session")

    if session_string:
        status_card = (
            "📱 <b>USERBOT ACCOUNT CONTROL PANEL</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
            "⚡ <b>Session Status:</b> <code>CONNECTED & ACTIVE ✅</code>\n"
            "🛡️ <b>Database Security:</b> <code>Encrypted Session String</code>\n\n"
            "ℹ️ <i>Your Userbot session is active and ready to access private/restricted source channels for cloning!</i>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Use the control buttons below to manage your account session:"
        )
        await message.reply_text(
            status_card,
            parse_mode=ParseMode.HTML,
            reply_markup=get_login_status_keyboard(is_logged_in=True)
        )
        return

    # If not logged in, proceed to login flow directly
    await start_login_flow(client, user_id, message)


@app.on_callback_query(filters.regex(r"^login_(relogin|start_cb|logout_cb|close_cb)$"))
async def login_callback_handler(client, query: CallbackQuery):
    user_id = query.from_user.id
    data = query.data

    if data == "login_close_cb":
        await query.message.delete()
        return

    if data == "login_logout_cb":
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
    except Exception:
        await app.send_message(user_id, "⏱ <b>Prompt timed out!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        return

    if not number or number.text == "/cancel":
        await app.send_message(user_id, "❌ <b>Login process cancelled.</b>", parse_mode=ParseMode.HTML)
        return

    phone_number = number.text.strip()

    sending_msg = await app.send_message(user_id, "📲 <b>Connecting to Telegram servers & sending OTP...</b>", parse_mode=ParseMode.HTML)
    
    ub_client = Client(f"session_{user_id}", api_id, api_hash, max_concurrent_transmissions=16)

    try:
        await ub_client.connect()
    except Exception as e:
        await sending_msg.edit(f"❌ <b>Connection failed:</b> `{e}`\n\nPlease wait a moment and try again using <code>/login</code>.", parse_mode=ParseMode.HTML)
        return

    try:
        code = await ub_client.send_code(phone_number)
    except ApiIdInvalid:
        await sending_msg.edit("❌ <b>Invalid API ID / API HASH configuration.</b> Please contact admin.", parse_mode=ParseMode.HTML)
        return
    except PhoneNumberInvalid:
        await sending_msg.edit("❌ <b>Invalid phone number!</b> Please restart using <code>/login</code> with valid country code.", parse_mode=ParseMode.HTML)
        return
    except Exception as err:
        await sending_msg.edit(f"❌ <b>OTP Request Error:</b> `{err}`", parse_mode=ParseMode.HTML)
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
    except Exception:
        await app.send_message(user_id, "⏱ <b>OTP prompt timed out!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        return

    if not otp_code or otp_code.text == "/cancel":
        await app.send_message(user_id, "❌ <b>Login process cancelled.</b>", parse_mode=ParseMode.HTML)
        return

    phone_code = otp_code.text.replace(" ", "").strip()

    try:
        await ub_client.sign_in(phone_number, code.phone_code_hash, phone_code)
    except PhoneCodeInvalid:
        await app.send_message(user_id, "❌ <b>Invalid OTP code entered!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
        return
    except PhoneCodeExpired:
        await app.send_message(user_id, "❌ <b>Expired OTP code!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
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
        except Exception:
            await app.send_message(user_id, "⏱ <b>Password prompt timed out!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
            return

        if not two_step_msg or two_step_msg.text == "/cancel":
            await app.send_message(user_id, "❌ <b>Login process cancelled.</b>", parse_mode=ParseMode.HTML)
            return

        try:
            password = two_step_msg.text.strip()
            await ub_client.check_password(password=password)
        except PasswordHashInvalid:
            await two_step_msg.reply_text("❌ <b>Invalid 2FA password!</b> Please restart using <code>/login</code>.", parse_mode=ParseMode.HTML)
            return
        except Exception as pwd_err:
            await two_step_msg.reply_text(f"❌ <b>2FA Authentication Error:</b> `{pwd_err}`", parse_mode=ParseMode.HTML)
            return

    # Export session string and save in MongoDB
    string_session = await ub_client.export_session_string()
    await db.set_session(user_id, string_session)

    try:
        await ub_client.disconnect()
    except Exception:
        pass

    success_card = (
        "🎉 <b>USERBOT LOGIN SUCCESSFUL!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 <b>Authenticated User:</b> <code>{user_id}</code>\n"
        "⚡ <b>Session Status:</b> <code>SAVED IN DATABASE ✅</code>\n\n"
        "🚀 <b>Unlocked Capabilities:</b>\n"
        "• 📁 Topic-to-Topic Supergroup Cloning\n"
        "• 📥 Restricted & Private Content Downloads\n"
        "• ⚡ Zero-Bandwidth High-Speed Server Forwarding\n\n"
        "<i>Use <code>/clone</code> or <code>/mirror</code> to start cloning your topics!</i>"
    )
    await app.send_message(
        user_id,
        success_card,
        parse_mode=ParseMode.HTML,
        reply_markup=get_login_status_keyboard(is_logged_in=True)
    )
