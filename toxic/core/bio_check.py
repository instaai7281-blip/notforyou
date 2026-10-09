

# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification & Chat Join Request handler
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

join_req_db = tdb["pending_join_requests"]
invite_link_db = tdb["channel_invite_links"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def has_bio_tag(user_bio: str) -> bool:
    if not user_bio:
        return False

    normalized = unicodedata.normalize("NFKC", user_bio).lower()

    clean_text = "".join(
        c if c.isalnum() or c == "_" else " "
        for c in normalized
    )

    return (
        "crazy_for_goals" in clean_text
        or "crazyforgoals" in clean_text.replace(" ", "")
    )


def get_owner_ids():
    if not OWNER_ID:
        return set()

    if isinstance(OWNER_ID, int):
        return {OWNER_ID}

    if isinstance(OWNER_ID, str):
        result = set()
        for item in OWNER_ID.split(","):
            item = item.strip()
            if item.lstrip("-").isdigit():
                result.add(int(item))
        return result

    try:
        return {int(item) for item in OWNER_ID}
    except (TypeError, ValueError):
        return set()


async def get_fresh_user_bio(client: Client, user_id: int):
    """Fetch a user's bio. None means the bio could not be verified."""

    try:
        peer = await client.resolve_peer(user_id)
        result = await client.invoke(
            functions.users.GetFullUser(id=peer)
        )

        if hasattr(result, "full_user"):
            about = getattr(result.full_user, "about", None)
            if about is not None:
                return about or ""

    except Exception as e:
        logger.warning("Raw bio lookup failed for %s: %s", user_id, e)

    try:
        from toxic import pro

        if pro and pro.is_connected:
            peer = await pro.resolve_peer(user_id)
            result = await pro.invoke(
                functions.users.GetFullUser(id=peer)
            )

            if hasattr(result, "full_user"):
                about = getattr(result.full_user, "about", None)
                if about is not None:
                    return about or ""

    except Exception:
        pass

    try:
        user = await client.get_chat(user_id)
        about = getattr(user, "bio", None)

        if about is not None:
            return about or ""

    except Exception as e:
        logger.warning("get_chat bio lookup failed for %s: %s", user_id, e)

    # Do not treat an API failure as proof that the user has no tag.
    return None


async def get_or_create_permanent_join_link(
    client: Client,
    chat_id: int,
    request_link=None,
    chat_obj=None
) -> str:
    """
    Reuse a saved link only after validating it.
    Otherwise create a fresh, non-expiring join-request invite link.
    """

    cached = await invite_link_db.find_one({"chat_id": chat_id})

    if cached and cached.get("link"):
        cached_link = cached["link"]

        try:
            invite_info = await client.get_chat_invite_link(
                chat_id=chat_id,
                invite_link=cached_link
            )

            if (
                invite_info
                and not getattr(invite_info, "is_revoked", False)
                and getattr(invite_info, "creates_join_request", False)
                and not getattr(invite_info, "expire_date", None)
            ):
                return invite_info.invite_link

        except Exception as e:
            logger.info(
                "Saved invite link is invalid; creating a new one: %s",
                e
            )

        await invite_link_db.delete_one({"chat_id": chat_id})

    # Create a fresh request-to-join link. Do not use a public URL or
    # an old request.invite_link as a substitute for this dedicated link.
    try:
        invite = await client.create_chat_invite_link(
            chat_id=chat_id,
            name="Permanent Join Request",
            creates_join_request=True
        )

        full_link = invite.invite_link

        if not full_link or "..." in full_link:
            logger.error("Telegram returned an invalid/incomplete invite URL.")
            return ""

        await invite_link_db.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "link": full_link
                }
            },
            upsert=True
        )

        logger.info("Created a new join-request invite link for %s", chat_id)
        return full_link

    except Exception as e:
        logger.error(
            "Could not create a join-request link for %s: %s",
            chat_id,
            e
        )
        return ""


def format_channel_display(
    channel_title: str,
    channel_link: str,
    suffix: str = ""
) -> str:
    """Put channel name and the complete link on separate blockquote lines."""

    safe_title = html.escape(channel_title or "Channel/Group")
    safe_link = html.escape(channel_link or "", quote=True)

    if channel_link:
        return (
            f"<blockquote><b>{safe_title}{suffix}</b>\n"
            f"{safe_link}</blockquote>"
        )

    return (
        f"<blockquote><b>{safe_title}{suffix}</b>\n"
        "Invite link could not be created. Please contact admin.</blockquote>"
    )


def get_verification_buttons():
    return InlineKeyboardMarkup([
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


async def check_user_bio_access(
    client: Client,
    message: Message
) -> bool:
    if not message.from_user:
        return True

    user_id = message.from_user.id
    user_name = html.escape(message.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

    if user_id in get_owner_ids():
        return True

    bio = await get_fresh_user_bio(client, user_id)

    if bio is not None and has_bio_tag(bio):
        return True

    if bio is None:
        prompt_text = (
            "⚠️ <b>Bio Verification Temporarily Unavailable</b>\n\n"
            "Telegram se aapka bio verify nahi ho paaya. "
            "Please thodi der baad dobara try karein."
        )
        try:
            await message.reply_text(
                prompt_text,
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        return False

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

    try:
        await message.reply_text(
            prompt_text,
            reply_markup=get_verification_buttons(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning("Could not send bio verification prompt: %s", e)

    return False


@app.on_chat_join_request()
async def handle_chat_join_request(
    client: Client,
    request: ChatJoinRequest
):
    user_id = request.from_user.id
    chat_id = request.chat.id
    chat_title = request.chat.title or "Channel/Group"

    safe_user_name = html.escape(request.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{safe_user_name}</a>"

    chat_link = await get_or_create_permanent_join_link(
        client,
        chat_id,
        request.invite_link,
        request.chat
    )

    chat_display = format_channel_display(chat_title, chat_link)
    chat_display_excl = format_channel_display(
        chat_title,
        chat_link,
        suffix=" !"
    )

    bio = await get_fresh_user_bio(client, user_id)

    if bio is not None and has_bio_tag(bio):
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            logger.info("Approved user %s in chat %s", user_id, chat_id)
        except Exception as e:
            logger.error("Failed to approve user %s: %s", user_id, e)

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
            logger.warning("Could not DM approved user %s: %s", user_id, e)

        return

    # Keep the request pending until verification succeeds.
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

    if bio is None:
        prompt_text = (
            "⚠️ <b>Bio Verification Temporarily Unavailable</b>\n\n"
            f"Hey {user_mention} 👋\n\n"
            "Telegram se aapka bio verify nahi ho paaya. "
            "Please thodi der baad Verify Bio button dabayein."
        )
    else:
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

    try:
        await client.send_message(
            user_id,
            prompt_text,
            reply_markup=get_verification_buttons(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning("Could not send prompt to user %s: %s", user_id, e)


@app.on_callback_query(filters.regex("^verify_user_bio$"))
async def verify_user_bio_callback(
    client: Client,
    callback_query: CallbackQuery
):
    user_id = callback_query.from_user.id

    user_name = html.escape(
        callback_query.from_user.first_name or "User"
    )
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

    bio = await get_fresh_user_bio(client, user_id)

    if bio is None:
        await callback_query.answer(
            "Telegram se bio verify nahi ho paaya. Thodi der baad try karein.",
            show_alert=True
        )
        return

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

                await join_req_db.delete_one({"_id": req["_id"]})

            except Exception as e:
                logger.error(
                    "Failed to approve chat %s: %s",
                    req.get("chat_id"),
                    e
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
        except Exception as e:
            logger.warning("Could not edit verification message: %s", e)

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
