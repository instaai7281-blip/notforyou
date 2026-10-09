
# ---------------------------------------------------
# File Name: bio_check.py
# Description: Bio Verification + Permanent Join Request Links
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
    InlineKeyboardButton,
)
from pyrogram.enums import ParseMode
from pyrogram.raw import functions

from config import OWNER_ID
from toxic import app, tdb

logger = logging.getLogger(__name__)

REQUIRED_TAG = "@Crazy_for_Goals"

join_req_db = tdb["pending_join_requests"]
invite_link_db = tdb["channel_invite_links"]


# ---------------------------------------------------
# Owner IDs
# ---------------------------------------------------

def get_owner_ids():
    values = OWNER_ID if isinstance(OWNER_ID, (list, tuple, set)) else [OWNER_ID]
    owners = set()

    for value in values:
        try:
            owners.add(int(value))
        except (TypeError, ValueError):
            continue

    return owners


OWNER_IDS = get_owner_ids()


# ---------------------------------------------------
# Bio verification
# ---------------------------------------------------

def has_bio_tag(user_bio: str) -> bool:
    if not user_bio:
        return False

    normalized = unicodedata.normalize("NFKC", user_bio).casefold()
    cleaned = "".join(
        char if char.isalnum() or char == "_" else " "
        for char in normalized
    )

    compact = cleaned.replace(" ", "")

    return (
        "crazy_for_goals" in cleaned
        or "crazyforgoals" in compact
    )


async def get_fresh_user_bio(client: Client, user_id: int):
    """Return the profile bio, or None if Telegram could not be queried."""

    try:
        peer = await client.resolve_peer(user_id)
        result = await client.invoke(
            functions.users.GetFullUser(id=peer)
        )
        full_user = getattr(result, "full_user", None)

        if full_user is not None:
            about = getattr(full_user, "about", None)
            if about is not None:
                return about or ""

    except Exception as exc:
        logger.warning("Raw bio lookup failed for %s: %s", user_id, exc)

    try:
        from toxic import pro

        if pro and pro.is_connected:
            peer = await pro.resolve_peer(user_id)
            result = await pro.invoke(
                functions.users.GetFullUser(id=peer)
            )
            full_user = getattr(result, "full_user", None)

            if full_user is not None:
                about = getattr(full_user, "about", None)
                if about is not None:
                    return about or ""

    except Exception as exc:
        logger.debug("Userbot bio lookup failed for %s: %s", user_id, exc)

    try:
        chat = await client.get_chat(user_id)
        bio = getattr(chat, "bio", None)

        if bio is not None:
            return bio or ""

    except Exception as exc:
        logger.warning("Bio lookup failed for %s: %s", user_id, exc)

    return None


def make_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚙️ Open Settings", url="tg://settings"),
                InlineKeyboardButton(
                    "🟢 Verify Bio 🔄",
                    callback_data="verify_user_bio",
                ),
            ],
            [
                InlineKeyboardButton(
                    "📢 Main Channel",
                    url="https://t.me/Crazy_for_Goals",
                ),
                InlineKeyboardButton(
                    "💬 Contact Admin",
                    url="https://t.me/CrazyxDeveloper_Bot",
                ),
            ],
        ]
    )


def make_bio_prompt(user_id: int, first_name: str, chat_title=None):
    name = html.escape(first_name or "User")
    mention = f'<a href="tg://user?id={user_id}">{name}</a>'
    tag = html.escape(REQUIRED_TAG)

    heading = (
        f"Request for <b>{html.escape(chat_title)}</b>\n\n"
        if chat_title
        else ""
    )

    return (
        "🔒 <b>Access Denied ❌</b>\n\n"
        f"Hey {mention} 👋\n\n"
        f"{heading}"
        "Access is pending bio verification.\n\n"
        "💡 <b>Step 1</b>\n"
        "Add this tag to your personal Telegram Bio:\n\n"
        f"<blockquote><code>{tag}</code></blockquote>\n\n"
        "💡 <b>Step 2</b>\n"
        "After updating your Bio, tap <b>Verify Bio 🔄</b> below.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Your join request will be approved after successful verification."
    )


