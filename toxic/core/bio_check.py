# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification middleware for @Crazy_for_Goals
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

    # Bio tag missing -> Prompt user to set bio
    prompt_text = (
        "🔒 <b>Access Denied — Bio Verification Required ❌</b>\n\n"
        f"To use this bot, you must add <code>{REQUIRED_TAG}</code> to your <b>Telegram Profile Bio</b>.\n\n"
        "💡 <b>Follow 3 Simple Steps:</b>\n"
        "1️⃣ Tap <b>Open Settings</b> button below (or go to Settings ➔ Edit Profile ➔ Bio).\n"
        f"2️⃣ Add <code>{REQUIRED_TAG}</code> in your Bio (<i>Tap to Copy</i>).\n"
        "3️⃣ Tap <b>Verify Bio 🔄</b> button after saving your Bio!\n\n"
        "<i>Once verified, all bot features will be instantly unlocked for you!</i>"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Open Settings", url="tg://settings")],
        [InlineKeyboardButton("Verify Bio 🔄", callback_data="verify_user_bio")]
    ])

    try:
        await message.reply_text(prompt_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    except Exception:
        pass

    return False

@app.on_callback_query(filters.regex("^verify_user_bio$"))
async def verify_user_bio_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    try:
        user = await client.get_chat(user_id)
        bio = user.bio or ""
    except Exception as e:
        print(f"[BIO CHECK] Error in callback for {user_id}: {e}")
        bio = ""

    if has_bio_tag(bio):
        await callback_query.answer("✅ Bio Verified! Access Unlocked.", show_alert=True)
        try:
            await callback_query.message.edit_text(
                "✅ <b>Bio Verified Successfully! 🎉</b>\n\n"
                "All features of XTRACTOR BOT PRO are now unlocked for you.\n"
                "Send /start to continue!",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    else:
        await callback_query.answer(
            f"❌ Bio tag missing!\n\nPlease add {REQUIRED_TAG} to your profile Bio and try again.",
            show_alert=True
        )
