# ---------------------------------------------------
# File Name: clean_service.py
# Description: Auto-deletes all service messages (joined group, left group, name change,
#              photo update, pinned, video chats, etc.) in groups, supergroups & channels.
#              Auto-locks all member permissions (send messages, topics, media, etc.) on add.
# ---------------------------------------------------

import asyncio
from pyrogram import filters, enums, raw
from pyrogram.types import Message, ChatMemberUpdated, ChatPermissions
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
    # CRITICAL: NEVER delete Forum Topic creation, edit, or status messages!
    # In Telegram, deleting a topic's creation service message destroys/deletes the entire forum topic!
    if (
        getattr(message, "forum_topic_created", None)
        or getattr(message, "forum_topic_edited", None)
        or getattr(message, "forum_topic_closed", None)
        or getattr(message, "forum_topic_reopened", None)
        or getattr(message, "general_forum_topic_hidden", None)
        or getattr(message, "general_forum_topic_unhidden", None)
    ):
        return
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
                await client.delete_messages(chat.id, [msg_id], revoke=True)
                print(f"[ServiceClean] 🧹 Auto-deleted service message {msg_id} in {chat.type.name} '{chat.title}' ({chat.id})")
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                try:
                    await client.delete_messages(chat.id, [msg_id], revoke=True)
                except Exception:
                    pass
            except RPCError as rpc_err:
                print(f"[ServiceClean] ⚠️ Could not delete service message {msg_id} in {chat.id} with bot: {rpc_err}. Trying userbot fallback...")
                try:
                    from toxic.core.userbot_manager import _active_userbots
                    for ub in _active_userbots.values():
                        if ub and getattr(ub, "is_connected", False):
                            await ub.delete_messages(chat.id, [msg_id], revoke=True)
                            print(f"[ServiceClean] 🧹 Userbot fallback deleted service message {msg_id} in {chat.id}")
                            break
                except Exception:
                    pass
            except Exception as del_err:
                print(f"[ServiceClean] ⚠️ Delete error for message {msg_id}: {del_err}")
    except Exception as e:
        print(f"[ServiceClean] Error in service cleaner: {e}")


# Extra fallback for ANY message that has service attributes or action set
@app.on_message(filters.group | filters.channel, group=-9)
async def fallback_check_service_actions(client, message: Message):
    try:
        if (
            getattr(message, "forum_topic_created", None)
            or getattr(message, "forum_topic_edited", None)
            or getattr(message, "forum_topic_closed", None)
            or getattr(message, "forum_topic_reopened", None)
            or getattr(message, "general_forum_topic_hidden", None)
            or getattr(message, "general_forum_topic_unhidden", None)
        ):
            return
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
            try:
                await client.delete_messages(message.chat.id, [message.id], revoke=True)
                print(f"[ServiceClean] 🧹 Auto-deleted fallback service message {message.id} in {message.chat.id}")
            except Exception:
                pass
    except Exception:
        pass


def _extract_chat_id_from_peer(peer) -> int:
    """Helper to convert raw peer objects to Pyrogram's signed 64-bit chat IDs."""
    if isinstance(peer, raw.types.PeerChannel):
        return int(f"-100{peer.channel_id}")
    elif isinstance(peer, raw.types.PeerChat):
        return -int(peer.chat_id)
    return 0


# Raw update handler to intercept raw service messages before Telegram UI finishes dispatching
@app.on_raw_update(group=-10)
async def raw_service_cleaner(client, update, users, chats):
    try:
        raw_msgs = []

        if isinstance(update, (raw.types.Updates, raw.types.UpdatesCombined)):
            for up in getattr(update, "updates", []):
                if isinstance(up, (raw.types.UpdateNewChannelMessage, raw.types.UpdateNewMessage)):
                    m = getattr(up, "message", None)
                    if isinstance(m, raw.types.MessageService):
                        raw_msgs.append(m)

        elif isinstance(update, (raw.types.UpdateNewChannelMessage, raw.types.UpdateNewMessage)):
            m = getattr(update, "message", None)
            if isinstance(m, raw.types.MessageService):
                raw_msgs.append(m)

        for raw_msg in raw_msgs:
            peer = getattr(raw_msg, "peer_id", None)
            target_chat_id = _extract_chat_id_from_peer(peer)
            if not target_chat_id:
                continue

            action = getattr(raw_msg, "action", None)
            # NEVER delete Forum Topic actions (TopicCreate, TopicEdit)
            if isinstance(action, (raw.types.MessageActionTopicCreate, raw.types.MessageActionTopicEdit)):
                continue
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


