import asyncio
import datetime
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMemberUpdated
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
from toxic import app
from config import OWNER_ID
from toxic.core.mongo.db import (
    admin_filter,
    is_admin_or_owner,
    get_broadcast_config, 
    update_broadcast_config, 
    add_broadcast_deletion,
    add_joined_chat,
    get_all_joined_chats,
    get_all_broadcast_chats,
    remove_joined_chat,
    get_pending_deletions,
    remove_broadcast_deletion,
    get_custom_group_bio,
    set_custom_group_bio,
    reset_custom_group_bio,
    DEFAULT_GROUP_BIO
)

# Helper to check if sender is owner or admin
def is_owner(user_id):
    if not user_id:
        return False
    return is_admin_or_owner(user_id)

def get_broadcast_menu_keyboard(is_active=False, interval_mins=30, delete_after_mins=0, max_runs=0, run_count=0):
    try:
        from toxic.modules.smart_broadcast import get_sb_main_keyboard
        cfg = {
            "is_active": is_active,
            "enable_groups": True,
            "enable_channels": True,
            "enable_dms": True,
            "disable_web_page_preview": True,
            "interval_mins": interval_mins,
            "delete_after_seconds": delete_after_mins * 60,
            "max_runs": max_runs,
            "run_count": run_count,
            "fast_forward_mode": True
        }
        return get_sb_main_keyboard(cfg)
    except Exception:
        del_after_text = f"{delete_after_mins}m" if delete_after_mins else "Disabled ❌"
        max_runs_text = f"{max_runs}" if max_runs else "No Limit ♾️"
        buttons = [
            [InlineKeyboardButton(f"⚡ Status: {'ACTIVE ✅' if is_active else 'INACTIVE ❌'}", callback_data="sb_toggle_status")],
            [InlineKeyboardButton("📝 Set Message", callback_data="sb_set_message"), InlineKeyboardButton("⏱️ Set Interval", callback_data="sb_set_interval")],
            [InlineKeyboardButton(f"🗑️ Auto-Delete: {del_after_text}", callback_data="sb_set_delete_timer"), InlineKeyboardButton(f"🔢 Max Runs: {max_runs_text}", callback_data="sb_set_max_runs")],
            [InlineKeyboardButton("🔄 Reset Run Count", callback_data="sb_reset_count"), InlineKeyboardButton("🚀 Send Now", callback_data="sb_launch_now")],
            [InlineKeyboardButton("❌ Close Menu", callback_data="sb_close")]
        ]
        return InlineKeyboardMarkup(buttons)

@app.on_callback_query(filters.regex(r"^abc_"))
async def auto_broadcast_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_owner(user_id):
        await callback_query.answer("❌ Access Denied!", show_alert=True)
        return

    try:
        from toxic.modules.smart_broadcast import render_smart_broadcast_menu
        await render_smart_broadcast_menu(client, callback_query)
    except Exception as e:
        print(f"Error redirecting abc callback: {e}")


def get_interval_keyboard():
    try:
        from toxic.modules.smart_broadcast import get_sb_interval_keyboard
        return get_sb_interval_keyboard()
    except Exception:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="sb_back")]])

def get_delete_after_keyboard():
    try:
        from toxic.modules.smart_broadcast import get_sb_delete_timer_keyboard
        return get_sb_delete_timer_keyboard()
    except Exception:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="sb_back")]])

def get_max_runs_keyboard():
    try:
        from toxic.modules.smart_broadcast import get_sb_rounds_keyboard
        return get_sb_rounds_keyboard()
    except Exception:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="sb_back")]])


