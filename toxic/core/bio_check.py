# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification middleware & Chat Join Request handler for @Crazy_for_Goals
# Author: Antigravity
# ---------------------------------------------------

import logging
import html
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
    user_name = html.escape(message.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
    
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
        f"Hey {user_mention} 👋 Aapka Request abhi pending me hai...\n\n"
        "Join karne ke liye bas ye 2 simple steps follow karo 😊:\n"
        "──────────────\n"
        " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
        "Apne Bio me ye Tag Lagao 👇\n\n"
        f"<blockquote>● <code>{REQUIRED_TAG}</code> ♡</blockquote>\n"
        "<i>(Tap karke copy kar lo 👆)</i>\n\n"
        " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
        "Bio update karne ke baad niche <b>🟢 Verify Bio 🔄</b> button par tap kar do, instant Access mil jayega! 🚀\n"
        "──────────────"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ Open Settings", url="tg://settings"), InlineKeyboardButton("🟢 Verify Bio 🔄", callback_data="verify_user_bio")],
        [InlineKeyboardButton("📢 Main Channel", url="https://t.me/Crazy_for_Goals"), InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
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
    user_name = html.escape(request.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

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
            f"<b><blockquote> Welcome to <a href='tg://user?id={user_id}'>{chat_title}</a> ! 🎉</blockquote></b>\n"
            "Aapka Bio verify ho gaya hai aur aapka join request approve kar diya gaya hai! 🥰\n\n"
            f"⚠️ <i>Note: Bio me <code>{REQUIRED_TAG}</code> tag hamesha rakhein. 📑</i>"
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
            "🔒 <b>Access Denied ❌</b>\n\n"
            f"Hey {user_mention} 👋 Aapka Request for <b>{chat_title}</b> abhi pending me hai...\n\n"
            "Join karne ke liye bas ye 2 simple steps follow karo 😊:\n"
            "──────────────\n"
            " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
            "Apne Bio me ye Tag Lagao 👇\n\n"
            f"<blockquote>● <code>{REQUIRED_TAG}</code> ♡</blockquote>\n"
            "<i>(Tap karke copy kar lo 👆)</i>\n\n"
            " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
            "Bio update karne ke baad niche <b>🟢 Verify Bio 🔄</b> button par tap kar do, instant Access mil jayega! 🚀\n"
            "──────────────"
        )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Open Settings", url="tg://settings"), InlineKeyboardButton("🟢 Verify Bio 🔄", callback_data="verify_user_bio")],
            [InlineKeyboardButton("📢 Main Channel", url="https://t.me/Crazy_for_Goals"), InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
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
        await callback_query.answer("🔓 Access Granted! Tera Bio Verify ho gaya. 🎉", show_alert=True)
        
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
            f"<b><blockquote> Welcome, <a href='tg://user?id={user_id}'>{user_name}</a> ! 🥂</blockquote></b>\n"
            "Tera profile Bio successfully verify ho gaya hai bro! 🎉\n\n"
        )
        if approved_chats:
            approve_text += f"✅ Join Request Approved for: <b>{', '.join(approved_chats)}</b>!\n\n"
        approve_text += (
            "Ab tu bot and channel access kar sakta hai. 🥰\n\n"
            f"⚠️ <i>Note: Agar Bio se <code>{REQUIRED_TAG}</code> hataya to access firse deny ho jayega. 📑</i>\n\n"
            "👉 <b>Send /start to proceed!</b>"
        )
        try:
            await callback_query.message.edit_text(approve_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            pass
    else:
        await callback_query.answer(
            f"❌ Access Denied!\n\nBio me '{REQUIRED_TAG}' tag nahi mila bro.\nPlease bio update karke firse Verify Bio button par click kar.",
            show_alert=True
        )
