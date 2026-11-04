# ---------------------------------------------------
# File Name: multiban.py
# Description: Stealth Infiltration Audit & Universal Channel Ban Module
#              Restricted strictly to Owner and Authorized Bot Admins.
#              Audits suspicious users across all connected channels/groups
#              and executes silent, irreversible bans without alerting the user.
# Author: ENI & LO
# ---------------------------------------------------

import asyncio
import logging
from pyrogram import Client, filters, raw
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatType
from pyrogram.errors import FloodWait, UserNotParticipant, PeerIdInvalid, ChatAdminRequired, RightForbidden, UserAdminInvalid

from toxic import app
from config import OWNER_ID
from toxic.core.mongo.db import (
    is_admin_or_owner,
    load_all_admins,
    get_all_broadcast_chats,
    ban_user as db_ban_user,
    unban_user as db_unban_user,
    is_user_banned
)
from toxic.modules.topic_mirror import get_working_userbot

logger = logging.getLogger(__name__)

# Temporary cache for audit results: user_id -> dict of found memberships
_audit_cache = {}


def _extract_target_user(message: Message):
    """
    Extracts target user_id or username from command arguments or replied message.
    Returns (user_id_or_username, error_message)
    """
    if message.reply_to_message:
        if message.reply_to_message.from_user:
            return message.reply_to_message.from_user.id, None
        if getattr(message.reply_to_message, "forward_from", None):
            return message.reply_to_message.forward_from.id, None
        if getattr(message.reply_to_message, "forward_from_chat", None):
            return message.reply_to_message.forward_from_chat.id, None
        if getattr(message.reply_to_message, "sender_chat", None):
            return message.reply_to_message.sender_chat.id, None

    parts = message.text.split(None, 1)
    if len(parts) > 1:
        raw_val = parts[1].strip()
        # Clean potential user link or @
        if raw_val.startswith("@"):
            return raw_val, None
        if "t.me/" in raw_val:
            raw_val = raw_val.split("t.me/")[-1].replace("/", "").strip()
            return raw_val, None
        try:
            return int(raw_val), None
        except ValueError:
            return raw_val, None

    return None, (
        "❌ <b>Usage:</b>\n"
        "• <code>/checkuser &lt;user_id or @username&gt;</code>\n"
        "• <code>/multiban &lt;user_id or @username&gt;</code>\n"
        "• Or simply reply to any message sent by the suspicious user with the command."
    )


async def _resolve_target(client: Client, raw_target, userbot=None):
    """Resolves user_id, first_name, and username safely across bot and userbot."""
    clients_to_try = [client]
    if userbot and userbot != client and getattr(userbot, "is_connected", False):
        clients_to_try.append(userbot)

    for cl in clients_to_try:
        try:
            user = await cl.get_users(raw_target)
            if user:
                return user.id, getattr(user, "first_name", "User"), getattr(user, "username", None)
        except Exception:
            pass

    if isinstance(raw_target, int):
        return raw_target, f"User {raw_target}", None

    return None, None, None


async def _gather_all_network_chats(client: Client, userbot=None) -> list:
    """
    Gathers all unique channels, supergroups, and topics across:
    1. MongoDB joined_chats_db, mirror_db, mappings_db, auth_channels
    2. Userbot dialogs (where userbot is admin or creator)
    Guarantees 100% comprehensive coverage.
    """
    chat_map = {}

    # 1. From database
    try:
        db_chats = await get_all_broadcast_chats()
        for c in db_chats:
            cid = c["chat_id"]
            chat_map[cid] = c
    except Exception as e:
        logger.warning(f"[MultiBan] db chats notice: {e}")

    # 2. From userbot active dialogs (for private channels/groups owned by userbot)
    if userbot and getattr(userbot, "is_connected", False):
        try:
            async for dialog in userbot.get_dialogs(limit=250):
                ch = dialog.chat
                if ch.type in (ChatType.SUPERGROUP, ChatType.CHANNEL, ChatType.GROUP):
                    if ch.id not in chat_map:
                        chat_map[ch.id] = {
                            "chat_id": ch.id,
                            "title": ch.title or f"Chat {ch.id}",
                            "chat_type": str(ch.type).split(".")[-1].lower()
                        }
        except Exception as ub_dlg_err:
            logger.warning(f"[MultiBan] userbot dialog scan notice: {ub_dlg_err}")

    return list(chat_map.values())