async def delete_all_active_broadcast_messages():
    # 1. Try starting the owner's userbot client
    owner_userbot = None
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    for owner_id in owner_list:
        try:
            from toxic.modules.main import initialize_userbot
            owner_userbot = await initialize_userbot(int(owner_id))
            if owner_userbot:
                break
        except Exception:
            pass

    from toxic.core.get_func import get_client
    shared_client = get_client()
    
    pending = await get_pending_deletions()
    deleted = 0
    try:
        for deletion in pending:
            chat_id = deletion["chat_id"]
            message_id = deletion["message_id"]
            
            client_to_use = owner_userbot if owner_userbot else (shared_client if shared_client else app)
            try:
                await client_to_use.delete_messages(chat_id, message_id)
                deleted += 1
            except Exception:
                if client_to_use != app:
                    try:
                        await app.delete_messages(chat_id, message_id)
                        deleted += 1
                    except Exception:
                        pass
            await remove_broadcast_deletion(deletion["_id"])
            await asyncio.sleep(0.1)
    finally:
        if owner_userbot:
            try:
                await owner_userbot.stop()
            except Exception:
                pass
    return deleted

async def send_auto_broadcast_to_all(manual=False):
    config = await get_broadcast_config()
    message_text = config.get("message")
    if not message_text:
        return 0, 0

    delete_after_mins = config.get("delete_after_mins", 0)
    
    # 1. Load from DB
    db_chats = await get_all_joined_chats()
    chat_ids = [c["chat_id"] for c in db_chats]
    
    # 2. Try starting the owner's userbot client
    owner_userbot = None
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    for owner_id in owner_list:
        try:
            from toxic.modules.main import initialize_userbot
            owner_userbot = await initialize_userbot(int(owner_id))
            if owner_userbot:
                break
        except Exception as e:
            print(f"Failed to initialize owner userbot: {e}")
            
    # If owner's userbot is active, sync dialogs first
    if owner_userbot:
        try:
            async for dialog in owner_userbot.get_dialogs(limit=250):
                chat = dialog.chat
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                    if chat.id not in chat_ids:
                        chat_ids.append(chat.id)
                        await add_joined_chat(chat.id, chat.title or "Unknown")
        except Exception as e:
            print(f"Owner userbot get_dialogs failed: {e}")

    # Fallback to shared userbot client if owner userbot not logged in
    from toxic.core.get_func import get_client
    shared_client = get_client()
    if not owner_userbot and shared_client:
        try:
            async for dialog in shared_client.get_dialogs(limit=200):
                chat = dialog.chat
                if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
                    if chat.id not in chat_ids:
                        chat_ids.append(chat.id)
                        await add_joined_chat(chat.id, chat.title or "Unknown")
        except Exception as e:
            print(f"Shared client get_dialogs failed: {e}")

    sent_count = 0
    failed_count = 0
    
    try:
        for cid in chat_ids:
            client_to_use = owner_userbot if owner_userbot else (shared_client if shared_client else app)
            try:
                sent_msg = await client_to_use.send_message(cid, message_text, disable_web_page_preview=True)
                sent_count += 1
                if delete_after_mins > 0:
                    delete_at = datetime.datetime.now() + datetime.timedelta(minutes=delete_after_mins)
                    await add_broadcast_deletion(cid, sent_msg.id, delete_at)
                await asyncio.sleep(0.5)  # Avoid rate limits
            except Exception as e:
                # Fallback to app client if userbot was used and failed
                if client_to_use != app:
                    try:
                        sent_msg = await app.send_message(cid, message_text, disable_web_page_preview=True)
                        sent_count += 1
                        if delete_after_mins > 0:
                            delete_at = datetime.datetime.now() + datetime.timedelta(minutes=delete_after_mins)
                            await add_broadcast_deletion(cid, sent_msg.id, delete_at)
                        await asyncio.sleep(0.5)
                        continue
                    except Exception as ae:
                        print(f"Fallback bot send failed for {cid}: {ae}")
                
                failed_count += 1
                print(f"Failed to send broadcast to chat {cid}: {e}")
                if "kicked" in str(e).lower() or "deactivated" in str(e).lower() or "chat not found" in str(e).lower():
                    await remove_joined_chat(cid)
    finally:
        if owner_userbot:
            try:
                await owner_userbot.stop()
            except Exception:
                pass
                
    return sent_count, failed_count

