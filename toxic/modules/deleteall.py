# ---------------------------------------------------
# File Name: deleteall.py
# Description: Mass message cleaner for Channels, Supergroups, and Forum Topics
#              Supports one-shot (/deleteall -f / /deleteall yes) & interactive confirmation
# ---------------------------------------------------

import asyncio
from typing import Optional
from pyrogram import filters, enums, raw
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError

from toxic import app
from toxic.core.mongo.db import is_admin_or_owner

ANONYMOUS_ADMIN_IDS = {1087968824, 777000}


async def _is_authorized_to_delete(chat_id: int, message: Message = None, callback_query: CallbackQuery = None, user_id: int = None) -> bool:
    """Verifies that the requester is a chat administrator or bot owner."""
    if message and message.chat.type == enums.ChatType.CHANNEL:
        if not message.from_user:
            return True

    if callback_query and callback_query.message and callback_query.message.chat.type == enums.ChatType.CHANNEL:
        if not callback_query.from_user:
            return True

    if not user_id:
        if callback_query and callback_query.from_user:
            user_id = callback_query.from_user.id
        elif message and message.from_user:
            user_id = message.from_user.id

    if not user_id:
        return False

    if user_id in ANONYMOUS_ADMIN_IDS:
        return True

    if is_admin_or_owner(user_id):
        return True

    try:
        member = await app.get_chat_member(chat_id, user_id)
        if member and member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
            return True
    except Exception:
        pass

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


async def execute_mass_clean(chat_id: int, trigger_msg_id: int, user_id: int, progress_sender, target_topic_id: Optional[int] = None):
    """
    Executes the full mass purge engine across channels, supergroups, basic groups, AND forum topics.
    1. Uses DeleteTopicHistory & GetReplies on forum topics
    2. Uses GetChatHistory on main chat
    3. Sweeps full backward sequential range in chunks of 100 to eliminate any missed/hidden messages
    """
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

    try:
        # STEP 1: Forum Topic Detection & Purge
        # If the supergroup has forum topics, scan topics and delete their history & replies
        await progress_sender("🔍 **Scanning forum topics & message threads...**")
        
        detected_topics = []
        if target_topic_id and target_topic_id > 1:
            detected_topics.append(target_topic_id)

        # Discover all forum topics in the supergroup
        for cl in clients:
            try:
                peer = await cl.resolve_peer(chat_id)
                offset_date = 0
                offset_id = 0
                offset_topic = 0
                seen = set()
                while True:
                    res = await cl.invoke(raw.functions.messages.GetForumTopics(
                        peer=peer,
                        offset_date=offset_date,
                        offset_id=offset_id,
                        offset_topic=offset_topic,
                        limit=100
                    ))
                    topics = getattr(res, "topics", [])
                    if not topics:
                        break
                    new_c = 0
                    for t in topics:
                        tid = getattr(t, "id", None)
                        if tid and tid not in seen:
                            seen.add(tid)
                            if tid not in detected_topics:
                                detected_topics.append(tid)
                            new_c += 1
                            offset_date = getattr(t, "date", offset_date)
                            top_msg = getattr(t, "top_message", 0)
                            offset_id = top_msg if top_msg else tid
                            offset_topic = tid
                    if new_c == 0:
                        break
                if detected_topics:
                    break
            except Exception as fe_err:
                print(f"[DELETEALL] GetForumTopics notice: {fe_err}")

        # Wipe topics history via MTProto DeleteTopicHistory + GetReplies
        topic_mids = []
        for tid in detected_topics:
            # 1. Native DeleteTopicHistory RPC
            for cl in clients:
                try:
                    peer = await cl.resolve_peer(chat_id)
                    await cl.invoke(raw.functions.channels.DeleteTopicHistory(
                        channel=peer,
                        top_msg_id=tid
                    ))
                    break
                except Exception:
                    pass

            # 2. Collect thread reply message IDs from this topic
            for cl in clients:
                try:
                    peer = await cl.resolve_peer(chat_id)
                    off_id = 0
                    while True:
                        rep = await cl.invoke(raw.functions.messages.GetReplies(
                            peer=peer,
                            msg_id=tid,
                            offset_id=off_id,
                            offset_date=0,
                            add_offset=0,
                            limit=100,
                            max_id=0,
                            min_id=0,
                            hash=0
                        ))
                        msgs = getattr(rep, "messages", [])
                        if not msgs:
                            break
                        m_ids = [m.id for m in msgs if getattr(m, "id", 0) and m.id != trigger_msg_id and m.id not in topic_mids]
                        if not m_ids:
                            break
                        topic_mids.extend(m_ids)
                        off_id = min(m_ids)
                        if len(topic_mids) > 5000:
                            break
                    break
                except Exception as rep_e:
                    print(f"[DELETEALL] Topic {tid} GetReplies: {rep_e}")

        if topic_mids:
            await progress_sender(f"🗑️ **Wiping `{len(topic_mids)}` messages inside forum topics...**")
            for k in range(0, len(topic_mids), 100):
                batch = topic_mids[k:k + 100]
                d = await _delete_batch_adaptive(clients, chat_id, batch)
                total_deleted += d
                await asyncio.sleep(0.1)

        # STEP 2: General / Root Chat History Scan
        max_passes = 10
        for pass_num in range(1, max_passes + 1):
            message_ids = []
            for scanner_client in clients:
                try:
                    async for msg in scanner_client.get_chat_history(chat_id, limit=3000):
                        if msg.id != trigger_msg_id and msg.id not in message_ids:
                            message_ids.append(msg.id)
                    if message_ids:
                        break
                except Exception as scan_err:
                    print(f"[DELETEALL] Chat history scan error: {scan_err}")

            if not message_ids:
                break

            await progress_sender(
                f"🗑️ **Deleting chat messages (Pass #{pass_num})...**\n\n"
                f"• Target in this pass: `{len(message_ids)}`\n"
                f"• Total Wiped So Far: `{total_deleted}` ✅"
            )

            for k in range(0, len(message_ids), 100):
                batch = message_ids[k:k + 100]
                d_count = await _delete_batch_adaptive(clients, chat_id, batch)
                total_deleted += d_count
                await asyncio.sleep(0.1)

            if len(message_ids) < 5:
                break

        # STEP 3: Deep Backward Sequential Range Sweep
        # Sweeps remaining messages from trigger_msg_id down to 1 in chunks of 100
        # Catches all service messages, unindexed topic messages, and media
        highest_id = trigger_msg_id - 1
        if highest_id > 0:
            await progress_sender(
                f"🧹 **Deep Sweep: Purging any remaining unindexed messages & media...**\n\n"
                f"• Scanned Range: `1` ➔ `{highest_id}`\n"
                f"• Total Wiped So Far: `{total_deleted}` ✅"
            )
            consecutive_zero = 0
            curr = highest_id
            while curr > 0:
                chunk_start = max(1, curr - 99)
                batch = list(range(curr, chunk_start - 1, -1))
                d_c = await _delete_batch_adaptive(clients, chat_id, batch)
                total_deleted += d_c
                if d_c == 0:
                    consecutive_zero += 1
                    if consecutive_zero >= 10:  # 1000 consecutive empty IDs
                        break
                else:
                    consecutive_zero = 0
                curr = chunk_start - 1
                await asyncio.sleep(0.08)

        await progress_sender(
            f"🎉 **Clean Complete!**\n\n"
            f"✅ Successfully wiped **`{total_deleted}`** messages across all topics & chat for everyone.\n"
            f"🧹 Group/Channel is now 100% clean!"
        )

    except Exception as e:
        await progress_sender(f"❌ **An error occurred during deletion:** `{str(e)}`")