# ---------------------------------------------------
# Permanent join-request invite link
# ---------------------------------------------------

async def get_or_create_permanent_join_link(
    client: Client,
    chat_id: int,
    request_link=None,
    chat_obj=None,
) -> str:
    """
    Reuse the bot's own saved, non-expiring join-request link when possible.
    Otherwise create a new link without an expiry date or member limit.

    The bot must have permission to invite users in the target chat.
    """

    cached = await invite_link_db.find_one({"chat_id": chat_id})

    # Validate only links created/managed by this bot.
    if cached and cached.get("link"):
        try:
            invite = await client.get_chat_invite_link(
                chat_id,
                cached["link"],
            )

            is_request_link = getattr(
                invite,
                "creates_join_request",
                False,
            )
            is_revoked = getattr(invite, "is_revoked", False)
            expiry = getattr(invite, "expire_date", None)

            if (
                invite
                and invite.invite_link
                and is_request_link
                and not is_revoked
                and expiry is None
            ):
                return invite.invite_link

        except Exception as exc:
            logger.info(
                "Saved invite link for %s is unavailable: %s",
                chat_id,
                exc,
            )

    # Create a fresh permanent join-request link.
    try:
        invite = await client.create_chat_invite_link(
            chat_id=chat_id,
            name="Bio Verification Join Request",
            expire_date=None,
            member_limit=None,
            creates_join_request=True,
        )

        link = invite.invite_link

        await invite_link_db.update_one(
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "link": link,
                    "creates_join_request": True,
                }
            },
            upsert=True,
        )

        logger.info("Created permanent join-request link for %s", chat_id)
        return link

    except Exception as exc:
        logger.error(
            "Could not create join-request link for %s: %s",
            chat_id,
            exc,
        )

    # A request's original invite link may be used as a fallback,
    # but its permanence cannot be guaranteed.
    if request_link and getattr(request_link, "invite_link", None):
        return request_link.invite_link

    # Public channel fallback. This is NOT a dedicated join-request link.
    username = getattr(chat_obj, "username", None) if chat_obj else None

    if username:
        return f"https://t.me/{username}"

    return ""


# ---------------------------------------------------
# Common bio access check
# ---------------------------------------------------