# Automatically track bot presence whenever a message is seen in a group/channel
@app.on_message((filters.group | filters.channel), group=-1)
async def log_bot_chat_presence(client: Client, message: Message):
    try:
        chat = message.chat
        title = chat.title or chat.username or "Group/Channel"
        await add_joined_chat(chat.id, title)
        c_type = "channel" if chat.type == ChatType.CHANNEL else "supergroup"
        try:
            from toxic.modules.smart_broadcast import add_sb_destination
            await add_sb_destination(chat.id, title, c_type)
        except Exception:
            pass
    except Exception:
        pass

@app.on_message(filters.command(["autobroadcast", "abc"]) & filters.private)
async def auto_broadcast_menu_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    try:
        from toxic.modules.smart_broadcast import render_smart_broadcast_menu
        await render_smart_broadcast_menu(client, message)
    except Exception as e:
        print(f"Error redirecting to smart broadcast menu: {e}")




# ────── Chat Member Updated (Bot Join/Kick Auto-Detection) ──────

@app.on_chat_member_updated()
async def on_bot_chat_member_updated(client: Client, chat_member_updated: ChatMemberUpdated):
    try:
        my_id = (await client.get_me()).id
        new_member = chat_member_updated.new_chat_member
        
        # Check if this update concerns the bot itself
        if new_member and new_member.user.id == my_id:
            chat = chat_member_updated.chat
            status = new_member.status
            title = chat.title or chat.username or "Group/Channel"
            c_type = "channel" if chat.type == ChatType.CHANNEL else "supergroup"
            
            # If bot was added as administrator or member
            if status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                await add_joined_chat(chat.id, title)
                try:
                    from toxic.modules.smart_broadcast import add_sb_destination
                    await add_sb_destination(chat.id, title, c_type)
                except Exception:
                    pass
                print(f"[AUTO DETECT] Bot added to chat: {title} (ID: {chat.id}). Added to broadcast list.")
                
                # Auto-update group description/bio with disclaimer & contact info
                try:
                    bio_text = await get_custom_group_bio()
                    await client.set_chat_description(chat.id, bio_text)
                    print(f"[AUTO BIO] Successfully updated bio for chat: {chat.title or chat.id} (ID: {chat.id})")
                except Exception as bio_err:
                    print(f"[AUTO BIO] Could not set bio for chat {chat.id}: {bio_err}")
            
            # If bot was kicked, banned, or left the chat
            elif status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                await remove_joined_chat(chat.id)
                try:
                    from toxic.modules.smart_broadcast import remove_sb_destination
                    await remove_sb_destination(chat.id)
                except Exception:
                    pass
                print(f"[AUTO DETECT] Bot left/kicked from chat: {title} (ID: {chat.id}). Removed from broadcast list.")
    except Exception as e:
        print(f"Error in on_bot_chat_member_updated: {e}")

# ────── Linked Chats Manual Management Commands ──────