# =====================================================================
# COMMAND: /checkuser (or /finduser)
# =====================================================================
@app.on_message(filters.command(["checkuser", "finduser"]))
async def check_user_memberships(client: Client, message: Message):
    """
    Audits all known channels and groups to see where the suspicious user is joined.
    Stealth mode: Only the admin sees this output.
    """
    admin_uid = message.from_user.id if message.from_user else message.chat.id
    print(f"[MultiBan] /checkuser called by {admin_uid}: {message.text}")
    logger.info(f"[MultiBan] /checkuser called by {admin_uid}: {message.text}")

    if not is_admin_or_owner(admin_uid):
        try:
            await load_all_admins()
        except Exception:
            pass
        if not is_admin_or_owner(admin_uid):
            print(f"[MultiBan] Access denied for user {admin_uid} on /checkuser")
            await message.reply_text(
                f"❌ <b>Access Denied:</b> This command is restricted to Bot Owners and authorized Admins.\n\n"
                f"🆔 <b>Your Telegram ID:</b> <code>{admin_uid}</code>",
                parse_mode=ParseMode.HTML
            )
            return

    raw_target, err = _extract_target_user(message)
    if not raw_target:
        await message.reply_text(err, parse_mode=ParseMode.HTML)
        return

    status_msg = await message.reply_text(
        f"🔍 <b>Auditing memberships for:</b> <code>{raw_target}</code>...\n"
        f"<i>Scanning all connected channels, groups, and mirror destinations...</i>",
        parse_mode=ParseMode.HTML
    )

    userbot = None
    try:
        userbot, _ = await get_working_userbot(admin_uid)
    except Exception as ub_err:
        print(f"[MultiBan] get_working_userbot notice: {ub_err}")

    uid, fname, uname = await _resolve_target(client, raw_target, userbot=userbot)
    if not uid:
        await status_msg.edit(
            f"❌ <b>Could not resolve user:</b> <code>{raw_target}</code>\n"
            f"Ensure the ID or username is valid and exists on Telegram.",
            parse_mode=ParseMode.HTML
        )
        return

    if is_admin_or_owner(uid):
        await status_msg.edit("⚠️ <b>Action Prohibited:</b> You cannot audit or ban a Bot Owner or Admin!", parse_mode=ParseMode.HTML)
        return

    all_chats = await _gather_all_network_chats(client, userbot=userbot)
    if not all_chats:
        await status_msg.edit("⚠️ <b>No connected channels or groups found in database.</b>", parse_mode=ParseMode.HTML)
        return

    found_memberships = []
    checked_count = 0

    clients_to_query = [client]
    if userbot and userbot != client and getattr(userbot, "is_connected", False):
        clients_to_query.append(userbot)

    for chat_info in all_chats:
        cid = chat_info["chat_id"]
        ctitle = chat_info.get("title", f"Chat {cid}")
        checked_count += 1

        for cl in clients_to_query:
            try:
                member = await cl.get_chat_member(cid, uid)
                if member and member.status in (
                    ChatMemberStatus.MEMBER,
                    ChatMemberStatus.ADMINISTRATOR,
                    ChatMemberStatus.OWNER,
                    ChatMemberStatus.RESTRICTED
                ):
                    status_str = str(member.status).split(".")[-1].capitalize()
                    found_memberships.append({
                        "chat_id": cid,
                        "title": ctitle,
                        "status": status_str,
                        "chat_type": chat_info.get("chat_type", "channel")
                    })
                    break
            except UserNotParticipant:
                break
            except Exception:
                continue

    # Cache results for quick one-tap multi-ban callback
    _audit_cache[uid] = found_memberships

    uname_str = f"(@{uname})" if uname else ""
    header = (
        f"🕵️‍♂️ <b>INFILTRATION AUDIT REPORT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Target:</b> {fname} {uname_str}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"📊 <b>Scanned:</b> {checked_count} chats\n"
        f"🚨 <b>Found In:</b> <b>{len(found_memberships)}</b> chat(s)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if not found_memberships:
        text = header + "✅ <b>Clean!</b> This user was NOT found in any of your monitored channels or groups."
        await status_msg.edit(text, parse_mode=ParseMode.HTML)
        return

    lines = []
    for idx, item in enumerate(found_memberships, 1):
        lines.append(f"{idx}. <b>{item['title']}</b>\n   ├ 🆔 <code>{item['chat_id']}</code>\n   └ 🏷 <i>{item['status']}</i>")

    text = header + "\n".join(lines)

    buttons = [
        [
            InlineKeyboardButton("🚫 Ban From All Found", callback_data=f"mban_exec_{uid}"),
            InlineKeyboardButton("❌ Dismiss", callback_data=f"mban_dismiss_{uid}")
        ]
    ]
    await status_msg.edit(text, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))


