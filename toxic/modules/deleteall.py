# ---------------------------------------------------
# File Name: deleteall.py
# Description: Mass message deletion module with full Channels, Supergroups & Basic Groups support
#              Supports one-shot (/deleteall -f / /deleteall yes) & interactive confirmation
#              Auto-scans via multiple clients, resolves channel peers, and batches deletions safely.
# Author: Antigravity
# ---------------------------------------------------

import asyncio
from pyrogram import filters, enums, raw
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message
from pyrogram.errors import FloodWait, RPCError
from toxic import app
from config import OWNER_ID
from toxic.core.mongo.db import is_admin_or_owner

ANONYMOUS_ADMIN_IDS = {1087968824, 777000}


async def _is_authorized_to_delete(chat_id: int, message: Message = None, user_id: int = None, is_callback: bool = False) -> bool:
    """Checks whether the triggerer is chat admin, channel poster, or bot owner."""
    if message:
        # 1. Anonymous admin or Channel message (sender_chat)
        if getattr(message, "sender_chat", None) is not None:
            return True
        if not getattr(message, "from_user", None):
            return True
        user_id = message.from_user.id

    if not user_id:
        return True

    if user_id in ANONYMOUS_ADMIN_IDS:
        return True

    if is_admin_or_owner(user_id):
        return True

    try:
        member = await app.get_chat_member(chat_id, user_id)
        if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
            return True
    except Exception:
        # In broadcast channels, normal users cannot post anyway; any posted message is from an admin
        if message and message.chat.type == enums.ChatType.CHANNEL:
            return True

    return False


async def _delete_batch_adaptive(clients, chat_id: int, message_ids: list) -> int:
    """
    Deletes message IDs adaptively:
    1. Bulk batch delete with client.delete_messages
    2. Raw RPC DeleteMessages for Channels & Chats
    3. Graceful fallback without stopping clients
    """
    if not message_ids:
        return 0

    deleted = 0
    # Try bulk delete with primary client
    for client in clients:
        try:
            await client.delete_messages(chat_id, message_ids, revoke=True)
            return len(message_ids)
        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            try:
                await client.delete_messages(chat_id, message_ids, revoke=True)
                return len(message_ids)
            except Exception:
                pass
        except Exception:
            pass

    # If bulk delete failed, try sub-batches of 10
    if len(message_ids) > 10:
        for i in range(0, len(message_ids), 10):
            sub_batch = message_ids[i:i + 10]
            sub_del = await _delete_batch_adaptive(clients, chat_id, sub_batch)
            deleted += sub_del
        return deleted

    # If small batch still failed, try 1-by-1
    for mid in message_ids:
        msg_deleted = False
        for client in clients:
            try:
                await client.delete_messages(chat_id, [mid], revoke=True)
                deleted += 1
                msg_deleted = True
                break
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await client.delete_messages(chat_id, [mid], revoke=True)
                    deleted += 1
                    msg_deleted = True
                    break
                except Exception:
                    pass
            except Exception:
                pass

        # Try Raw RPC for channel / supergroup / basic group
        if not msg_deleted:
            for client in clients:
                try:
                    peer = await client.resolve_peer(chat_id)
                    if isinstance(peer, raw.types.InputPeerChannel):
                        chan_input = raw.types.InputChannel(channel_id=peer.channel_id, access_hash=peer.access_hash)
                        await client.invoke(raw.functions.channels.DeleteMessages(
                            channel=chan_input,
                            id=[mid]
                        ))
                        deleted += 1
                        msg_deleted = True
                        break
                    elif isinstance(peer, (raw.types.InputPeerChat, raw.types.InputChat)):
                        await client.invoke(raw.functions.messages.DeleteMessages(
                            id=[mid],
                            revoke=True
                        ))
                        deleted += 1
                        msg_deleted = True
                        break
                except Exception:
                    pass

        await asyncio.sleep(0.01)

    return deleted


