# ---------------------------------------------------
# File Name: deleteall.py
# Description: Mass message deletion module for Groups, Supergroups & Channels
# Author: Antigravity
# ---------------------------------------------------

import asyncio
from pyrogram import filters, enums, raw
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import FloodWait, RPCError
from toxic import app
from config import OWNER_ID
from toxic.core.mongo.db import is_admin_or_owner

@app.on_message(filters.command(["deleteall", "delall", "purgeall", "clearchat", "wipe"]))
async def delete_all_cmd(_, message):
    chat_id = message.chat.id
    
    # 1. Direct check: works in channels, supergroups, and basic groups
    if message.chat.type not in [enums.ChatType.CHANNEL, enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply("❌ **Error:** This command can only be used in channels or groups.")
        return

    # 2. Check authorization of the sender (if sent by a user)
    if message.from_user:
        user_id = message.from_user.id
        if not is_admin_or_owner(user_id):
            # Check if they are admin in this chat
            try:
                member = await app.get_chat_member(chat_id, user_id)
                if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply("❌ **Access Denied:** Only administrators can use this command.")
                    return
            except Exception:
                await message.reply("❌ **Access Denied:** You are not authorized here.")
                return

    # 3. Send confirmation message with buttons
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete All", callback_data="confirm_delete_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete_all")
        ]
    ])
    
    await message.reply(
        "⚠️ **WARNING:**\n\n"
        "Are you absolutely sure you want to delete **all messages** in this chat?\n"
        "This action is permanent and will wipe all group/channel messages for everyone!",
        reply_markup=buttons
    )

async def _delete_batch_adaptive(clients, chat_id, message_ids):
    """
    Deletes a list of message IDs adaptively:
    Tries bulk batch delete with revoke=True first.
    If bulk fails, breaks down into small sub-batches (10), then 1-by-1.
    Tries all available clients and MTProto raw RPC for Channels & Groups.
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
            sub_batch = message_ids[i:i+10]
            sub_del = await _delete_batch_adaptive(clients, chat_id, sub_batch)
            deleted += sub_del
        return deleted

    # If small batch still failed, delete message 1-by-1 to skip non-deletables
    for mid in message_ids:
        msg_deleted = False
        for client in clients:
            try:
                await client.delete_messages(chat_id, mid, revoke=True)
                deleted += 1
                msg_deleted = True
                break
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await client.delete_messages(chat_id, mid, revoke=True)
                    deleted += 1
                    msg_deleted = True
                    break
                except Exception:
                    pass
            except Exception:
                pass

        # Try Raw RPC for channel / supergroup / basic group if high-level failed
        if not msg_deleted:
            for client in clients:
                try:
                    peer = await client.resolve_peer(chat_id)
                    if isinstance(peer, (raw.types.InputPeerChannel, raw.types.InputChannel)):
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


@app.on_callback_query(filters.regex(r"^(confirm_delete_all|cancel_delete_all)$"))
async def delete_all_callback(_, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    prompt_msg_id = callback_query.message.id
    
    # Verify clicker's rights (Must be chat owner, chat administrator, or bot owner/admin)
    authorized = False
    if is_admin_or_owner(user_id):
        authorized = True
    else:
        try:
            member = await app.get_chat_member(chat_id, user_id)
            if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                authorized = True
        except Exception:
            pass

    if not authorized:
        await callback_query.answer("❌ Only administrators of this chat can perform this action!", show_alert=True)
        return

    if callback_query.data == "cancel_delete_all":
        await callback_query.message.edit_text("❌ **Operation cancelled.** No messages were deleted.")
        return

    # Confirm delete all
    await callback_query.message.edit_text("⌛ **Initializing mass deletion engine...**")
    
    userbot = None
    try:
        from toxic.modules.main import initialize_userbot
        userbot = await initialize_userbot(user_id)
    except Exception:
        pass

    # Try shared userbot if user's own userbot is not logged in
    shared_ub = None
    try:
        from toxic.core.get_func import get_client
        shared_ub = get_client()
    except Exception:
        pass

    clients = []
    if userbot:
        clients.append(userbot)
    if shared_ub and shared_ub not in clients:
        clients.append(shared_ub)
    clients.append(app)

    total_deleted = 0
    max_passes = 15  # Multi-pass loop ensures zero messages are left behind

    try:
        for pass_num in range(1, max_passes + 1):
            message_ids = []
            
            # Scan history using available clients
            for scanner_client in clients:
                try:
                    async for msg in scanner_client.get_chat_history(chat_id, limit=5000):
                        if msg.id != prompt_msg_id and msg.id not in message_ids:
                            message_ids.append(msg.id)
                    if message_ids:
                        break
                except Exception as scan_err:
                    print(f"[DELETEALL] Scan error on client {scanner_client.__class__.__name__}: {scan_err}")

            # Fallback range scan if get_chat_history returned nothing or for basic group cleanup
            if not message_ids and pass_num == 1:
                highest_id = prompt_msg_id - 1
                if highest_id > 0:
                    message_ids = list(range(highest_id, 0, -1))

            if not message_ids:
                break

            await callback_query.message.edit_text(
                f"🗑️ **Deleting messages for everyone (Pass #{pass_num})...**\n\n"
                f"• Target in this pass: `{len(message_ids)}`\n"
                f"• Total Wiped So Far: `{total_deleted}` ✅"
            )

            batch_size = 100
            for k in range(0, len(message_ids), batch_size):
                batch = message_ids[k:k+batch_size]
                d_count = await _delete_batch_adaptive(clients, chat_id, batch)
                total_deleted += d_count
                await asyncio.sleep(0.2)

            # If very few messages were found, no need for more passes
            if len(message_ids) < 5:
                break

        await callback_query.message.edit_text(
            f"🎉 **Clean Complete!**\n\n"
            f"✅ Successfully wiped **`{total_deleted}`** messages for everyone.\n"
            f"🧹 Group/Channel chat is now clean!"
        )
        
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **An error occurred during deletion:** `{str(e)}`")
    finally:
        if userbot:
            try:
                await userbot.stop()
            except Exception:
                pass