# Helper to lock all permissions for members in a group / supergroup
async def lock_all_group_permissions(client, chat_id: int):
    """
    Turns off all permissions for normal members:
    - Send messages
    - Send media (photos, videos, docs, audios, stickers, gifs, etc.)
    - Add web page previews
    - Send polls
    - Change chat info
    - Pin messages
    - Create/manage forum topics
    """
    try:
        # ChatPermissions with all_perms=False or explicitly False denies everything
        strict_permissions = ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=True,  # Keep invite link enabled so members can join
            can_pin_messages=False,
            can_manage_topics=False,
            can_send_audios=False,
            can_send_docs=False,
            can_send_games=False,
            can_send_gifs=False,
            can_send_inline=False,
            can_send_photos=False,
            can_send_plain=False,
            can_send_roundvideos=False,
            can_send_stickers=False,
            can_send_videos=False,
            can_send_voices=False
        )
        await client.set_chat_permissions(chat_id, strict_permissions)
        print(f"[AUTO PERMISSIONS] 🔒 All member permissions (send messages, media, topics) turned OFF in chat {chat_id}")
    except RPCError as rpc:
        print(f"[AUTO PERMISSIONS] ⚠️ Could not set permissions for {chat_id}: {rpc}")
    except Exception as e:
        print(f"[AUTO PERMISSIONS] ⚠️ Error locking permissions in {chat_id}: {e}")


# Auto-lock permissions when the bot is added or promoted in a group
# NOTE: Disabled auto-locking of chat permissions because setting can_manage_topics=False
# was preventing users and bots from creating/managing forum topics!
# @app.on_chat_member_updated()
async def auto_lock_permissions_on_bot_added_disabled(client, chat_member_updated: ChatMemberUpdated):
    try:
        my_id = (await client.get_me()).id
        new_member = chat_member_updated.new_chat_member
        
        # Check if the bot was added or promoted
        if new_member and new_member.user.id == my_id:
            chat = chat_member_updated.chat
            if chat.type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
                # When bot is added or promoted to admin, lock permissions for members
                if new_member.status in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.MEMBER]:
                    await asyncio.sleep(1)  # small breathing room for admin rights propagation
                    await lock_all_group_permissions(client, chat.id)
    except Exception as e:
        print(f"[AUTO PERMISSIONS] Error in chat_member_updated listener: {e}")


# ─────────────────────────────────────────────────────────────
# 🧹 MANUAL CLEAN & PURGE COMMANDS FOR SERVICE MESSAGES
# ─────────────────────────────────────────────────────────────

@app.on_message(filters.command(["del", "delete"]) & (filters.group | filters.channel))
async def delete_single_replied_message(client: Client, message: Message):
    """
    Reply to ANY message (especially stubborn service messages like 'joined via invite link')
    with /del or /delete to purge it instantly.
    """
    try:
        reply = message.reply_to_message
        if not reply:
            sent_hint = await message.reply("⚠️ **Please reply to the message you want to delete!**")
            await asyncio.sleep(4)
            try:
                await client.delete_messages(message.chat.id, [message.id, sent_hint.id], revoke=True)
            except Exception:
                pass
            return

        chat_id = message.chat.id
        msg_ids_to_del = [message.id, reply.id]

        deleted = False
        try:
            await client.delete_messages(chat_id, msg_ids_to_del, revoke=True)
            deleted = True
        except RPCError as rpc:
            # Try via active userbot if bot lacks admin rights
            from toxic.core.userbot_manager import _active_userbots
            for ub in _active_userbots.values():
                if ub and getattr(ub, "is_connected", False):
                    try:
                        await ub.delete_messages(chat_id, msg_ids_to_del, revoke=True)
                        deleted = True
                        break
                    except Exception:
                        pass

        if not deleted:
            sent_err = await message.reply("❌ **Could not delete:** Make sure the bot is an Admin with 'Delete Messages' permission enabled!")
            await asyncio.sleep(5)
            try:
                await client.delete_messages(chat_id, [message.id, sent_err.id], revoke=True)
            except Exception:
                pass
    except Exception as e:
        print(f"[DelCommand] Error deleting message: {e}")


