# ---------------------------------------------------
# File Name: clean_service.py
# Description: Auto-deletes all service messages (joined group, left group, name change,
#              photo update, pinned, video chats, etc.) in groups, supergroups & channels.
# ---------------------------------------------------

import asyncio
from pyrogram import filters, enums, raw
from pyrogram.types import Message
from pyrogram.errors import RPCError, FloodWait
from toxic import app

# Target group/supergroup/channel service messages with comprehensive filters
SERVICE_FILTER = (
    filters.service
    | filters.new_chat_members
    | filters.left_chat_member
    | filters.new_chat_title
    | filters.new_chat_photo
    | filters.delete_chat_photo
    | filters.pinned_message
    | filters.video_chat_started
    | filters.video_chat_ended
    | filters.video_chat_members_invited
)


@app.on_message(SERVICE_FILTER, group=-10)
async def auto_delete_all_service_messages(client, message: Message):
    """
    Auto-deletes all service messages in groups and supergroups:
    - User joined the group (via invite link, added by admin/user, or request)
    - User left or was removed from the group
    - Group name / chat title changed (new_chat_title)
    - Group photo changed or removed (new_chat_photo, delete_chat_photo)
    - Pinned message notifications
    - Video chat started / ended / members invited
    - Forum topic created / edited / closed / reopened
    Runs at group=-10 so it executes before any other handler or filter.
    """
    try:
        if not message or not message.chat:
            return

        chat = message.chat
        if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP, enums.ChatType.CHANNEL):
            msg_id = getattr(message, "id", None)
            if not msg_id:
                return

            try:
                await message.delete()
                print(f"[ServiceClean] 🧹 Auto-deleted service message {msg_id} in {chat.type.name} '{chat.title}' ({chat.id})")
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await message.delete()
                except Exception:
                    pass
            except RPCError as rpc_err:
                print(f"[ServiceClean] ⚠️ Could not delete service message {msg_id} in {chat.id}: {rpc_err}")
            except Exception as del_err:
                print(f"[ServiceClean] ⚠️ Delete error for message {msg_id}: {del_err}")
    except Exception as e:
        print(f"[ServiceClean] Error in service cleaner: {e}")


# Extra fallback for ANY message that has service attributes or action set
@app.on_message(filters.group | filters.channel, group=-9)
async def fallback_check_service_actions(client, message: Message):
    try:
        is_service = (
            getattr(message, "service", False)
            or getattr(message, "new_chat_members", None)
            or getattr(message, "left_chat_member", None)
            or getattr(message, "new_chat_title", None)
            or getattr(message, "new_chat_photo", None)
            or getattr(message, "delete_chat_photo", None)
            or getattr(message, "pinned_message", None)
            or getattr(message, "group_chat_created", False)
            or getattr(message, "supergroup_chat_created", False)
            or getattr(message, "channel_chat_created", False)
            or getattr(message, "migrate_to_chat_id", None)
            or getattr(message, "migrate_from_chat_id", None)
            or getattr(message, "video_chat_started", None)
            or getattr(message, "video_chat_ended", None)
            or getattr(message, "video_chat_members_invited", None)
            or getattr(message, "action", None) is not None
        )
        if is_service:
            await message.delete()
            print(f"[ServiceClean] 🧹 Auto-deleted fallback service message {message.id} in {message.chat.id}")
    except Exception:
        pass


# Raw update handler to intercept raw service messages before Telegram UI finishes dispatching
@app.on_raw_update(group=-10)
async def raw_service_cleaner(client, update, users, chats):
    try:
        raw_msg = None
        target_chat_id = None

        if isinstance(update, raw.types.UpdateNewChannelMessage):
            raw_msg = getattr(update, "message", None)
            if isinstance(raw_msg, raw.types.MessageService):
                peer = getattr(raw_msg, "peer_id", None)
                if isinstance(peer, raw.types.PeerChannel):
                    target_chat_id = int(f"-100{peer.channel_id}")

        elif isinstance(update, raw.types.UpdateNewMessage):
            raw_msg = getattr(update, "message", None)
            if isinstance(raw_msg, raw.types.MessageService):
                peer = getattr(raw_msg, "peer_id", None)
                if isinstance(peer, raw.types.PeerChat):
                    target_chat_id = -int(peer.chat_id)
                elif isinstance(peer, raw.types.PeerChannel):
                    target_chat_id = int(f"-100{peer.channel_id}")

        if raw_msg and isinstance(raw_msg, raw.types.MessageService) and target_chat_id:
            action = getattr(raw_msg, "action", None)
            # Service actions: joined, left, title, photo, pin, call, etc.
            if action:
                msg_id = getattr(raw_msg, "id", None)
                if msg_id:
                    try:
                        await client.delete_messages(target_chat_id, [msg_id], revoke=True)
                        print(f"[ServiceClean] ⚡ Raw auto-deleted service message {msg_id} ({action.__class__.__name__}) in {target_chat_id}")
                    except Exception:
                        pass
    except Exception:
        pass
