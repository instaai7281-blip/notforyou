
# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification middleware & Chat Join Request handler for @Crazy_for_Goals
# Author: Antigravity
# ---------------------------------------------------

import logging
import html
import unicodedata

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from pyrogram.enums import ParseMode
from pyrogram.raw import functions

from config import OWNER_ID
from toxic import app, tdb

REQUIRED_TAG = "@Crazy_for_Goals"

# Store pending join requests & channel invite links in MongoDB
join_req_db = tdb["pending_join_requests"]
invite_link_db = tdb["channel_invite_links"]


def has_bio_tag(user_bio: str) -> bool:
    if not user_bio:
        return False

    normalized = unicodedata.normalize("NFKC", user_bio).lower()

    clean_text = "".join(
        c if c.isalnum() or c == "_" else " "
        for c in normalized
    )

    target = "crazy_for_goals"
    target_no_spaces = "crazyforgoals"

    return (
        target in clean_text
        or target_no_spaces in clean_text.replace(" ", "")
    )


async def get_fresh_user_bio(client: Client, user_id: int) -> str:
    """Fetch user bio using Telegram raw API, with fallbacks."""

    try:
        peer = await client.resolve_peer(user_id)
        full_user_res = await client.invoke(
            functions.users.GetFullUser(id=peer)
        )

        if hasattr(full_user_res, "full_user"):
            bio = getattr(full_user_res.full_user, "about", None)
            if bio:
                return bio

    except Exception as e:
        logging.warning(
            "[BIO CHECK] Raw RPC failed for %s: %s",
            user_id,
            e
        )

    try:
        from toxic import pro

        if pro and pro.is_connected:
            peer = await pro.resolve_peer(user_id)
            full_user_res = await pro.invoke(
                functions.users.GetFullUser(id=peer)
            )

            if hasattr(full_user_res, "full_user"):
                bio = getattr(full_user_res.full_user, "about", None)
                if bio:
                    return bio

    except Exception:
        pass

    try:
        user = await client.get_chat(user_id)
        return user.bio or ""

    except Exception as e:
        logging.warning(
            "[BIO CHECK] get_chat failed for %s: %s",
            user_id,
            e
        )
        return ""


async def get_or_create_permanent_join_link(
    client: Client,
    chat_id: int,
    request_link=None,
    chat_obj=None
) -> str:
    """Get or create a non-expiring join-request link."""

    cached = await invite_link_db.find_one({"chat_id": chat_id})

    if cached and cached.get("link"):
        return cached["link"]

    link = ""

    try:
        chat = chat_obj or await client.get_chat(chat_id)

        # Public channel/group link
        if getattr(chat, "username", None):
            link = f"https://t.me/{chat.username}"

        else:
            # Create a non-expiring join-request invite link
            invite = await client.create_chat_invite_link(
                chat_id=chat_id,
                name="Permanent Join Request",
                creates_join_request=True
            )
            link = invite.invite_link

    except Exception as e:
        logging.error(
            "[INVITE LINK] Failed for %s: %s",
            chat_id,
            e
        )

        # Do not reuse an unverified request link as a guaranteed
        # permanent invite link.
        link = ""

    if link:
        await invite_link_db.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "link": link
                }
            },
            upsert=True
        )

    return link


def format_channel_display(
    channel_title: str,
    channel_link: str,
    suffix: str = ""
) -> str:
    """Display channel name and link on separate blockquote lines."""

    safe_title = html.escape(channel_title or "Channel/Group")
    safe_link = html.escape(channel_link or "", quote=True)

    if channel_link:
        return (
            f"<blockquote><b>{safe_title}{suffix}</b>\n"
            f"<a href='{safe_link}'>{safe_link}</a></blockquote>"
        )

    return (
        f"<blockquote><b>{safe_title}{suffix}</b>\n"
        f"Link unavailable</blockquote>"
    )


