

# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio verification & Chat Join Request handler
# Author: Antigravity
# ---------------------------------------------------

import logging
import html
import unicodedata
import asyncio
from datetime import datetime, timedelta

from pyrogram import Client, filters, enums
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
from toxic.core.mongo.db import is_admin_or_owner

DEFAULT_REQUIRED_TAG = "@Crazy_for_Goals"
REQUIRED_TAG = DEFAULT_REQUIRED_TAG

join_req_db = tdb["pending_join_requests"]
invite_link_db = tdb["channel_invite_links"]
bio_settings_db = tdb["global_bio_settings"]
verified_bio_users_db = tdb["verified_bio_users"]
bio_auto_deletions_db = tdb["bio_auto_deletions"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def schedule_bio_message_auto_delete(
    client: Client,
    chat_id: int,
    message_id: int,
    delay_seconds: int = 7200
):
    """
    Schedules a bio verification message for automatic deletion after 2 hours (7200s).
    Saves to MongoDB so it persists across bot restarts, and spawns an asyncio task.
    """
    delete_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
    try:
        await bio_auto_deletions_db.update_one(
            {"chat_id": chat_id, "message_id": message_id},
            {"$set": {
                "chat_id": chat_id,
                "message_id": message_id,
                "delete_at": delete_at
            }},
            upsert=True
        )
    except Exception as e:
        logger.warning("Failed to store bio auto-deletion in DB: %s", e)

    asyncio.create_task(_async_delete_after_delay(client, chat_id, message_id, delay_seconds))


async def _async_delete_after_delay(client: Client, chat_id: int, message_id: int, delay_seconds: int):
    try:
        await asyncio.sleep(delay_seconds)
        await client.delete_messages(chat_id=chat_id, message_ids=message_id)
        logger.info("Auto-deleted bio verification message %s in chat %s after 2 hours.", message_id, chat_id)
    except Exception as e:
        logger.debug("Failed to auto-delete bio message %s in chat %s: %s", message_id, chat_id, e)
    finally:
        try:
            await bio_auto_deletions_db.delete_one({"chat_id": chat_id, "message_id": message_id})
        except Exception:
            pass


async def check_pending_bio_auto_deletions(client: Client):
    """
    Checks MongoDB for any expired bio verification messages and deletes them.
    Called periodically by background scheduler.
    """
    try:
        now = datetime.utcnow()
        cursor = bio_auto_deletions_db.find({"delete_at": {"$lte": now}})
        async for item in cursor:
            chat_id = item.get("chat_id")
            message_id = item.get("message_id")
            if chat_id and message_id:
                try:
                    await client.delete_messages(chat_id=chat_id, message_ids=message_id)
                    logger.info("Cleaned up expired bio message %s in chat %s from DB queue.", message_id, chat_id)
                except Exception as e:
                    logger.debug("Could not delete expired bio message %s: %s", message_id, e)
                await bio_auto_deletions_db.delete_one({"_id": item["_id"]})
    except Exception as e:
        logger.debug("Error checking pending bio auto deletions: %s", e)

async def mark_user_bio_verified(user_id: int, tag: str, first_name: str = ""):
    """Marks a user as having verified the required bio tag in MongoDB."""
    try:
        await verified_bio_users_db.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "user_id": user_id,
                    "first_name": first_name or "",
                    "tag": tag,
                    "status": "verified"
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error("Failed to mark user bio verified: %s", e)


async def mark_user_bio_revoked(user_id: int):
    """Marks a user as having removed or lost the required bio tag."""
    try:
        await verified_bio_users_db.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "status": "revoked"
                }
            }
        )
    except Exception as e:
        logger.error("Failed to mark user bio revoked: %s", e)


async def get_verified_bio_users_count() -> int:
    """Returns the total number of users who currently have verified bio tags."""
    try:
        return await verified_bio_users_db.count_documents({"status": "verified"})
    except Exception:
        return 0

async def is_bio_check_enabled() -> bool:
    """Returns True if Bio Verification is enabled. Defaults to True (ON)."""
    try:
        doc = await bio_settings_db.find_one({"_id": "bio_verification_status"})
        if doc is not None:
            return bool(doc.get("enabled", True))
    except Exception:
        pass
    return True

async def set_bio_check_enabled(enabled: bool):
    """Saves Bio Verification state to MongoDB."""
    try:
        await bio_settings_db.update_one(
            {"_id": "bio_verification_status"},
            {"$set": {"enabled": bool(enabled)}},
            upsert=True
        )
    except Exception as e:
        logger.error("Failed to save bio setting: %s", e)