@app.on_message(filters.command(["addchat"]) & filters.private)
async def add_chat_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/addchat <chat_id_or_username>`\n\nExample:\n• `/addchat -10012345678`\n• `/addchat @my_channel`")
        return

    chat_input = message.command[1]
    
    # Try resolving to integer ID and title
    try:
        chat = await client.get_chat(chat_input)
        chat_id = chat.id
        title = chat.title or chat.username or "Group/Channel"
    except Exception:
        # If bot cannot resolve directly (e.g. not in chat yet), check if integer
        try:
            chat_id = int(chat_input)
            title = "Manual Link (ID)"
        except ValueError:
            await message.reply_text("❌ **Error:** Invalid chat ID or username. Make sure the bot is added to that channel/group first!")
            return

    await add_joined_chat(chat_id, title)
    try:
        from toxic.modules.smart_broadcast import add_sb_destination
        c_type = "channel" if str(chat_id).startswith("-100") else "supergroup"
        await add_sb_destination(chat_id, title, c_type)
    except Exception:
        pass
    
    # Auto-update bio
    bio_status = "Skipped"
    try:
        bio_text = await get_custom_group_bio()
        await client.set_chat_description(chat_id, bio_text)
        bio_status = "Updated ✅"
    except Exception as e:
        bio_status = f"Failed ❌ ({e})"

    await message.reply_text(
        f"✅ **Linked Chat Added!**\n\n"
        f"• **Title:** `{title}`\n"
        f"• **ID:** `{chat_id}`\n"
        f"• **Group Bio:** {bio_status}"
    )

@app.on_message(filters.command(["removechat"]) & filters.private)
async def remove_chat_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/removechat <chat_id>`\n\nExample:\n• `/removechat -10012345678`")
        return

    chat_input = message.command[1]
    try:
        chat_id = int(chat_input)
    except ValueError:
        await message.reply_text("❌ **Error:** Please provide a valid integer Chat ID to remove.")
        return

    await remove_joined_chat(chat_id)
    try:
        from toxic.modules.smart_broadcast import remove_sb_destination
        await remove_sb_destination(chat_id)
    except Exception:
        pass
    await message.reply_text(f"✅ **Linked Chat Removed!**\n\n• **ID:** `{chat_id}`")

@app.on_message(filters.command(["listchats"]) & filters.private)
async def list_chats_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    db_chats = await get_all_joined_chats()
    if not db_chats:
        await message.reply_text("ℹ️ **No chats are currently linked.** Use `/addchat` or wait for the bot to auto-detect group/channel activity.")
        return

    text = "👥 **List of Linked Chats (Broadcast Destinations):**\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, chat in enumerate(db_chats, 1):
        text += f"{i}. **{chat['title']}**\n   • ID: `{chat['chat_id']}`\n\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    await message.reply_text(text)


# ────── Automatic Group Bio Management Commands ──────

@app.on_message(filters.command(["setbio", "updatebio"]))
async def set_group_bio_cmd(client: Client, message: Message):
    """Updates group bio for the current chat or specified chat ID."""
    user_id = message.from_user.id if message.from_user else 0
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    target_chat_id = message.chat.id
    if len(message.command) > 1 and message.chat.type == ChatType.PRIVATE:
        try:
            target_chat_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Error:** Please provide a valid integer Chat ID.\nUsage: `/setbio -10012345678`")
            return

    bio_text = await get_custom_group_bio()
    try:
        await client.set_chat_description(target_chat_id, bio_text)
        await message.reply_text(
            f"✅ **Group Bio Updated Successfully!**\n\n"
            f"📍 **Chat ID:** `{target_chat_id}`\n\n"
            f"📝 **Applied Bio:**\n```\n{bio_text}\n```"
        )
    except Exception as e:
        await message.reply_text(
            f"❌ **Failed to update group bio.**\n\n"
            f"• **Reason:** `{e}`\n"
            f"• *Make sure the bot is an Administrator with 'Change Group Info' permission in the group.*"
        )


@app.on_message(filters.command(["syncallbio", "updateallbio"]) & filters.private)
async def sync_all_group_bios_cmd(client: Client, message: Message):
    """Bulk updates group bio across all linked groups and saved mirror targets."""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    status_msg = await message.reply_text("⏳ **Starting automatic bio update across all linked groups...**")
    
    db_chats = await get_all_joined_chats()
    if not db_chats:
        await status_msg.edit("ℹ️ **No linked groups found in database.** Add groups using `/addchat` or let bot auto-detect them.")
        return

    bio_text = await get_custom_group_bio()
    success_count = 0
    fail_count = 0
    
    for chat in db_chats:
        c_id = chat.get("chat_id")
        try:
            await client.set_chat_description(c_id, bio_text)
            success_count += 1
            await asyncio.sleep(1)  # Rate-limit protection
        except Exception as err:
            fail_count += 1
            print(f"[SYNC BIO] Failed for chat {c_id}: {err}")

    await status_msg.edit(
        f"🎉 **Group Bio Sync Completed!**\n\n"
        f"✅ **Successfully Updated:** `{success_count}`\n"
        f"❌ **Failed / No Permission:** `{fail_count}`\n"
        f"📊 **Total Chats Processed:** `{len(db_chats)}`\n\n"
        f"📝 **Applied Bio Content:**\n```\n{bio_text}\n```"
    )