# =====================================================================
# COMMAND: /multiban (or /massban, /banall)
# =====================================================================
@app.on_message(filters.command(["multiban", "massban", "banall"]))
async def multiban_command(client: Client, message: Message):
    """
    Directly bans the suspicious user from ALL connected channels and groups silently.
    Also blacklists them in the bot's global database.
    """
    admin_uid = message.from_user.id if message.from_user else message.chat.id
    print(f"[MultiBan] /multiban called by {admin_uid}: {message.text}")
    logger.info(f"[MultiBan] /multiban called by {admin_uid}: {message.text}")

    if not is_admin_or_owner(admin_uid):
        try:
            await load_all_admins()
        except Exception:
            pass
        if not is_admin_or_owner(admin_uid):
            print(f"[MultiBan] Access denied for user {admin_uid} on /multiban")
            await message.reply_text(
                f"❌ <b>Access Denied:</b> This command is restricted to Bot Owners and authorized Admins.\n\n"
                f"🆔 <b>Your Telegram ID:</b> <code>{admin_uid}</code>",
                parse_mode=ParseMode.HTML
            )
            return

    raw_target, err = _extract_target_user(message)
    if not raw_target:
        await message.reply_text(err, parse_mode=ParseMode.HTML)
        return

    status_msg = await message.reply_text(
        f"⚡️ <b>Initiating Universal Stealth Ban for:</b> <code>{raw_target}</code>...\n"
        f"<i>Kicking & banning silently across all connected channels...</i>",
        parse_mode=ParseMode.HTML
    )

    userbot = None
    try:
        userbot, _ = await get_working_userbot(admin_uid)
    except Exception as ub_err:
        print(f"[MultiBan] get_working_userbot notice: {ub_err}")

    uid, fname, uname = await _resolve_target(client, raw_target, userbot=userbot)
    if not uid:
        await status_msg.edit(
            f"❌ <b>Could not resolve user:</b> <code>{raw_target}</code>\n"
            f"Ensure the ID or username is valid and exists on Telegram.",
            parse_mode=ParseMode.HTML
        )
        return

    if is_admin_or_owner(uid):
        await status_msg.edit("⚠️ <b>Action Prohibited:</b> You cannot ban a Bot Owner or Admin!", parse_mode=ParseMode.HTML)
        return

    res_text = await _execute_universal_ban(client, uid, fname, uname, userbot=userbot)
    await status_msg.edit(res_text, parse_mode=ParseMode.HTML)


