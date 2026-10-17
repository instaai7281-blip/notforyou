# ---------------------------------------------------
# File Name: clean_service.py
# Description: Auto-deletes all service messages (joined group, left group, pinned, etc.)
#              with top priority (group=-10) to keep groups & channels clean.
# ---------------------------------------------------

import asyncio
from pyrogram import filters, enums
from pyrogram.types import Message
from pyrogram.errors import RPCError, FloodWait
from toxic import app

# Target group/supergroup/channel service messages
SERVICE_FILTER = (
    filters.service
    | filters.new_chat_members
    | filters.left_chat_member
)

@app.on_message(SERVICE_FILTER, group=-10)
async def auto_delete_all_service_messages(client, message: Message):
    """
    Auto-deletes all service messages in groups and supergroups:
    - User joined the group (via invite link or added by admin/user)
    - User left or was removed from the group
    - Pinned message notifications
    - Forum topic created / edited / closed / reopened
    - Chat title / photo / video changed
    Runs at group=-10 so it executes before any other handler or filter.
    """
    try:
        if not message or not message.chat:
            return

        chat = message.chat
        # Target all groups, supergroups, and channels
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
                # Bot doesn't have 'delete_messages' admin permission in this group
                print(f"[ServiceClean] ⚠️ Could not delete service message {msg_id} in {chat.id}: {rpc_err}")
            except Exception as del_err:
                print(f"[ServiceClean] ⚠️ Delete error for message {msg_id}: {del_err}")
    except Exception as e:
        print(f"[ServiceClean] Error in service cleaner: {e}")


# Extra fallback for any service or action messages that might not be caught by filters.service
@app.on_message(filters.group, group=-9)
async def fallback_check_service_actions(client, message: Message):
    try:
        if getattr(message, "service", False) or getattr(message, "new_chat_members", None) or getattr(message, "left_chat_member", None) or getattr(message, "action", None):
            await message.delete()
            print(f"[ServiceClean] 🧹 Auto-deleted fallback service message {message.id} in {message.chat.id}")
    except Exception:
        pass