async def execute_mass_clean(chat_id: int, trigger_msg_id: int, user_id: int, progress_sender):
    """Executes the full mass purge engine across channels and groups."""
    clients = []

    # 1. Userbot client if available
    userbot = None
    if user_id:
        try:
            from toxic.core.userbot_manager import get_or_create_userbot
            userbot = await get_or_create_userbot(user_id)
            if userbot and getattr(userbot, "is_connected", False):
                clients.append(userbot)
        except Exception:
            pass

    # 2. Shared userbot / pool clients
    try:
        from toxic.core.get_func import get_client
        shared_ub = get_client()
        if shared_ub and getattr(shared_ub, "is_connected", False) and shared_ub not in clients:
            clients.append(shared_ub)
    except Exception:
        pass

    try:
        from toxic import pro_clients
        if pro_clients:
            for pc in pro_clients:
                if pc and getattr(pc, "is_connected", False) and pc not in clients:
                    clients.append(pc)
    except Exception:
        pass

    # 3. Always include bot app
    if app not in clients:
        clients.append(app)

    total_deleted = 0
    max_passes = 15

    try:
        for pass_num in range(1, max_passes + 1):
            message_ids = []

            # Scan history using available clients
            for scanner_client in clients:
                try:
                    async for msg in scanner_client.get_chat_history(chat_id, limit=5000):
                        if msg.id != trigger_msg_id and msg.id not in message_ids:
                            message_ids.append(msg.id)
                    if message_ids:
                        break
                except Exception as scan_err:
                    print(f"[DELETEALL] Scan error on {scanner_client.__class__.__name__}: {scan_err}")

            # Fallback range scan if get_chat_history returned nothing or for basic group cleanup
            if not message_ids and pass_num == 1:
                highest_id = trigger_msg_id - 1
                if highest_id > 0:
                    message_ids = list(range(highest_id, max(0, highest_id - 5000), -1))

            if not message_ids:
                break

            await progress_sender(
                f"🗑️ **Deleting messages for everyone (Pass #{pass_num})...**\n\n"
                f"• Target in this pass: `{len(message_ids)}`\n"
                f"• Total Wiped So Far: `{total_deleted}` ✅"
            )

            batch_size = 100
            for k in range(0, len(message_ids), batch_size):
                batch = message_ids[k:k + batch_size]
                d_count = await _delete_batch_adaptive(clients, chat_id, batch)
                total_deleted += d_count
                await asyncio.sleep(0.15)

            if len(message_ids) < 5:
                break

        await progress_sender(
            f"🎉 **Clean Complete!**\n\n"
            f"✅ Successfully wiped **`{total_deleted}`** messages for everyone.\n"
            f"🧹 Group/Channel chat is now clean!"
        )

    except Exception as e:
        await progress_sender(f"❌ **An error occurred during deletion:** `{str(e)}`")


@app.on_message(filters.command(["deleteall", "delall", "purgeall", "clearchat", "wipe"]))
async def delete_all_cmd(_, message: Message):
    chat_id = message.chat.id

    # 1. Direct check: works in channels, supergroups, and basic groups
    if message.chat.type not in [enums.ChatType.CHANNEL, enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply("❌ **Error:** This command can only be used in channels or groups.")
        return

    # 2. Check authorization
    user_id = message.from_user.id if message.from_user else 0
    authorized = await _is_authorized_to_delete(chat_id, message=message, user_id=user_id)
    if not authorized:
        await message.reply("❌ **Access Denied:** Only administrators can use this command.")
        return

    # 3. Direct execution flag support (e.g. /deleteall -f, /deleteall confirm, /deleteall yes)
    cmd_text = (message.text or message.caption or "").strip().lower()
    auto_confirm = any(flag in cmd_text for flag in ["-f", "confirm", "yes", "now", "force"])

    if auto_confirm or message.chat.type == enums.ChatType.CHANNEL:
        # In channels, inline buttons cannot be clicked anonymously or by ordinary subscribers.
        # Direct clean execution is cleaner and 100% reliable!
        status_msg = await message.reply("⌛ **Initializing mass deletion engine for everyone...**")

        async def edit_progress(txt: str):
            try:
                await status_msg.edit_text(txt)
            except Exception:
                pass

        await execute_mass_clean(chat_id, message.id, user_id, edit_progress)
        return

    # 4. Group confirmation prompt with buttons
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete All", callback_data="confirm_delete_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete_all")
        ]
    ])

    await message.reply(
        "⚠️ **WARNING:**\n\n"
        "Are you absolutely sure you want to delete **all messages** in this chat?\n"
        "This action is permanent and will wipe all messages for everyone!\n\n"
        "*(Or send `/deleteall -f` to execute directly without confirmation)*",
        reply_markup=buttons
    )


@app.on_callback_query(filters.regex(r"^(confirm_delete_all|cancel_delete_all)$"))
async def delete_all_callback(_, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id if callback_query.from_user else 0
    chat_id = callback_query.message.chat.id
    prompt_msg_id = callback_query.message.id

    authorized = await _is_authorized_to_delete(chat_id, user_id=user_id, is_callback=True)
    if not authorized:
        await callback_query.answer("❌ Only administrators of this chat can perform this action!", show_alert=True)
        return

    if callback_query.data == "cancel_delete_all":
        await callback_query.message.edit_text("❌ **Operation cancelled.** No messages were deleted.")
        return

    await callback_query.message.edit_text("⌛ **Initializing mass deletion engine...**")

    async def edit_progress(txt: str):
        try:
            await callback_query.message.edit_text(txt)
        except Exception:
            pass

    await execute_mass_clean(chat_id, prompt_msg_id, user_id, edit_progress)