@app.on_message(filters.command(["custombio"]) & filters.private)
async def custom_bio_cmd(client: Client, message: Message):
    """Sets a custom global group bio template."""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    if len(message.text.split(None, 1)) < 2:
        current_bio = await get_custom_group_bio()
        await message.reply_text(
            f"ℹ️ **Current Group Bio Template:**\n\n```\n{current_bio}\n```\n\n"
            f"To set a new bio template, use:\n`/custombio <your new bio text>`\n\n"
            f"To reset to default, use `/resetbio`"
        )
        return

    new_bio = message.text.split(None, 1)[1].strip()
    if len(new_bio) > 255:
        await message.reply_text(f"❌ **Bio is too long!** Telegram description limit is 255 characters (Your text is {len(new_bio)} chars).")
        return

    await set_custom_group_bio(new_bio)
    await message.reply_text(
        f"✅ **Custom Group Bio Template Saved!**\n\n"
        f"All new groups will automatically receive this bio.\n\n"
        f"📝 **New Bio:**\n```\n{new_bio}\n```\n\n"
        f"Run `/syncallbio` to apply this new bio to all existing groups immediately!"
    )


@app.on_message(filters.command(["getbio"]) & filters.private)
async def get_bio_cmd(client: Client, message: Message):
    """Displays current group bio template."""
    current_bio = await get_custom_group_bio()
    await message.reply_text(
        f"📝 **Active Group Bio Template:**\n\n```\n{current_bio}\n```"
    )


@app.on_message(filters.command(["resetbio"]) & filters.private)
async def reset_bio_cmd(client: Client, message: Message):
    """Resets group bio template to default."""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    await reset_custom_group_bio()
    default_bio = DEFAULT_GROUP_BIO
    await message.reply_text(
        f"🔄 **Group Bio Reset to Default!**\n\n"
        f"📝 **Default Bio:**\n```\n{default_bio}\n```\n\n"
        f"Run `/syncallbio` to update all connected groups."
    )


# ────── Dedicated Group-Only Broadcast Command (/gcast /groupbroadcast) ──────

# ────── Common Message Delivery Helper ──────