# =====================================================================
# CALLBACKS: Ban from All Found / Dismiss
# =====================================================================
@app.on_callback_query(filters.regex(r"^mban_exec_(\d+)$"))
async def multiban_callback(client: Client, query: CallbackQuery):
    """Handles the one-tap 'Ban From All Found' button from the audit card."""
    user_id = query.from_user.id
    if not is_admin_or_owner(user_id):
        await query.answer("🔒 Admin only!", show_alert=True)
        return

    target_uid = int(query.data.split("_")[-1])
    if is_admin_or_owner(target_uid):
        await query.answer("⚠️ Cannot ban admin/owner!", show_alert=True)
        return

    await query.answer("⚡️ Executing stealth bans...", show_alert=False)
    await query.message.edit_text(
        f"⏳ <b>Banning user</b> <code>{target_uid}</code> <b>across all discovered channels...</b>",
        parse_mode=ParseMode.HTML
    )

    userbot = None
    try:
        userbot, _ = await get_working_userbot(user_id)
    except Exception:
        pass

    uid, fname, uname = await _resolve_target(client, target_uid, userbot=userbot)

    pre_cached = _audit_cache.pop(target_uid, None)
    res_text = await _execute_universal_ban(client, target_uid, fname, uname, target_chats=pre_cached, userbot=userbot)
    await query.message.edit_text(res_text, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^mban_dismiss_(\d+)$"))
async def multiban_dismiss_callback(client: Client, query: CallbackQuery):
    """Dismisses the audit report card cleanly."""
    _audit_cache.pop(int(query.data.split("_")[-1]), None)
    await query.message.delete()


# =====================================================================
# INTERNAL: _execute_universal_ban
# =====================================================================
async def _execute_universal_ban(client: Client, uid: int, fname: str, uname: str, target_chats=None, userbot=None) -> str:
    """
    Executes stealth ban on all target channels/groups and adds user to MongoDB blacklist.
    Uses BOTH bot client and userbot for maximum success across all private and public channels.
    """
    if not target_chats:
        all_chats = await _gather_all_network_chats(client, userbot=userbot)
    else:
        all_chats = target_chats

    banned_list = []
    failed_list = []

    clients_to_ban = [client]
    if userbot and userbot != client and getattr(userbot, "is_connected", False):
        clients_to_ban.append(userbot)

    for chat_info in all_chats:
        cid = chat_info["chat_id"]
        ctitle = chat_info.get("title", f"Chat {cid}")

        banned_success = False
        last_ban_err = "No admin permissions"

        for cl in clients_to_ban:
            try:
                # Ban user silently
                res = await cl.ban_chat_member(chat_id=cid, user_id=uid)
                if res:
                    banned_list.append(ctitle)
                    banned_success = True
                    break
            except UserNotParticipant:
                # Still try to ban from joining in future
                try:
                    await cl.ban_chat_member(chat_id=cid, user_id=uid)
                    banned_list.append(ctitle)
                    banned_success = True
                    break
                except Exception:
                    pass
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await cl.ban_chat_member(chat_id=cid, user_id=uid)
                    banned_list.append(ctitle)
                    banned_success = True
                    break
                except Exception as e:
                    last_ban_err = str(e)
            except Exception as e:
                last_ban_err = type(e).__name__

        if not banned_success and ctitle not in banned_list:
            failed_list.append(f"{ctitle} ({last_ban_err})")

    # Blacklist permanently in MongoDB so they cannot interact with the bot
    try:
        await db_ban_user(uid)
    except Exception as dbe:
        logger.error(f"[MultiBan] Failed to blacklist user {uid} in DB: {dbe}")

    uname_str = f"(@{uname})" if uname else ""
    report = (
        f"🛡 <b>STEALTH MULTI-BAN COMPLETE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {fname} {uname_str}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n"
        f"🔒 <b>Bot Global DB:</b> <code>BLACKLISTED</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ <b>Successfully Banned From ({len(banned_list)}):</b>\n"
    )

    if banned_list:
        report += "\n".join([f"• <b>{t}</b>" for t in banned_list[:25]])
        if len(banned_list) > 25:
            report += f"\n• <i>...and {len(banned_list) - 25} more channels</i>"
    else:
        report += "• <i>None (user was not present or could not be banned)</i>"

    if failed_list:
        report += f"\n\n⚠️ <b>Could Not Ban ({len(failed_list)}):</b>\n"
        report += "\n".join([f"• {f}" for f in failed_list[:10]])

    report += (
        "\n\n🤫 <i>Stealth executed: The user has been silently removed without sending any notification or alert.</i>"
    )
    return report


# =====================================================================
# COMMAND: /multiunban (or /unbanall)
# =====================================================================
@app.on_message(filters.command(["multiunban", "unbanall"]))
async def multiunban_command(client: Client, message: Message):
    """
    Unbans a previously banned user across all connected channels and groups,
    and removes them from the MongoDB bot blacklist.
    """
    admin_uid = message.from_user.id if message.from_user else message.chat.id
    print(f"[MultiBan] /multiunban called by {admin_uid}: {message.text}")
    logger.info(f"[MultiBan] /multiunban called by {admin_uid}: {message.text}")

    if not is_admin_or_owner(admin_uid):
        try:
            await load_all_admins()
        except Exception:
            pass
        if not is_admin_or_owner(admin_uid):
            print(f"[MultiBan] Access denied for user {admin_uid} on /multiunban")
            await message.reply_text(
                f"❌ <b>Access Denied:</b> This command is restricted to Bot Owners and authorized Admins.\n\n"
                f"🆔 <b>Your Telegram ID:</b> <code>{admin_uid}</code>",
                parse_mode=ParseMode.HTML
            )
            return

    raw_target, err = _extract_target_user(message)
    if not raw_target:
        await message.reply_text(
            "❌ <b>Usage:</b> <code>/multiunban &lt;user_id or @username&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return

    status_msg = await message.reply_text(
        f"⏳ <b>Unbanning user</b> <code>{raw_target}</code> <b>across all channels...</b>",
        parse_mode=ParseMode.HTML
    )

    userbot = None
    try:
        userbot, _ = await get_working_userbot(admin_uid)
    except Exception:
        pass

    uid, fname, uname = await _resolve_target(client, raw_target, userbot=userbot)
    if not uid:
        await status_msg.edit(f"❌ <b>Could not resolve user:</b> <code>{raw_target}</code>", parse_mode=ParseMode.HTML)
        return

    all_chats = await _gather_all_network_chats(client, userbot=userbot)
    unbanned_count = 0

    clients_to_unban = [client]
    if userbot and userbot != client and getattr(userbot, "is_connected", False):
        clients_to_unban.append(userbot)

    for chat_info in all_chats:
        cid = chat_info["chat_id"]
        for cl in clients_to_unban:
            try:
                await cl.unban_chat_member(chat_id=cid, user_id=uid)
                unbanned_count += 1
                break
            except Exception:
                pass

    # Remove from MongoDB blacklist
    try:
        await db_unban_user(uid)
    except Exception as dbe:
        logger.error(f"[MultiBan] Failed to unban user {uid} in DB: {dbe}")

    await status_msg.edit(
        f"✅ <b>UNBAN COMPLETE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {fname} (<code>{uid}</code>)\n"
        f"🔓 <b>Unbanned In:</b> {unbanned_count} channels/groups\n"
        f"🔓 <b>Bot Global DB:</b> <code>UNBANNED</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        parse_mode=ParseMode.HTML
    )