async def get_required_bio_tag() -> str:
    """Returns the current required bio tag from MongoDB. Defaults to @Crazy_for_Goals."""
    try:
        doc = await bio_settings_db.find_one({"_id": "bio_verification_tag"})
        if doc and doc.get("tag"):
            return str(doc["tag"]).strip()
    except Exception:
        pass
    return DEFAULT_REQUIRED_TAG


async def set_required_bio_tag(tag: str) -> str:
    """Saves the required bio tag to MongoDB."""
    tag_clean = str(tag).strip()
    if not tag_clean.startswith("@"):
        tag_clean = f"@{tag_clean}"
    try:
        await bio_settings_db.update_one(
            {"_id": "bio_verification_tag"},
            {"$set": {"tag": tag_clean}},
            upsert=True
        )
        return tag_clean
    except Exception as e:
        logger.error("Failed to save required bio tag: %s", e)
        return tag_clean


def has_bio_tag(user_bio: str, target_tag: str = None) -> bool:
    if not user_bio:
        return False

    normalized = unicodedata.normalize("NFKC", user_bio).lower()

    clean_text = "".join(
        c if c.isalnum() or c == "_" else " "
        for c in normalized
    )
    clean_nospace = clean_text.replace(" ", "")

    if target_tag:
        raw_tag = str(target_tag).lower().replace("@", "").strip()
        raw_clean = "".join(c if c.isalnum() or c == "_" else " " for c in raw_tag).strip()
        raw_nospace = raw_clean.replace(" ", "")
        if raw_clean and (raw_clean in clean_text or raw_nospace in clean_nospace):
            return True

    return (
        "crazy_for_goals" in clean_text
        or "crazyforgoals" in clean_nospace
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
    """
    Fetch a user's bio using raw GetFullUser and get_chat across bot and available userbot clients.
    None means the bio could not be retrieved at all.
    """
    # 1. Try with the primary bot client
    try:
        peer = await client.resolve_peer(user_id)
        result = await client.invoke(functions.users.GetFullUser(id=peer))
        if hasattr(result, "full_user"):
            about = getattr(result.full_user, "about", None)
            if about is not None:
                return about or ""
    except Exception as e:
        logger.debug("Raw bot bio lookup for %s: %s", user_id, e)

    try:
        user = await client.get_chat(user_id)
        about = getattr(user, "bio", None)
        if about is not None:
            return about or ""
    except Exception as e:
        logger.debug("get_chat bot bio lookup for %s: %s", user_id, e)

    # 2. Try with pro / pro_clients pool (Userbots see full bios without bot privacy limitations)
    try:
        from toxic import pro, pro_clients
        candidates = [pro] if pro else []
        if pro_clients:
            for pc in pro_clients:
                if pc and pc not in candidates:
                    candidates.append(pc)

        for ub_cl in candidates:
            if ub_cl and getattr(ub_cl, "is_connected", False):
                try:
                    p = await ub_cl.resolve_peer(user_id)
                    res = await ub_cl.invoke(functions.users.GetFullUser(id=p))
                    if hasattr(res, "full_user"):
                        about = getattr(res.full_user, "about", None)
                        if about is not None:
                            return about or ""
                except Exception:
                    try:
                        u = await ub_cl.get_chat(user_id)
                        about = getattr(u, "bio", None)
                        if about is not None:
                            return about or ""
                    except Exception:
                        pass
    except Exception as err:
        logger.debug("Pro clients bio fallback error: %s", err)

    # 3. Try userbot pool from DB if available
    try:
        from toxic.core.mongo.db import get_all_active_userbots
        active_ubs = await get_all_active_userbots()
        for ub in active_ubs:
            if ub and getattr(ub, "is_connected", False):
                try:
                    p = await ub.resolve_peer(user_id)
                    res = await ub.invoke(functions.users.GetFullUser(id=p))
                    if hasattr(res, "full_user"):
                        about = getattr(res.full_user, "about", None)
                        if about is not None:
                            return about or ""
                except Exception:
                    pass
    except Exception:
        pass

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
            if "BOT_METHOD_INVALID" in str(e):
                if cached_link and cached_link.startswith("https://t.me/"):
                    return cached_link
            logger.info(
                "Saved invite link check skipped/invalid; reusing or creating: %s",
                e
            )

        if cached_link and cached_link.startswith("https://t.me/"):
            return cached_link

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
                "📜 Bio Setup Guide & Terms",
                callback_data="bio_terms_info"
            ),
            InlineKeyboardButton(
                "💎 View Plans",
                callback_data="see_plan"
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
    if not await is_bio_check_enabled():
        return True

    if not message.from_user:
        return True

    user_id = message.from_user.id
    user_name = html.escape(message.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"

    if user_id in get_owner_ids() or is_admin_or_owner(user_id):
        return True

    req_tag = await get_required_bio_tag()
    bio = await get_fresh_user_bio(client, user_id)

    # If bio has the required tag, grant access and track
    if bio is not None and has_bio_tag(bio, req_tag):
        await mark_user_bio_verified(user_id, req_tag, message.from_user.first_name)
        return True

    # Check if previously verified user removed the tag
    user_doc = await verified_bio_users_db.find_one({"user_id": user_id})
    was_previously_verified = bool(user_doc and user_doc.get("status") == "verified")
    if was_previously_verified:
        await mark_user_bio_revoked(user_id)

    await send_bio_verification_prompt(client, message)
    return False


async def send_bio_verification_prompt(
    client: Client,
    message: Message
):
    """Sends the official bio verification message with instructions and interactive buttons."""
    if not message.from_user:
        return None

    user_id = message.from_user.id
    user_name = html.escape(message.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
    req_tag = await get_required_bio_tag()

    # Check if previously verified user removed the tag
    user_doc = await verified_bio_users_db.find_one({"user_id": user_id})
    was_previously_verified = bool(user_doc and user_doc.get("status") == "verified")
    if was_previously_verified:
        header_text = (
            "⚠️ <b>Warning: Bio Tag Removed! ❌</b>\n\n"
            f"Hey {user_mention} 👋 Aapne apne profile bio se required tag <code>{req_tag}</code> hata diya hai!\n"
            "Aapka free bot access <b>suspend</b> kar diya gaya hai.\n\n"
        )
    else:
        header_text = (
            "🔒 <b>Access Denied ❌</b>\n\n"
            f"Hey {user_mention} 👋 Aapka Access Abhi Pending Me Hai...\n\n"
        )

    prompt_text = (
        f"{header_text}"
        "Join / Use karne ke liye bas ye 2 simple steps follow karo 😊:\n"
        "─────────────────\n"
        " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
        "Add This 👇 Tag in <a href=\"tg://settings\"><b>Your Bio</b></a> 👀\n\n"
        f"<blockquote>● <code>{req_tag}</code> ♡</blockquote>\n"
        "<i>(Tap to Copy 👆)</i>\n\n"
        " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
        "Bio update karne ke baad niche\n\n"
        "<b>🟢 Verify Bio 🔄</b>\n\n"
        "Button par tap kar do,\n"
        "instant Access mil jayega! 🚀\n"
        "─────────────────\n\n"
        "<blockquote><b>⚖️ <u>Bio Verification Rules & Terms:</u></b>\n"
        "• <b>Privacy:</b> Settings ⚙️ ➔ Privacy ➔ Bio must be set to <b>'Everybody'</b>.\n"
        f"• <b>Mandatory:</b> <code>{req_tag}</code> bio me hona anivarya hai.\n"
        "• <b>Auto Revoke:</b> Tag hatane par access turant terminate ho jata hai.\n"
        "• <b>Auto Delete:</b> ⏱️ <i>Yeh verification message 2 ghante baad auto-delete ho jayega.</i>\n"
        "• <b>Premium Users:</b> Premium users ke liye koi bio tag required nahi hai.</blockquote>"
    )

    try:
        sent_msg = await message.reply_text(
            prompt_text,
            reply_markup=get_verification_buttons(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        if sent_msg and hasattr(sent_msg, "id"):
            await schedule_bio_message_auto_delete(client, message.chat.id, sent_msg.id, 7200)
        return sent_msg
    except Exception as e:
        logger.warning("Could not send bio verification prompt: %s", e)
        return None


@app.on_chat_join_request()
async def handle_chat_join_request(
    client: Client,
    request: ChatJoinRequest
):
    user_id = request.from_user.id
    chat_id = request.chat.id
    chat_title = request.chat.title or "Channel/Group"

    # If Bio Verification is OFF, do NOT auto-approve requests! Keep them pending.
    if not await is_bio_check_enabled():
        logger.info("Join request from user %s in chat %s received but Bio Verification is OFF. Leaving request pending.", user_id, chat_id)
        return

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

    req_tag = await get_required_bio_tag()
    bio = await get_fresh_user_bio(client, user_id)

    if bio is not None and has_bio_tag(bio, req_tag):
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            logger.info("Approved user %s in chat %s", user_id, chat_id)
            await mark_user_bio_verified(user_id, req_tag, request.from_user.first_name)
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
            f"<code>{req_tag}</code> hataya to access "
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

    prompt_text = (
        "🔒 <b>Access Denied ❌</b>\n\n"
        f"Hey {user_mention} 👋 Aapka\n"
        "Request for 👇\n\n"
        f"{chat_display}\n\n"
        "Abhi Pending Me Hai...\n\n"
        "Join karne ke liye bas ye 2 simple steps follow karo 😊:\n"
        "─────────────────\n"
        " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
        "Add This 👇 Tag in <a href=\"tg://settings\"><b>Your Bio</b></a> 👀\n\n"
        f"<blockquote>● <code>{req_tag}</code> ♡</blockquote>\n"
        "<i>(Tap to Copy 👆)</i>\n\n"
        " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
        "Bio update karne ke baad niche\n\n"
        "<b>🟢 Verify Bio 🔄</b>\n\n"
        "Button par tap kar do,\n"
        "instant Access mil jayega! 🚀\n"
        "─────────────────\n\n"
        "<blockquote><b>⚖️ <u>Bio Verification Rules & Terms:</u></b>\n"
        "• <b>Privacy:</b> Settings ⚙️ ➔ Privacy ➔ Bio must be set to <b>'Everybody'</b>.\n"
        f"• <b>Mandatory:</b> <code>{req_tag}</code> bio me hona anivarya hai.\n"
        "• <b>Auto Revoke:</b> Tag hatane par access turant terminate ho jata hai.\n"
        "• <b>Auto Delete:</b> ⏱️ <i>Yeh verification message 2 ghante baad auto-delete ho jayega.</i>\n"
        "• <b>Premium Users:</b> Premium users ke liye koi bio tag required nahi hai.</blockquote>"
    )


    try:
        sent_msg = await client.send_message(
            user_id,
            prompt_text,
            reply_markup=get_verification_buttons(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        if sent_msg and hasattr(sent_msg, "id"):
            await schedule_bio_message_auto_delete(client, user_id, sent_msg.id, 7200)
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

    req_tag = await get_required_bio_tag()
    if not await is_bio_check_enabled():
        await callback_query.answer("⚠️ Bio verification abhi OFF hai. Admin verification on hone par hi requests process hongi.", show_alert=True)
        return
    else:
        bio = await get_fresh_user_bio(client, user_id)

        if bio is None or not has_bio_tag(bio, req_tag):
            denied_msg = (
                "❌ Access Denied!\n\n"
                f"1️⃣ Bio me '{req_tag}' tag lagayein.\n"
                "2️⃣ Privacy Setting: Settings ⚙️ ➔ "
                "Privacy & Security ➔ Bio ➔ Set to 'Everybody'!\n\n"
                "Fir 🟢 Verify Bio 🔄 button par click karein."
            )
            await callback_query.answer(
                denied_msg,
                show_alert=True
            )
            return

        # If bio has the tag, grant access
        await callback_query.answer(
            "🔓 Access Granted! Aapka Bio Verify ho gaya hai. 🎉",
            show_alert=True
        )
        await mark_user_bio_verified(user_id, req_tag, callback_query.from_user.first_name)


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

    # Fetch channel links to send along with verification message
    from toxic.core.mongo.db import get_main_channel_link, get_bio_channel, get_auth_channels
    main_ch_link = await get_main_channel_link()
    bio_ch_id = await get_bio_channel()
    auth_chs = await get_auth_channels()

    # If user had pending requests, show those. Otherwise, show main channel / destination links!
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
    else:
        # User verified directly via bot DM or button: provide access channel link!
        channel_name = "🎯 Official Channel"
        approve_text += (
            "✅ <b>Unlocked Channel & Bot Access Link:</b>\n"
            f"<blockquote><b>{channel_name} 🚀</b>\n"
            f"<a href='{main_ch_link}'>{main_ch_link}</a></blockquote>\n\n"
        )

    approve_text += (
        "Ab aap bot aur channel ko unhindered access kar sakte hain. 🥰\n\n"
        f"⚠️ <b>Note:</b> <i>Agar Bio se "
        f"<code>{req_tag}</code> hataya toh automated security system access revoke kar dega. 📑</i>\n\n"
        "👉 <b>Niche button se Channel join karein ya /start karein! 🚀</b>"
    )

    # Add interactive access buttons
    success_buttons = [
        [
            InlineKeyboardButton("📢 Open Channel 🚀", url=main_ch_link),
            InlineKeyboardButton("🚀 Start Bot (/start)", url=f"https://t.me/{(client.me.username if client.me else 'bot')}?start=verified")
        ],
        [
            InlineKeyboardButton("💎 View Premium Plans", callback_data="see_plan"),
            InlineKeyboardButton("💬 Contact Support", url="https://t.me/CrazyxDeveloper_Bot")
        ]
    ]

    try:
        await callback_query.message.edit_text(
            approve_text,
            reply_markup=InlineKeyboardMarkup(success_buttons),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.warning("Could not edit verification message: %s", e)
        try:
            await client.send_message(
                user_id,
                approve_text,
                reply_markup=InlineKeyboardMarkup(success_buttons),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception:
            pass


@app.on_callback_query(filters.regex("^bio_terms_info$"))
async def bio_terms_info_callback(client: Client, callback_query: CallbackQuery):
    req_tag = await get_required_bio_tag()
    terms_info = (
        "<blockquote><b>📜 <u>BIO SETUP GUIDE & VERIFICATION TERMS</u> 📜</b></blockquote>\n\n"
        "<b>📱 <u>How to Set & Verify Your Bio (Step-by-Step):</u></b>\n"
        "1️⃣ <b>Copy Tag:</b> Tap on <code>{req_tag}</code> to copy it.\n"
        "2️⃣ <b>Open Settings:</b> Go to Telegram <b>Settings ⚙️ ➔ Edit Profile / Bio</b> and paste the tag.\n"
        "3️⃣ <b>Set Privacy:</b> Go to <b>Settings ⚙️ ➔ Privacy & Security ➔ Bio</b> and set it to <b>'Everybody'</b> (zaroori hai taaki hamara automated bot tag check kar sake).\n"
        "4️⃣ <b>Tap Verify:</b> Niche diye gaye <b>🟢 Verify Bio 🔄</b> button par tap karein aur instant access payein!\n\n"
        "<b>⚖️ <u>Disclaimer & Verification Terms:</u></b>\n"
        f"• <b>🤖 Auto Verification Tag Only:</b> <code>{req_tag}</code> kewal ek automated security verification tag hai jisse system real user activity verify karke free access enable karta hai.\n"
        "• <b>🛡️ No Liability / Not Responsible:</b> We are <b>NOT responsible</b> for any user's profile, bio words, personal actions, or activities. Tag lagana ya hatana user ki apni marzi hai.\n"
        "• <b>🚫 Copyright Disclaimer:</b> Hum kisi bhi prakar ke copyrighted ya unauthorized content ko promote ya host nahi karte hain. Bot ka upyog kewal personal backup aur educational utility ke liye hai.\n"
        "• <b>⚡ Auto-Revoke Policy:</b> Access milne ke baad agar bio se tag hataya gaya, toh bot access automatically revoke ho jayega.\n"
        "• <b>👑 Premium Users Exemption:</b> Paid VIP/PRO plans wale users ke liye bio tag lagana bilkul mandatory nahi hai.\n\n"
        "<i>By verifying and using this bot, you acknowledge and agree to these terms.</i>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟢 Verify Bio 🔄", callback_data="verify_user_bio"),
            InlineKeyboardButton("⚙️ Open Settings", url="tg://settings")
        ],
        [
            InlineKeyboardButton("💎 View Premium Plans", callback_data="see_plan"),
            InlineKeyboardButton("🔙 Back", callback_data="back_to_bio_prompt")
        ]
    ])
    try:
        await callback_query.message.edit_text(terms_info, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        await callback_query.answer("📜 Please review the bio setup guide & terms displayed.", show_alert=True)


@app.on_callback_query(filters.regex("^back_to_bio_prompt$"))
async def back_to_bio_prompt_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_name = html.escape(callback_query.from_user.first_name or "User")
    user_mention = f"<a href='tg://user?id={user_id}'>{user_name}</a>"
    req_tag = await get_required_bio_tag()

    prompt_text = (
        "🔒 <b>Access Denied ❌</b>\n\n"
        f"Hey {user_mention} 👋 Aapka Access Abhi Pending Me Hai...\n\n"
        "Join karne ke liye bas ye 2 simple steps follow karo 😊:\n"
        "─────────────────\n"
        " 💡 <b><u>Step</u> 1️⃣</b>\n\n"
        "Add This 👇 Tag in <a href=\"tg://settings\"><b>Your Bio</b></a> 👀\n\n"
        f"<blockquote>● <code>{req_tag}</code> ♡</blockquote>\n"
        "<i>(Tap to Copy 👆)</i>\n\n"
        " 💡 <b><u>Step</u> 2️⃣</b>\n\n"
        "Bio update karne ke baad niche\n\n"
        "<b>🟢 Verify Bio 🔄</b>\n\n"
        "Button par tap kar do,\n"
        "instant Access mil jayega! 🚀\n"
        "─────────────────\n\n"
        "<blockquote><b>⚖️ <u>Bio Verification Rules & Terms:</u></b>\n"
        "• <b>Privacy:</b> Settings ⚙️ ➔ Privacy ➔ Bio must be set to <b>'Everybody'</b>.\n"
        f"• <b>Mandatory:</b> <code>{req_tag}</code> bio me hona anivarya hai.\n"
        "• <b>Auto Revoke:</b> Tag hatane par access turant terminate ho jata hai.\n"
        "• <b>Auto Delete:</b> ⏱️ <i>Yeh verification message 2 ghante baad auto-delete ho jayega.</i>\n"
        "• <b>Premium Users:</b> Premium users ke liye koi bio tag required nahi hai.</blockquote>"
    )
    try:
        await callback_query.message.edit_text(prompt_text, reply_markup=get_verification_buttons(), parse_mode=ParseMode.HTML)
    except Exception:
        pass


@app.on_message(filters.command(["biocheck", "togglebio", "biostatus", "bio"]) & filters.private)
async def biocheck_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_admin_or_owner(user_id) and user_id not in get_owner_ids():
        return await message.reply_text(
            "⛔ <b>Admin Only:</b> Only bot admins or owner can configure bio check settings.",
            parse_mode=ParseMode.HTML
        )

    is_enabled = await is_bio_check_enabled()
    req_tag = await get_required_bio_tag()
    verified_count = await get_verified_bio_users_count()
    status_icon = "🟢 <b>ON</b> (Mandatory Bio Verification)" if is_enabled else "🔴 <b>OFF</b> (Free / No Bio Required)"
    action_text = "Disable Bio Check 🔴" if is_enabled else "Enable Bio Check 🟢"

    text = (
        "⚙️ <b><u>Global Bio Verification Settings</u></b>\n\n"
        f"<b>Current Status:</b> {status_icon}\n"
        f"<b>Required Tag:</b> <code>{req_tag}</code>\n"
        f"👥 <b>Verified Bio Users:</b> <code>{verified_count}</code> users\n\n"
        "<i>When OFF, join requests are NOT auto-accepted (stay pending until ON or accepted manually).\n"
        "When ON, only users with the required tag in their bio will be approved.\n"
        "Admins can toggle ON/OFF or change the verification tag directly from this panel or using /setbiotag.</i>"
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(action_text, callback_data="toggle_bio_status")
        ],
        [
            InlineKeyboardButton("🏷️ Change Bio Tag", callback_data="change_bio_tag_prompt"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_bio_status")
        ]
    ])
    await message.reply_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["setbiotag", "biotag"]) & filters.private)
async def set_bio_tag_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_admin_or_owner(user_id) and user_id not in get_owner_ids():
        return await message.reply_text(
            "⛔ <b>Admin Only:</b> Only bot admins or owner can configure bio tag.",
            parse_mode=ParseMode.HTML
        )

    if len(message.command) > 1:
        new_tag = message.text.split(None, 1)[1].strip()
        saved_tag = await set_required_bio_tag(new_tag)
        return await message.reply_text(
            f"✅ <b>Required Bio Tag Updated!</b>\n\n"
            f"🏷️ <b>New Required Tag:</b> <code>{saved_tag}</code>\n\n"
            f"<i>All future bio checks and channel join requests will verify this tag.</i>",
            parse_mode=ParseMode.HTML
        )

    curr_tag = await get_required_bio_tag()
    try:
        prompt = await client.ask(
            chat_id=user_id,
            text=(
                f"🏷️ <b><u>Set Required Bio Tag</u></b>\n\n"
                f"Current Tag: <code>{curr_tag}</code>\n\n"
                "Please send the new tag to require in user bios (e.g. <code>@Crazy_for_Goals</code> or <code>@MyTag</code>):\n\n"
                "<i>Send /cancel to abort.</i>"
            ),
            timeout=120,
            parse_mode=ParseMode.HTML
        )
        if not prompt or not prompt.text or prompt.text.strip().lower() in ("/cancel", "cancel"):
            return await message.reply_text("❌ Operation cancelled.")
        new_tag = prompt.text.strip()
        saved_tag = await set_required_bio_tag(new_tag)
        await message.reply_text(
            f"✅ <b>Required Bio Tag Updated!</b>\n\n"
            f"🏷️ <b>New Required Tag:</b> <code>{saved_tag}</code>\n\n"
            f"<i>All future bio checks and channel join requests will verify this tag.</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.reply_text(f"⚠️ Error: {e}")


@app.on_callback_query(filters.regex(r"^(toggle_bio_status|refresh_bio_status|change_bio_tag_prompt)$"))
async def toggle_bio_status_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin_or_owner(user_id) and user_id not in get_owner_ids():
        return await callback_query.answer("⛔ Only bot admins or owner can change this setting!", show_alert=True)

    action = callback_query.data
    if action == "toggle_bio_status":
        curr = await is_bio_check_enabled()
        new_state = not curr
        await set_bio_check_enabled(new_state)
        await callback_query.answer(
            f"✅ Bio check is now {'ENABLED 🟢' if new_state else 'DISABLED 🔴'}!",
            show_alert=True
        )
    elif action == "change_bio_tag_prompt":
        await callback_query.answer()
        try:
            curr_tag = await get_required_bio_tag()
            prompt = await client.ask(
                chat_id=user_id,
                text=(
                    f"🏷️ <b><u>Set Required Bio Tag</u></b>\n\n"
                    f"Current Tag: <code>{curr_tag}</code>\n\n"
                    "Please send the new tag to require in user bios (e.g. <code>@Crazy_for_Goals</code> or <code>@MyTag</code>):\n\n"
                    "<i>Send /cancel to abort.</i>"
                ),
                timeout=120,
                parse_mode=ParseMode.HTML
            )
            if not prompt or not prompt.text or prompt.text.strip().lower() in ("/cancel", "cancel"):
                return await client.send_message(user_id, "❌ Tag update cancelled.")
            new_tag = prompt.text.strip()
            saved_tag = await set_required_bio_tag(new_tag)
            await client.send_message(
                user_id,
                f"✅ <b>Required Bio Tag Updated!</b>\n\n"
                f"🏷️ <b>New Required Tag:</b> <code>{saved_tag}</code>\n\n"
                "<i>All future bio checks will look for this tag.</i>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            await client.send_message(user_id, f"⚠️ Error or timeout: {e}")
            return
    else:
        await callback_query.answer("🔄 Status refreshed!")

    is_enabled = await is_bio_check_enabled()
    req_tag = await get_required_bio_tag()
    verified_count = await get_verified_bio_users_count()
    status_icon = "🟢 <b>ON</b> (Mandatory Bio Verification)" if is_enabled else "🔴 <b>OFF</b> (Free / No Bio Required)"
    action_text = "Disable Bio Check 🔴" if is_enabled else "Enable Bio Check 🟢"

    text = (
        "⚙️ <b><u>Global Bio Verification Settings</u></b>\n\n"
        f"<b>Current Status:</b> {status_icon}\n"
        f"<b>Required Tag:</b> <code>{req_tag}</code>\n"
        f"👥 <b>Verified Bio Users:</b> <code>{verified_count}</code> users\n\n"
        "<i>When OFF, join requests are NOT auto-accepted (stay pending until ON or accepted manually).\n"
        "When ON, only users with the required tag in their bio will be approved.\n"
        "Admins can toggle ON/OFF or change the verification tag directly from this panel or using /setbiotag.</i>"
    )
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(action_text, callback_data="toggle_bio_status")
        ],
        [
            InlineKeyboardButton("🏷️ Change Bio Tag", callback_data="change_bio_tag_prompt"),
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_bio_status")
        ]
    ])
    try:
        await callback_query.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    except Exception:
        pass


@app.on_message(filters.command(["acceptall", "approveall", "acceptrequests", "approverequests"]))
async def accept_all_channel_requests_command(client: Client, message: Message):
    """
    Accepts all pending join requests in a specific channel or group:
    Usage:
      - Send `/acceptall` inside the target channel/group.
      - OR in private chat: `/acceptall <channel_id or @username or invite_link>`
    Only Owner and Bot Admins can execute this command.
    """
    user_id = message.from_user.id if message.from_user else 0
    if not is_admin_or_owner(user_id) and user_id not in get_owner_ids():
        return await message.reply_text("⛔ <b>Admin Only:</b> Only bot admins or owner can use this command.", parse_mode=ParseMode.HTML)

    target_chat_input = None
    if len(message.command) > 1:
        target_chat_input = message.text.split(None, 1)[1].strip()
    elif message.chat and message.chat.type in (enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP, enums.ChatType.GROUP):
        target_chat_input = message.chat.id

    if not target_chat_input:
        return await message.reply_text(
            "📌 <b><u>Usage of /acceptall</u></b>\n\n"
            "• <b>Direct in Channel/Group:</b> Send <code>/acceptall</code> directly in that channel/group.\n"
            "• <b>In Private Chat:</b> Send <code>/acceptall &lt;chat_id or @username&gt;</code>\n\n"
            "<i>Example:</i> <code>/acceptall -1001234567890</code> or <code>/acceptall @MyChannel</code>",
            parse_mode=ParseMode.HTML
        )

    status_msg = await message.reply_text("⏳ <b>Processing join requests...</b> Please wait.", parse_mode=ParseMode.HTML)

    try:
        # Resolve target chat
        try:
            target_chat_id = int(target_chat_input)
        except ValueError:
            target_chat_id = target_chat_input

        target_chat = await client.get_chat(target_chat_id)
        target_cid = target_chat.id
        target_title = target_chat.title or str(target_cid)

        # 1. First try Telegram's native HideAllChatJoinRequests RPC (approves all in 1 shot)
        approved_via_rpc = False
        try:
            peer = await client.resolve_peer(target_cid)
            from pyrogram.raw.functions.messages import HideAllChatJoinRequests
            await client.invoke(HideAllChatJoinRequests(peer=peer, approved=True))
            approved_via_rpc = True
            logger.info("Successfully executed HideAllChatJoinRequests for %s", target_cid)
        except Exception as rpc_e:
            logger.warning("HideAllChatJoinRequests RPC attempt failed for %s: %s. Falling back to DB & loop method.", target_cid, rpc_e)

        # 2. Approve all pending requests recorded in DB for this chat
        db_approved_count = 0
        try:
            db_reqs = await join_req_db.find({"chat_id": target_cid}).to_list(5000)
            for req in db_reqs:
                uid = req.get("user_id")
                if uid:
                    try:
                        await client.approve_chat_join_request(target_cid, uid)
                        db_approved_count += 1
                        await asyncio.sleep(0.05)
                    except Exception:
                        pass
            await join_req_db.delete_many({"chat_id": target_cid})
        except Exception as db_e:
            logger.warning("DB approve cleanup warning: %s", db_e)

        # 3. If RPC failed and DB count is low, try crawling pending importers if available
        crawled_count = 0
        if not approved_via_rpc:
            try:
                from pyrogram.raw.functions.messages import GetChatInviteImporters
                peer = await client.resolve_peer(target_cid)
                offset_date = 0
                offset_user = functions.types.InputUserEmpty()
                while True:
                    res = await client.invoke(
                        GetChatInviteImporters(
                            peer=peer,
                            requested=True,
                            limit=100,
                            offset_date=offset_date,
                            offset_user=offset_user
                        )
                    )
                    importers = getattr(res, "importers", [])
                    if not importers:
                        break
                    for imp in importers:
                        user_raw_id = getattr(imp, "user_id", None)
                        if user_raw_id:
                            try:
                                await client.approve_chat_join_request(target_cid, user_raw_id)
                                crawled_count += 1
                                await asyncio.sleep(0.05)
                            except Exception:
                                pass
                    last_imp = importers[-1]
                    offset_date = getattr(last_imp, "date", 0)
                    last_uid = getattr(last_imp, "user_id", None)
                    offset_user = await client.resolve_peer(last_uid) if last_uid else functions.types.InputUserEmpty()
                    if len(importers) < 100:
                        break
            except Exception as crawl_e:
                logger.debug("GetChatInviteImporters notice: %s", crawl_e)

        total_accepted = db_approved_count + crawled_count
        summary_extra = f" (Processed <code>{total_accepted}</code> requests from queue)" if total_accepted > 0 else ""
        if approved_via_rpc:
            result_text = (
                f"✅ <b>All Join Requests Approved!</b>\n\n"
                f"📢 <b>Channel/Group:</b> <code>{target_title}</code> (<code>{target_cid}</code>)\n"
                f"⚡ <b>Status:</b> All pending join requests successfully accepted via Telegram Instant API!{summary_extra}"
            )
        else:
            result_text = (
                f"✅ <b>Join Requests Processing Complete!</b>\n\n"
                f"📢 <b>Channel/Group:</b> <code>{target_title}</code> (<code>{target_cid}</code>)\n"
                f"👥 <b>Total Approved:</b> <code>{total_accepted}</code> pending requests."
            )

        await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error("Error in acceptall command: %s", e)
        await status_msg.edit_text(f"❌ <b>Error:</b> <code>{e}</code>\n\n<i>Make sure the bot is an Admin with 'Invite Users via Link' & 'Add Members' rights in this channel.</i>", parse_mode=ParseMode.HTML)