async def check_user_bio_access(
    client: Client,
    message: Message,
) -> bool:
    if not message.from_user:
        return True

    user_id = message.from_user.id

    if user_id in OWNER_IDS or message.from_user.is_bot:
        return True

    bio = await get_fresh_user_bio(client, user_id)

    if bio is not None and has_bio_tag(bio):
        return True

    # Fail closed if bio lookup failed.
    text = make_bio_prompt(
        user_id,
        message.from_user.first_name,
    )

    if bio is None:
        text = (
            "⚠️ <b>Bio verification is temporarily unavailable.</b>\n\n"
            "Please try again shortly."
        )

    try:
        await message.reply_text(
            text,
            reply_markup=make_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning("Could not send bio prompt: %s", exc)

    return False


# ---------------------------------------------------
# Chat join request handler
# ---------------------------------------------------

@app.on_chat_join_request()
async def handle_chat_join_request(
    client: Client,
    request: ChatJoinRequest,
):
    user_id = request.from_user.id
    chat_id = request.chat.id

    chat_title = request.chat.title or "Channel/Group"
    safe_title = html.escape(chat_title)

    chat_link = await get_or_create_permanent_join_link(
        client,
        chat_id,
        request.invite_link,
        request.chat,
    )

    bio = await get_fresh_user_bio(client, user_id)

    if bio is not None and has_bio_tag(bio):
        try:
            await client.approve_chat_join_request(chat_id, user_id)
            logger.info("Approved join request for %s in %s", user_id, chat_id)
        except Exception as exc:
            logger.error("Join approval failed for %s: %s", user_id, exc)
            return

        try:
            await client.send_message(
                user_id,
                (
                    "🔓 <b>Access Granted & Bio Verified ✅</b>\n\n"
                    f"Welcome, <a href='tg://user?id={user_id}'>"
                    f"{html.escape(request.from_user.first_name or 'User')}</a>!\n\n"
                    "Your bio has been verified and your join request approved.\n\n"
                    f"📢 <b>Channel:</b> {safe_title}\n"
                    + (
                        f"🔗 <a href='{html.escape(chat_link, quote=True)}'>"
                        "Open channel</a>\n\n"
                        if chat_link
                        else "\n"
                    )
                    + f"Keep <code>{html.escape(REQUIRED_TAG)}</code> "
                    "in your Bio to retain access."
                ),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as exc:
            logger.info("Approval DM unavailable for %s: %s", user_id, exc)

        await join_req_db.delete_one(
            {"user_id": user_id, "chat_id": chat_id}
        )
        return

    await join_req_db.update_one(
        {"user_id": user_id, "chat_id": chat_id},
        {
            "$set": {
                "user_id": user_id,
                "chat_id": chat_id,
                "chat_title": chat_title,
                "chat_link": chat_link,
            }
        },
        upsert=True,
    )

    prompt = make_bio_prompt(
        user_id,
        request.from_user.first_name or "User",
        chat_title,
    )

    try:
        await client.send_message(
            user_id,
            prompt,
            reply_markup=make_keyboard(),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        logger.warning(
            "Could not DM join-request user %s: %s",
            user_id,
            exc,
        )


# ---------------------------------------------------
# Verify Bio callback
# ---------------------------------------------------

@app.on_callback_query(filters.regex(r"^verify_user_bio$"))
async def verify_user_bio_callback(
    client: Client,
    callback_query: CallbackQuery,
):
    user = callback_query.from_user
    user_id = user.id

    if user_id in OWNER_IDS:
        await callback_query.answer(
            "🔓 Owner access granted!",
            show_alert=True,
        )
        return

    bio = await get_fresh_user_bio(client, user_id)

    if bio is None:
        await callback_query.answer(
            "⚠️ Telegram bio could not be checked. Try again shortly.",
            show_alert=True,
        )
        return

    if not has_bio_tag(bio):
        await callback_query.answer(
            f"❌ Add {REQUIRED_TAG} to your personal Bio, then retry.",
            show_alert=True,
        )
        return

    await callback_query.answer(
        "🔓 Bio verified successfully!",
        show_alert=True,
    )

    pending = await join_req_db.find(
        {"user_id": user_id}
    ).to_list(length=100)

    approved = []
    failed = []

    for item in pending:
        chat_id = item.get("chat_id")

        try:
            await client.approve_chat_join_request(chat_id, user_id)
            approved.append(item)

            await join_req_db.delete_one({"_id": item["_id"]})

        except Exception as exc:
            logger.error(
                "Could not approve %s for chat %s: %s",
                user_id,
                chat_id,
                exc,
            )
            failed.append(item)

    name = html.escape(user.first_name or "User")
    mention = f'<a href="tg://user?id={user_id}">{name}</a>'

    response = (
        "🔓 <b>Bio Verification Successful ✅</b>\n\n"
        f"Welcome, {mention}!\n\n"
        f"Your Bio contains <code>{html.escape(REQUIRED_TAG)}</code>.\n\n"
    )

    if approved:
        response += "✅ <b>Approved join requests:</b>\n"

        for item in approved:
            title = html.escape(item.get("chat_title") or "Channel/Group")
            link = item.get("chat_link") or ""

            if link.startswith(("https://t.me/", "http://t.me/")):
                safe_link = html.escape(link, quote=True)
                response += (
                    f'• <a href="{safe_link}">{title}</a>\n'
                )
            else:
                response += f"• {title}\n"

        response += "\n"

    if failed:
        response += (
            "⚠️ Some join requests could not be approved automatically. "
            "Please contact the administrator.\n\n"
        )

    response += "👉 Send /start to proceed."

    try:
        if callback_query.message:
            await callback_query.message.edit_text(
                response,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
    except Exception as exc:
        logger.warning("Could not update verification message: %s", exc)