async def check_user_bio_access(
    client: Client,
    message: Message
) -> bool:
    if not message.from_user:
        return True

    user_id = message.from_user.id
    user_name = html.escape(message.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

    # Owners bypass bio check
    owner_ids = (
        {OWNER_ID}
        if isinstance(OWNER_ID, int)
        else set(OWNER_ID or [])
    )

    if user_id in owner_ids:
        return True

    bio = await get_fresh_user_bio(client, user_id)

    if has_bio_tag(bio):
        return True

    prompt_text = (
        "🔒 <b>Access Denied ❌</b>\n\n"
        f"Hey {user_mention} 👋 Aapka Access Abhi Pending Me Hai...\n\n"
        "Join karne ke liye bas ye 2 simple steps follow karo 😊:\n"
        "─────────────────\n"
        " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
        "Apne Bio me ye Tag Lagao 👇\n\n"
        f"<blockquote>● <code>{REQUIRED_TAG}</code></blockquote>\n"
        "<i>(Tap to Copy 👆)</i>\n\n"
        " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
        "Bio update karne ke baad niche\n\n"
        "<b>🟢 Verify Bio 🔄</b>\n\n"
        "Button par tap kar do,\n"
        "instant Access mil jayega! 🚀\n"
        "─────────────────"
    )

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⚙️ Open Settings",
                url="tg://settings"
            ),
            InlineKeyboardButton(
                "🟢 Verify Bio 🔄",
                callback_data="verify_user_bio"
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Main Channel",
                url="https://t.me/Crazy_for_Goals"
            ),
            InlineKeyboardButton(
                "💬 Contact Admin",
                url="https://t.me/CrazyxDeveloper_Bot"
            )
        ]
    ])

    try:
        await message.reply_text(
            prompt_text,
            reply_markup=buttons,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception:
        pass

    return False


@app.on_chat_join_request()
async def handle_chat_join_request(
    client: Client,
    request: ChatJoinRequest
):
    user_id = request.from_user.id
    chat_id = request.chat.id
    chat_title = request.chat.title or "Channel/Group"

    safe_user_name = html.escape(
        request.from_user.first_name or "User"
    )
    user_mention = (
        f"<a href='tg://user?id={user_id}'>{safe_user_name}</a>"
    )

    chat_link = await get_or_create_permanent_join_link(
        client,
        chat_id,
        request.invite_link,
        request.chat
    )

    # Channel name on the first quoted line; link on the second.
    chat_display = format_channel_display(
        chat_title,
        chat_link
    )
    chat_display_excl = format_channel_display(
        chat_title,
        chat_link,
        suffix=" !"
    )

    bio = await get_fresh_user_bio(client, user_id)

    if has_bio_tag(bio):
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            print(
                f"[JOIN REQ] Approved user {user_id} "
                f"in chat {chat_title}"
            )
        except Exception as e:
            print(
                f"[JOIN REQ] Failed to approve user {user_id}: {e}"
            )

        approve_text = (
            "🔓 <b>Access Granted & Bio Verified ✅</b>\n\n"
            f"<blockquote><b>Welcome, {user_mention} ! 🥂</b></blockquote>\n\n"
            "Aapka profile Bio successfully verify ho gaya hai! 🎉\n\n"
            "✅ <b>Join Request Approved for:</b>\n"
            f"{chat_display_excl}\n\n"
            "Ab aap bot and channel access kar sakte hain. 🥰\n\n"
            f"⚠️ <b>Note:</b> <i>Agar Bio se "
            f"<code>{REQUIRED_TAG}</code> hataya to access "
            "firse deny ho jayega. 📑</i>\n\n"
            "👉 <b>Send /start to proceed!</b>"
        )

        try:
            await client.send_message(
                user_id,
                approve_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            print(
                f"[JOIN REQ] Could not send DM to "
                f"approved user {user_id}: {e}"
            )

    else:
        await join_req_db.update_one(
            {"user_id": user_id, "chat_id": chat_id},
            {
                "$set": {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "chat_title": chat_title,
                    "chat_link": chat_link
                }
            },
            upsert=True
        )

        prompt_text = (
            "🔒 <b>Access Denied ❌</b>\n\n"
            f"Hey {user_mention} 👋 Aapka\n"
            "Request for 👇\n\n"
            f"{chat_display}\n\n"
            "Abhi Pending Me Hai...\n\n"
            "Join karne ke liye bas ye 2 simple steps follow karo 😊:\n"
            "─────────────────\n"
            " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
            "Apne Bio me ye Tag Lagao 👇\n\n"
            f"<blockquote>● <code>{REQUIRED_TAG}</code></blockquote>\n"
            "<i>(Tap to Copy 👆)</i>\n\n"
            " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
            "Bio update karne ke baad niche\n\n"
            "<b>🟢 Verify Bio 🔄</b>\n\n"
            "Button par tap kar do,\n"
            "instant Access mil jayega! 🚀\n"
            "─────────────────"
        )

        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "⚙️ Open Settings",
                    url="tg://settings"
                ),
                InlineKeyboardButton(
                    "🟢 Verify Bio 🔄",
                    callback_data="verify_user_bio"
                )
            ],
            [
                InlineKeyboardButton(
                    "📢 Main Channel",
                    url="https://t.me/Crazy_for_Goals"
                ),
                InlineKeyboardButton(
                    "💬 Contact Admin",
                    url="https://t.me/CrazyxDeveloper_Bot"
                )
            ]
        ])

        try:
            await client.send_message(
                user_id,
                prompt_text,
                reply_markup=buttons,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as e:
            print(
                f"[JOIN REQ] Could not send prompt DM "
                f"to user {user_id}: {e}"
            )


@app.on_callback_query(filters.regex("^verify_user_bio$"))
async def verify_user_bio_callback(
    client: Client,
    callback_query: CallbackQuery
):
    user_id = callback_query.from_user.id

    user_name = html.escape(
        callback_query.from_user.first_name
        if callback_query.from_user
        else "User"
    )
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

    bio = await get_fresh_user_bio(client, user_id)

    if has_bio_tag(bio):
        await callback_query.answer(
            "🔓 Access Granted! Aapka Bio Verify ho gaya hai. 🎉",
            show_alert=True
        )

        pending_requests = await join_req_db.find(
            {"user_id": user_id}
        ).to_list(100)

        approved_chats_list = []

        for req in pending_requests:
            try:
                await client.approve_chat_join_request(
                    req["chat_id"],
                    user_id
                )

                approved_chats_list.append({
                    "title": req.get("chat_title", "Channel"),
                    "link": req.get("chat_link", "")
                })

                await join_req_db.delete_one(
                    {"_id": req["_id"]}
                )

            except Exception as e:
                print(
                    f"[JOIN REQ VERIFY] Failed to approve "
                    f"chat {req['chat_id']}: {e}"
                )

        approve_text = (
            "🔓 <b>Access Granted & Bio Verified ✅</b>\n\n"
            f"<blockquote><b>Welcome, {user_mention} ! 🥂</b></blockquote>\n\n"
            "Aapka profile Bio successfully verify ho gaya hai! 🎉\n\n"
        )

        if approved_chats_list:
            approve_text += "✅ <b>Join Request Approved for:</b>\n"

            for item in approved_chats_list:
                approve_text += (
                    format_channel_display(
                        item["title"],
                        item["link"],
                        suffix=" !"
                    )
                    + "\n"
                )

            approve_text += "\n"

        approve_text += (
            "Ab aap bot and channel access kar sakte hain. 🥰\n\n"
            f"⚠️ <b>Note:</b> <i>Agar Bio se "
            f"<code>{REQUIRED_TAG}</code> hataya to access "
            "firse deny ho jayega. 📑</i>\n\n"
            "👉 <b>Send /start to proceed!</b>"
        )

        try:
            await callback_query.message.edit_text(
                approve_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception:
            pass

    else:
        denied_msg = (
            "❌ Access Denied!\n\n"
            f"1️⃣ Bio me '{REQUIRED_TAG}' tag lagayein.\n"
            "2️⃣ Privacy Setting: Settings ⚙️ ➔ "
            "Privacy & Security ➔ Bio ➔ Set to 'Everybody'!\n\n"
            "Fir 🟢 Verify Bio 🔄 button par click karein."
        )

        await callback_query.answer(
            denied_msg,
            show_alert=True
        )
