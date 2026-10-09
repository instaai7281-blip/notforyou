# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification middleware & Chat Join Request handler for @Crazy_for_Goals
# Author: Antigravity
# ---------------------------------------------------

import logging
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, ChatJoinRequest, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from config import OWNER_ID
from toxic import app, tdb

REQUIRED_TAG = "@Crazy_for_Goals"

# Store pending join requests in MongoDB for instant approval on verification
join_req_db = tdb["pending_join_requests"]

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

@app.on_chat_join_request()
async def handle_chat_join_request(client: Client, request: ChatJoinRequest):
    user_id = request.from_user.id
    chat_id = request.chat.id
    chat_title = request.chat.title or "Channel/Group"
    user_mention = request.from_user.mention

    try:
        user = await client.get_chat(user_id)
        bio = user.bio or ""
    except Exception as e:
        print(f"[JOIN REQ] Could not fetch chat info for user {user_id}: {e}")
        bio = ""

    if has_bio_tag(bio):
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            print(f"[JOIN REQ] Approved user {user_id} in chat {chat_title}")
        except Exception as e:
            print(f"[JOIN REQ] Failed to approve user {user_id}: {e}")

        approve_text = (
            "🔓 <b>Join Request Approved ✅</b>\n\n"
            f"塑造<b><blockquote> Welcome to <a href='tg://user?id={user_id}'>{chat_title}</a> ! 🎉</blockquote></b>\n"
            "Your profile Bio has been verified and your join request is approved! 🥰\n\n"
            f"⚠️ <i>Note: Keep <code>{REQUIRED_TAG}</code> in your Bio to maintain verified status. 📑</i>"
        )
        try:
            await client.send_message(user_id, approve_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            print(f"[JOIN REQ] Could not send DM to approved user {user_id}: {e}")

    else:
        await join_req_db.update_one(
            {"user_id": user_id, "chat_id": chat_id},
            {"$set": {"user_id": user_id, "chat_id": chat_id, "chat_title": chat_title}},
            upsert=True
        )

        prompt_text = (
            "🔒 <b>Join Request Pending ❌</b>\n\n"
            f"Dear <b>{user_mention}</b> 🌞 Your request to join <b>{chat_title}</b> is Pending...\n\n"
            "To get your Join Request approved, follow these <b>2 Simple Steps 😊</b>:\n"
            "───────────────────────────────────\n"
            " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
            "Add This 👇 Tag in <b><a href='tg://settings'>Your Bio 👁️</a></b>\n"
            f"<blockquote>● <code>{REQUIRED_TAG}</code> ♡</blockquote>\n"
            "<i>(Tap code to Copy 👆)</i>\n\n"
            " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
            "After updating your bio, tap the <b>Verify Bio 🔄</b> button below to approve your request instantly! 🔗 👇\n"
            "───────────────────────────────────"
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings", url="tg://settings"), InlineKeyboardButton("Verify Bio 🔄", callback_data="verify_user_bio")],
            [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
        ])

        try:
            await client.send_message(user_id, prompt_text, reply_markup=buttons, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            print(f"[JOIN REQ] Could not send prompt DM to user {user_id}: {e}")


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
        
        pending_requests = await join_req_db.find({"user_id": user_id}).to_list(100)
        approved_chats = []
        for req in pending_requests:
            try:
                await client.approve_chat_join_request(req["chat_id"], user_id)
                approved_chats.append(req.get("chat_title", "Channel"))
                await join_req_db.delete_one({"_id": req["_id"]})
            except Exception as e:
                print(f"[JOIN REQ VERIFY] Failed to approve chat {req['chat_id']}: {e}")

        approve_text = (
            "🔓 <b>Access Granted & Bio Verified ✅</b>\n\n"
            f"<b><blockquote> Cheers, <a href='tg://user?id={user_id}'>{user_name}</a> ! 🥂</blockquote></b>\n"
            "Your profile Bio has been verified successfully! 🎉\n"
        )
        if approved_chats:
            approve_text += f"✅ Approved Join Request for: <b>{', '.join(approved_chats)}</b>!\n\n"
        approve_text += (
            "<b>We’re happy to have you with us. 🥰</b>\n\n"
            f"⚠️ <i>Note: If you remove <code>{REQUIRED_TAG}</code> from your bio, access will be restricted again. Make sure to keep it in your Bio. 📑</i>\n\n"
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