@app.on_message(filters.command(["cleanservice", "cleanservices", "cleansvc", "purgeservice"]) & (filters.group | filters.channel))
async def clean_all_existing_service_messages(client: Client, message: Message):
    """
    Sweeps through recent messages in the group/topic and deletes ALL service messages:
    - User joined via invite link / added
    - User left or removed
    - Pinned messages
    - Chat title/photo updates
    - Video chat notifications
    """
    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else 0
    from toxic.core.mongo.db import is_admin_or_owner
    from toxic.modules.deleteall import _is_authorized_to_delete

    authorized = await _is_authorized_to_delete(chat_id, message=message, user_id=user_id)
    if not authorized:
        await message.reply("❌ **Access Denied:** Only administrators can use this command!")
        return

    topic_id = getattr(message, "message_thread_id", None)
    status_msg = await message.reply("🧹 **Scanning and sweeping service messages...**")

    service_ids = []
    try:
        # Search recent 300 messages for service messages
        async for m in client.get_chat_history(chat_id, limit=300):
            if not m:
                continue
            # If in a forum topic, only match messages in that topic
            m_topic = getattr(m, "message_thread_id", None)
            if topic_id and m_topic != topic_id:
                continue

            # Skip any forum topic message
            if (
                getattr(m, "forum_topic_created", None)
                or getattr(m, "forum_topic_edited", None)
                or getattr(m, "forum_topic_closed", None)
                or getattr(m, "forum_topic_reopened", None)
            ):
                continue

            is_service = (
                getattr(m, "service", False)
                or getattr(m, "new_chat_members", None)
                or getattr(m, "left_chat_member", None)
                or getattr(m, "new_chat_title", None)
                or getattr(m, "new_chat_photo", None)
                or getattr(m, "delete_chat_photo", None)
                or getattr(m, "pinned_message", None)
                or getattr(m, "video_chat_started", None)
                or getattr(m, "video_chat_ended", None)
                or getattr(m, "video_chat_members_invited", None)
                or getattr(m, "action", None) is not None
            )
            if is_service:
                service_ids.append(m.id)

        if service_ids:
            # Delete in chunks of 100
            total_deleted = 0
            for i in range(0, len(service_ids), 100):
                chk = service_ids[i:i + 100]
                try:
                    await client.delete_messages(chat_id, chk, revoke=True)
                    total_deleted += len(chk)
                except Exception:
                    # Userbot fallback
                    from toxic.core.userbot_manager import _active_userbots
                    for ub in _active_userbots.values():
                        if ub and getattr(ub, "is_connected", False):
                            try:
                                await ub.delete_messages(chat_id, chk, revoke=True)
                                total_deleted += len(chk)
                                break
                            except Exception:
                                pass

            await status_msg.edit(f"✅ **Cleaned {total_deleted} service messages successfully!** 🧹")
        else:
            await status_msg.edit("✨ **No service messages found to clean!**")

        await asyncio.sleep(4)
        try:
            await client.delete_messages(chat_id, [message.id, status_msg.id], revoke=True)
        except Exception:
            pass
    except Exception as err:
        print(f"[CleanService] Sweep error: {err}")
        try:
            await status_msg.edit(f"⚠️ **Notice:** Make sure bot has 'Delete Messages' admin permission! ({err})")
        except Exception:
            pass
