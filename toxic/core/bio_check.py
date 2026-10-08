# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification middleware for @Crazy_for_Goals (Bio-main Style)
# Author: Antigravity
# ---------------------------------------------------

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from config import OWNER_ID
from toxic import app

REQUIRED_TAG = "@Crazy_for_Goals"

def has_bio_tag(user_bio: str) -> bool:
    if not user_bio:
        return False
    return REQUIRED_TAG.lower() in user_bio.lower()

async def check_user_bio_access(client: Client, message: Message) -> bool:
    if not message.from_user:
        return True

    user_id = message.from_user.id
    user_mention = message.from_user.mention
    
    # Owners bypass bio check
    if user_id in OWNER_ID:
        return True

    try:
        user = await client.get_chat(user_id)
        bio = user.bio or ""
    except Exception as e:
        print(f"[BIO CHECK] Error fetching user profile for {user_id}: {e}")
        bio = ""

    if has_bio_tag(bio):
        return True

    # Bio-main Style Reject & Guide Prompt
    prompt_text = (
        "🔒 <b>Access Denied ❌</b>\n\n"
        f"Dear <b>{user_mention}</b> 🌞 Your Access is Pending...\n\n"
        "If you want to unlock & access the bot, follow these <b>2 Simple Steps 😊</b>:\n"
        "───────────────────────────────────\n"
        " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
        "Add This 👇 Tag in <b><a href='tg://settings'>Your Bio 👁️</a></b>\n"
        f"<blockquote>● <code>{REQUIRED_TAG}</code> ♡</blockquote>\n"
        "<i>(Tap code to Copy 👆)</i>\n\n"
        " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
        "After updating your bio, tap the <b>Verify Bio 🔄</b> button below to unlock access! 🔗 👇\n"
        "───────────────────────────────────"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Open Settings", url="tg://settings"), InlineKeyboardButton("Verify Bio 🔄", callback_data="verify_user_bio")],
        [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])

    try:
        await message.reply_text(prompt_text, reply_markup=buttons, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception:
        pass

    return False

@app.on_callback_query(filters.regex("^verify_user_bio$"))
async def verify_user_bio_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_name = callback_query.from_user.first_name if callback_query.from_user else "User"

    try:
        user = await client.get_chat(user_id)
        bio = user.bio or ""
    except Exception as e:
        print(f"[BIO CHECK] Error in callback for {user_id}: {e}")
        bio = ""

    if has_bio_tag(bio):
        await callback_query.answer("🔓 Access Granted! Your Bio is Verified. 🎉", show_alert=True)
        approve_text = (
            "🔓 <b>Access Granted ✅</b>\n\n"
            f"<b><blockquote> Cheers, <a href='tg://user?id={user_id}'>{user_name}</a> ! 🥂</blockquote></b>\n"
            "Your profile Bio has been verified successfully! 🎉\n"
            "<b>We’re happy to have you with us. 🥰</b>\n\n"
            f"⚠️ <i>Note: If you remove <code>{REQUIRED_TAG}</code> from your bio, access will be restricted again. Make sure to keep it in your Bio to avoid interruption. 📑</i>\n\n"
            "👉 <b>Send /start to proceed!</b>"
        )
        try:
            await callback_query.message.edit_text(approve_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            pass
    else:
        await callback_query.answer(
            f"❌ Access Denied!\n\nTag '{REQUIRED_TAG}' was not found in your Bio.\nPlease add it in your Bio and tap Verify Bio again.",
            show_alert=True
        )