@app.on_message(filters.command(["deleteall", "delall", "purgeall", "clearchat", "wipe"]))
async def delete_all_cmd(_, message: Message):
    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None) or getattr(message, "topic_id", None)

    # 1. Direct check: works in channels, supergroups, and basic groups
    if message.chat.type not in [enums.ChatType.CHANNEL, enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply("❌ **Error:** This command can only be used in channels or groups.")
        return

    # 2. Strict admin authorization check
    user_id = message.from_user.id if message.from_user else 0
    authorized = await _is_authorized_to_delete(chat_id, message=message, user_id=user_id)
    if not authorized:
        await message.reply("❌ **Access Denied:** Only administrators can use this command! You are not admin noob.")
        return

    # 3. Direct execution flag support (e.g. /deleteall -f, /deleteall confirm, /deleteall yes)
    cmd_text = (message.text or message.caption or "").strip().lower()
    auto_confirm = any(flag in cmd_text for flag in ["-f", "confirm", "yes", "now", "force"])

    if auto_confirm:
        status_msg = await message.reply("⌛ **Initializing mass deletion engine for everyone...**")

        async def edit_progress(txt: str):
            try:
                await status_msg.edit_text(txt)
            except Exception:
                pass

        await execute_mass_clean(chat_id, message.id, user_id, edit_progress, target_topic_id=topic_id)
        return

    # 4. Confirmation prompt with Delete All and Cancel buttons (works in both Groups & Channels)
    chat_label = "Channel" if message.chat.type == enums.ChatType.CHANNEL else "Group"
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete All", callback_data=f"confirm_delete_all:{topic_id or 0}"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete_all")
        ]
    ])

    topic_note = f" (Topic ID: `{topic_id}`)" if topic_id else ""
    await message.reply(
        f"⚠️ **{chat_label.upper()} MASS CLEAN WARNING{topic_note}:**\n\n"
        f"Are you absolutely sure you want to delete **all messages** in this {chat_label.lower()}?\n"
        f"This action is permanent and will wipe all messages for everyone!\n\n"
        f"*(Or send `/deleteall -f` to wipe directly without buttons)*",
        reply_markup=buttons
    )


@app.on_callback_query(filters.regex(r"^(confirm_delete_all(:(\d+))?|cancel_delete_all)$"))
async def delete_all_callback(_, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    prompt_msg_id = callback_query.message.id

    # Verify admin status of user who pressed the button
    authorized = await _is_authorized_to_delete(chat_id, callback_query=callback_query)
    if not authorized:
        await callback_query.answer("⚠️ You are not admin noob! ❌\nOnly chat administrators can click this button.", show_alert=True)
        return

    user_id = callback_query.from_user.id if callback_query.from_user else 0

    if callback_query.data == "cancel_delete_all":
        await callback_query.answer("Operation cancelled ✅", show_alert=False)
        try:
            await callback_query.message.edit_text("❌ **Operation cancelled.** No messages were deleted.")
        except Exception:
            pass
        return

    # Extract topic_id if passed in callback data
    topic_id = None
    data_parts = callback_query.data.split(":")
    if len(data_parts) > 1 and data_parts[1].isdigit():
        tid_val = int(data_parts[1])
        if tid_val > 0:
            topic_id = tid_val

    if not topic_id:
        topic_id = getattr(callback_query.message, "message_thread_id", None) or getattr(callback_query.message, "topic_id", None)

    await callback_query.answer("Starting Mass Deletion 🧹", show_alert=False)
    try:
        await callback_query.message.edit_text("⌛ **Initializing mass deletion engine for everyone...**")
    except Exception:
        pass

    async def edit_progress(txt: str):
        try:
            await callback_query.message.edit_text(txt)
        except Exception:
            pass

    await execute_mass_clean(chat_id, prompt_msg_id, user_id, edit_progress, target_topic_id=topic_id)