async def send_single_broadcast(client: Client, chat_id: int, reply: Message = None, cmd_text: str = "", userbot_client: Client = None):
    """Delivers message payload (media, document, photo, text, etc.) with dual-client, forum general topic, and flood-wait protection."""
    clients_to_try = [client]
    if userbot_client and userbot_client not in clients_to_try:
        clients_to_try.append(userbot_client)

    try:
        from toxic.core.mongo.db import get_all_active_userbots
        ubs = await get_all_active_userbots()
        for ub in ubs:
            if ub and ub not in clients_to_try and getattr(ub, "is_connected", False):
                clients_to_try.append(ub)
    except Exception:
        pass

    last_err = None
    for current_client in clients_to_try:
        if not getattr(current_client, "is_connected", True):
            continue
        try:
            if reply:
                if cmd_text:
                    orig_html = reply.text.html if reply.text else (reply.caption.html if reply.caption else "")
                    combined_text = f"{orig_html}\n\n{cmd_text}".strip()
                    if reply.photo:
                        return await current_client.send_photo(chat_id, reply.photo.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.video:
                        return await current_client.send_video(chat_id, reply.video.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.document:
                        return await current_client.send_document(chat_id, reply.document.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.animation:
                        return await current_client.send_animation(chat_id, reply.animation.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.audio:
                        return await current_client.send_audio(chat_id, reply.audio.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.voice:
                        return await current_client.send_voice(chat_id, reply.voice.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    else:
                        try:
                            return await current_client.send_message(chat_id, combined_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                        except Exception:
                            return await current_client.send_message(chat_id, combined_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, message_thread_id=1)
                else:
                    try:
                        return await reply.copy(chat_id)
                    except Exception:
                        try:
                            return await reply.forward(chat_id)
                        except Exception:
                            # General topic fallback for forum supergroups
                            return await reply.copy(chat_id, message_thread_id=1)
            elif cmd_text:
                try:
                    return await current_client.send_message(chat_id, cmd_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                except Exception:
                    # General topic fallback for forum supergroups
                    return await current_client.send_message(chat_id, cmd_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, message_thread_id=1)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                if reply and not cmd_text:
                    return await reply.copy(chat_id)
                elif reply and cmd_text:
                    orig_html = reply.text.html if reply.text else (reply.caption.html if reply.caption else "")
                    combined_text = f"{orig_html}\n\n{cmd_text}".strip()
                    return await current_client.send_message(chat_id, combined_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                elif cmd_text:
                    return await current_client.send_message(chat_id, cmd_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            except Exception as retry_err:
                last_err = retry_err
        except Exception as e:
            last_err = e
            continue

    if last_err:
        raise last_err
    return None



# ────── 1. User DM Broadcast Command (/broadcast /bcast /sendall /dmcast) ──────

@app.on_message(filters.command(["broadcast", "bcast", "userbroadcast", "sendall", "dmcast", "user_broadcast"]))
async def user_broadcast_cmd(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner / admins can use this command.")
        return

    reply = message.reply_to_message
    cmd_text = message.text.split(None, 1)[1] if len(message.text.split(None, 1)) > 1 else ""

    if not reply and not cmd_text:
        await message.reply_text(
            "📢 <b>User Direct Message (DM) Broadcast Usage</b>:\n\n"
            "1️⃣ <b>Reply to any Message</b> (Photo, Video, Formatted Text, Doc, Audio, etc.):\n"
            "   • <code>/broadcast</code> — Delivers exact copy to all bot users in DM.\n"
            "   • <code>/broadcast &lt;custom text&gt;</code> — Appends your custom note to the caption!\n\n"
            "2️⃣ <b>Direct Text Broadcast</b>:\n"
            "   • <code>/broadcast &lt;b&gt;Announcement&lt;/b&gt;\n\nYour message here...</code>\n\n"
            "<i>(Sends directly to all private chats of registered bot users)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    from toxic.core.mongo.users_db import get_all_registered_users
    raw_users = await get_all_registered_users()
    all_users = [u for u in raw_users if isinstance(u, int) and u > 0]

    if not all_users:
        await message.reply_text("ℹ️ **No registered users found in database to broadcast.**")
        return

    status_msg = await message.reply_text(f"🚀 **Starting User Broadcast to `{len(all_users)}` users...**")
    sent_count = 0
    failed_count = 0
    total_users = len(all_users)
    start_time = asyncio.get_event_loop().time()

    for i, target_uid in enumerate(all_users, 1):
        try:
            await send_single_broadcast(client, target_uid, reply=reply, cmd_text=cmd_text)
            sent_count += 1
            await asyncio.sleep(0.08)
        except (UserIsBlocked, InputUserDeactivated):
            failed_count += 1
        except PeerIdInvalid:
            failed_count += 1
        except Exception as err:
            failed_count += 1
            print(f"[USER BROADCAST] Error delivering to {target_uid}: {err}")

        # Update progress every 25 users or at the end
        if i % 25 == 0 or i == total_users:
            percent = int((i / total_users) * 100)
            try:
                await status_msg.edit(
                    f"📢 **User Broadcast in Progress...**\n\n"
                    f"• Progress: `{i}/{total_users}` ({percent}%)\n"
                    f"• Delivered: `{sent_count}` ✅\n"
                    f"• Failed / Blocked: `{failed_count}` ❌"
                )
            except Exception:
                pass

    elapsed = round(asyncio.get_event_loop().time() - start_time, 1)
    await status_msg.edit(
        f"🎉 **User Broadcast Completed!**\n\n"
        f"• **Total Targeted Users:** `{total_users}`\n"
        f"• **Successfully Delivered:** `{sent_count}` ✅\n"
        f"• **Failed / Blocked:** `{failed_count}` ❌\n"
        f"• **Time Taken:** `{elapsed}s` ⏱️"
    )


# ────── 2. Group & Channel Broadcast Command (/gcast /groupbroadcast) ──────

@app.on_message(filters.command(["gcast", "groupbroadcast", "bcast_groups", "broadcast_groups"]))
async def group_broadcast_cmd(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner / admins can use this command.")
        return

    reply = message.reply_to_message
    cmd_text = message.text.split(None, 1)[1] if len(message.text.split(None, 1)) > 1 else ""

    if not reply and not cmd_text:
        await message.reply_text(
            "📢 <b>Group & Channel Broadcast Usage (/gcast)</b>:\n\n"
            "1️⃣ <b>Reply to a Message</b> (Photo, Video, Formatted Text, Doc, Audio, etc.):\n"
            "   • <code>/gcast</code> — Broadcasts exact replied message to all supergroups, groups & channels.\n"
            "   • <code>/gcast &lt;extra text&gt;</code> — Appends your custom text to the replied message!\n\n"
            "2️⃣ <b>Direct Text Broadcast</b>:\n"
            "   • <code>/gcast &lt;b&gt;Header Text&lt;/b&gt;\n\nBlockquote announcement...</code>\n\n"
            "<i>(Sends to all linked Telegram Channels, Supergroups & Groups)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    # Initialize userbot fallback if available
    userbot_client = None
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    for oid in owner_list:
        try:
            from toxic.modules.main import initialize_userbot
            userbot_client = await initialize_userbot(int(oid))
            if userbot_client:
                break
        except Exception:
            pass

    # Aggregates chats from all collections (where bot presence is verified)
    db_chats = await get_all_broadcast_chats()

    if not db_chats:
        await message.reply_text("ℹ️ **No linked groups or channels found in database to broadcast.**")
        if userbot_client:
            try:
                await userbot_client.stop()
            except Exception:
                pass
        return

    status_msg = await message.reply_text(f"🚀 **Starting Broadcast to `{len(db_chats)}` groups & channels...**")
    sent_count = 0
    failed_count = 0
    total_groups = len(db_chats)
    start_time = asyncio.get_event_loop().time()

    try:
        for i, chat_info in enumerate(db_chats, 1):
            cid = chat_info.get("chat_id")
            if not cid:
                continue
            try:
                await send_single_broadcast(client, cid, reply=reply, cmd_text=cmd_text, userbot_client=userbot_client)
                sent_count += 1
                await asyncio.sleep(0.3)
            except Exception as err:
                failed_count += 1
                print(f"[GCAST] Failed for chat {cid}: {err}")
                if any(k in str(err).lower() for k in ["kicked", "deactivated", "chat not found", "peer_id_invalid", "chat_write_forbidden"]):
                    await remove_joined_chat(cid)

            if i % 10 == 0 or i == total_groups:
                try:
                    await status_msg.edit(
                        f"📢 **Group & Channel Broadcast in Progress...**\n\n"
                        f"• Progress: `{i}/{total_groups}` chats\n"
                        f"• Delivered: `{sent_count}` ✅\n"
                        f"• Failed: `{failed_count}` ❌"
                    )
                except Exception:
                    pass
    finally:
        if userbot_client:
            try:
                await userbot_client.stop()
            except Exception:
                pass

    elapsed = round(asyncio.get_event_loop().time() - start_time, 1)
    await status_msg.edit(
        f"🎉 **Group & Channel Broadcast Completed!**\n\n"
        f"• **Total Chats Targeted:** `{total_groups}`\n"
        f"• **Successfully Delivered:** `{sent_count}` ✅\n"
        f"• **Failed / Unreachable:** `{failed_count}` ❌\n"
        f"• **Time Taken:** `{elapsed}s` ⏱️"
    )


# ────── 3. Broadcast to All (DMs + Groups + Channels) (/broadcast_all /bcastall) ──────

@app.on_message(filters.command(["broadcast_all", "bcastall", "sendtoall", "allcast", "broadcastall"]))
async def all_broadcast_cmd(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner / admins can use this command.")
        return

    reply = message.reply_to_message
    cmd_text = message.text.split(None, 1)[1] if len(message.text.split(None, 1)) > 1 else ""

    if not reply and not cmd_text:
        await message.reply_text(
            "📢 <b>Universal Broadcast (Users + Groups + Channels) Usage</b>:\n\n"
            "• Reply to any message or send text with <code>/broadcast_all</code>.\n"
            "<i>(Delivers to ALL registered bot users in DM and ALL joined groups & channels!)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    # Initialize userbot fallback if available
    userbot_client = None
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    for oid in owner_list:
        try:
            from toxic.modules.main import initialize_userbot
            userbot_client = await initialize_userbot(int(oid))
            if userbot_client:
                break
        except Exception:
            pass

    from toxic.core.mongo.users_db import get_all_registered_users
    raw_users = await get_all_registered_users()
    all_users = [u for u in raw_users if isinstance(u, int) and u > 0]
    
    # Aggregates chats from all collections (where bot presence is verified)
    db_chats = await get_all_broadcast_chats()
    group_ids = [c["chat_id"] for c in db_chats if c.get("chat_id")]

    all_destinations = all_users + group_ids
    total_targets = len(all_destinations)

    if not all_destinations:
        await message.reply_text("ℹ️ **No users, groups, or channels found in database to broadcast.**")
        if userbot_client:
            try:
                await userbot_client.stop()
            except Exception:
                pass
        return

    status_msg = await message.reply_text(f"🚀 **Starting Universal Broadcast to `{len(all_users)}` users and `{len(group_ids)}` groups/channels...**")
    sent_count = 0
    failed_count = 0
    start_time = asyncio.get_event_loop().time()

    try:
        for i, target_id in enumerate(all_destinations, 1):
            try:
                await send_single_broadcast(client, target_id, reply=reply, cmd_text=cmd_text, userbot_client=userbot_client)
                sent_count += 1
                await asyncio.sleep(0.1)
            except Exception:
                failed_count += 1

            if i % 25 == 0 or i == total_targets:
                try:
                    await status_msg.edit(
                        f"📢 **Universal Broadcast in Progress...**\n\n"
                        f"• Progress: `{i}/{total_targets}` chats\n"
                        f"• Delivered: `{sent_count}` ✅\n"
                        f"• Failed: `{failed_count}` ❌"
                    )
                except Exception:
                    pass
    finally:
        if userbot_client:
            try:
                await userbot_client.stop()
            except Exception:
                pass

    elapsed = round(asyncio.get_event_loop().time() - start_time, 1)
    await status_msg.edit(
        f"🎉 **Universal Broadcast Completed!**\n\n"
        f"• **Users Targeted:** `{len(all_users)}`\n"
        f"• **Groups/Channels Targeted:** `{len(group_ids)}`\n"
        f"• **Successfully Delivered:** `{sent_count}` ✅\n"
        f"• **Failed:** `{failed_count}` ❌\n"
        f"• **Time Taken:** `{elapsed}s` ⏱️"
    )

