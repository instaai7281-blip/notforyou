import asyncio
import datetime
from pyrogram import filters, Client
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMemberUpdated
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from toxic import app
from config import OWNER_ID
from toxic.core.mongo.db import (
    get_broadcast_config, 
    update_broadcast_config, 
    add_broadcast_deletion,
    add_joined_chat,
    get_all_joined_chats,
    remove_joined_chat,
    get_pending_deletions,
    remove_broadcast_deletion,
    get_custom_group_bio,
    set_custom_group_bio,
    reset_custom_group_bio,
    DEFAULT_GROUP_BIO
)

# Helper to check if sender is owner
def is_owner(user_id):
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    return any(str(user_id) == str(o) for o in owner_list)

def get_broadcast_menu_keyboard(is_active, interval_mins, delete_after_mins, max_runs, run_count):
    del_after_text = f"{delete_after_mins}m" if delete_after_mins else "Disabled ❌"
    max_runs_text = f"{max_runs}" if max_runs else "No Limit ♾️"
    
    buttons = [
        [
            InlineKeyboardButton(f"⚡ Status: {'ACTIVE ✅' if is_active else 'INACTIVE ❌'}", callback_data="abc_toggle_status")
        ],
        [
            InlineKeyboardButton("📝 Set Message", callback_data="abc_set_msg"),
            InlineKeyboardButton("⏱️ Set Interval", callback_data="abc_set_interval")
        ],
        [
            InlineKeyboardButton(f"🗑️ Auto-Delete: {del_after_text}", callback_data="abc_set_delete_after"),
            InlineKeyboardButton(f"🔢 Max Runs: {max_runs_text}", callback_data="abc_set_max_runs")
        ],
        [
            InlineKeyboardButton("🔄 Reset Run Count", callback_data="abc_reset_runs"),
            InlineKeyboardButton("🚀 Send Now", callback_data="abc_send_now")
        ],
        [
            InlineKeyboardButton("❌ Close Menu", callback_data="abc_close")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_interval_keyboard():
    buttons = [
        [
            InlineKeyboardButton("30 Minutes", callback_data="abc_select_interval_30"),
            InlineKeyboardButton("1 Hour", callback_data="abc_select_interval_60")
        ],
        [
            InlineKeyboardButton("2 Hours", callback_data="abc_select_interval_120"),
            InlineKeyboardButton("4 Hours", callback_data="abc_select_interval_240")
        ],
        [
            InlineKeyboardButton("8 Hours", callback_data="abc_select_interval_480"),
            InlineKeyboardButton("12 Hours", callback_data="abc_select_interval_720")
        ],
        [
            InlineKeyboardButton("24 Hours", callback_data="abc_select_interval_1440")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="abc_back")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_delete_after_keyboard():
    buttons = [
        [
            InlineKeyboardButton("Disabled (Don't Delete)", callback_data="abc_select_delete_after_0")
        ],
        [
            InlineKeyboardButton("2 Minutes", callback_data="abc_select_delete_after_2"),
            InlineKeyboardButton("5 Minutes", callback_data="abc_select_delete_after_5")
        ],
        [
            InlineKeyboardButton("10 Minutes", callback_data="abc_select_delete_after_10"),
            InlineKeyboardButton("15 Minutes", callback_data="abc_select_delete_after_15")
        ],
        [
            InlineKeyboardButton("30 Minutes", callback_data="abc_select_delete_after_30"),
            InlineKeyboardButton("60 Minutes", callback_data="abc_select_delete_after_60")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="abc_back")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_max_runs_keyboard():
    buttons = [
        [
            InlineKeyboardButton("No Limit (Infinite)", callback_data="abc_select_max_runs_0")
        ],
        [
            InlineKeyboardButton("1 Time", callback_data="abc_select_max_runs_1"),
            InlineKeyboardButton("2 Times", callback_data="abc_select_max_runs_2")
        ],
        [
            InlineKeyboardButton("5 Times", callback_data="abc_select_max_runs_5"),
            InlineKeyboardButton("10 Times", callback_data="abc_select_max_runs_10")
        ],
        [
            InlineKeyboardButton("20 Times", callback_data="abc_select_max_runs_20"),
            InlineKeyboardButton("50 Times", callback_data="abc_select_max_runs_50")
        ],
        [
            InlineKeyboardButton("🔙 Back", callback_data="abc_back")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

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
@app.on_message(filters.group | filters.channel, group=10)
async def log_bot_chat_presence(client: Client, message: Message):
    try:
        chat = message.chat
        await add_joined_chat(chat.id, chat.title or chat.username or "Group/Channel")
    except Exception:
        pass

@app.on_message(filters.command(["autobroadcast", "abc"]) & filters.private)
async def auto_broadcast_menu_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    config = await get_broadcast_config()
    msg_text = config.get("message", "None")
    interval = config.get("interval_mins", 60)
    is_active = config.get("is_active", False)
    delete_after_mins = config.get("delete_after_mins", 0)
    max_runs = config.get("max_runs", 0)
    run_count = config.get("run_count", 0)

    # Show database stats
    db_chats = await get_all_joined_chats()
    db_chats_count = len(db_chats)

    preview_text = (
        f"📢 **Automated Message Broadcast Settings**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ **Status:** `{'Active' if is_active else 'Inactive'}`\n"
        f"⏱️ **Interval:** `every {interval} minutes`\n"
        f"🗑️ **Auto-Delete After:** `{f'{delete_after_mins} mins' if delete_after_mins > 0 else 'Disabled'}`\n"
        f"🔢 **Runs Limit:** `{max_runs if max_runs > 0 else 'No Limit'}`\n"
        f"📊 **Current Run Count:** `{run_count}` times sent\n"
        f"👥 **Linked Chats (Database):** `{db_chats_count}` chats\n\n"
        f"📝 **Current Custom Message:**\n"
        f"----------------------------------------\n"
        f"{msg_text}\n"
        f"----------------------------------------\n\n"
        f"Use the settings below to manage the automatic broadcast:"
    )

    await message.reply_text(
        preview_text,
        reply_markup=get_broadcast_menu_keyboard(is_active, interval, delete_after_mins, max_runs, run_count)
    )

@app.on_callback_query(filters.regex(r"^abc_(toggle_status|set_msg|set_interval|send_now|close|back|set_delete_after|set_max_runs|reset_runs|select_interval_\d+|select_delete_after_\d+|select_max_runs_\d+)$"))
async def auto_broadcast_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_owner(user_id):
        await callback_query.answer("❌ Access Denied!", show_alert=True)
        return

    data = callback_query.data
    config = await get_broadcast_config()

    if data == "abc_close":
        await callback_query.message.delete()
        return

    elif data == "abc_toggle_status":
        new_status = not config.get("is_active", False)
        await update_broadcast_config({"is_active": new_status})
        
        # If disabled manually, immediately delete any remaining active broadcast messages
        if not new_status:
            deleted_count = await delete_all_active_broadcast_messages()
            await callback_query.answer(f"Deactivated! Deleted {deleted_count} active broadcast messages.", show_alert=True)
        else:
            await callback_query.answer("Automated broadcast activated!")

    elif data == "abc_reset_runs":
        await update_broadcast_config({"run_count": 0})
        await callback_query.answer("Run count reset to 0!")

    elif data == "abc_set_interval":
        await callback_query.message.edit_text(
            "⏱️ **Select Broadcast Interval:**\n\nChoose the time frequency for the broadcast message:",
            reply_markup=get_interval_keyboard()
        )
        return

    elif data == "abc_set_delete_after":
        await callback_query.message.edit_text(
            "🗑️ **Select Auto-Delete Duration:**\n\nChoose how long the sent broadcast messages should stay in the chat before being automatically deleted:",
            reply_markup=get_delete_after_keyboard()
        )
        return

    elif data == "abc_set_max_runs":
        await callback_query.message.edit_text(
            "🔢 **Select Maximum Run Limit:**\n\nChoose how many times the automated broadcast should send messages before automatically disabling itself:",
            reply_markup=get_max_runs_keyboard()
        )
        return

    elif data.startswith("abc_select_interval_"):
        mins = int(data.split("_")[-1])
        await update_broadcast_config({"interval_mins": mins})
        await callback_query.answer(f"Interval set to {mins} minutes")

    elif data.startswith("abc_select_delete_after_"):
        mins = int(data.split("_")[-1])
        await update_broadcast_config({"delete_after_mins": mins})
        await callback_query.answer(f"Auto-delete set to {f'{mins} minutes' if mins > 0 else 'Disabled'}")

    elif data.startswith("abc_select_max_runs_"):
        runs = int(data.split("_")[-1])
        await update_broadcast_config({"max_runs": runs})
        await callback_query.answer(f"Max runs set to {f'{runs} times' if runs > 0 else 'No Limit'}")

    elif data == "abc_back":
        pass  # Just falls through to refresh page

    elif data == "abc_send_now":
        await callback_query.message.edit_text("🚀 **Broadcasting message to all chats in the background...**")
        sent, failed = await send_auto_broadcast_to_all(manual=True)
        await callback_query.message.reply_text(
            f"✅ **Manual Broadcast Completed!**\n\n"
            f"• Successfully sent: `{sent}` chats\n"
            f"• Failed/skipped: `{failed}` chats"
        )

    elif data == "abc_set_msg":
        await callback_query.message.delete()
        ask = await client.ask(user_id, "📝 **Send your custom broadcast message now (formatting bold/italic/blockquote is fully supported!).**\n\n> Send /cancel to abort.")
        if ask.text == "/cancel":
            await ask.reply("Action cancelled.")
        else:
            message_text = ask.text.markdown if hasattr(ask.text, 'markdown') else ask.text
            await update_broadcast_config({"message": message_text})
            await ask.reply("✅ **Broadcast message saved successfully (with formatting)!**")
        
        await asyncio.sleep(0.5)
        await auto_broadcast_menu_cmd(client, ask)
        return

    # Refresh page
    config = await get_broadcast_config()
    msg_text = config.get("message", "None")
    interval = config.get("interval_mins", 60)
    is_active = config.get("is_active", False)
    delete_after_mins = config.get("delete_after_mins", 0)
    max_runs = config.get("max_runs", 0)
    run_count = config.get("run_count", 0)

    db_chats = await get_all_joined_chats()
    db_chats_count = len(db_chats)

    preview_text = (
        f"📢 **Automated Message Broadcast Settings**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ **Status:** `{'Active' if is_active else 'Inactive'}`\n"
        f"⏱️ **Interval:** `every {interval} minutes`\n"
        f"🗑️ **Auto-Delete After:** `{f'{delete_after_mins} mins' if delete_after_mins > 0 else 'Disabled'}`\n"
        f"🔢 **Runs Limit:** `{max_runs if max_runs > 0 else 'No Limit'}`\n"
        f"📊 **Current Run Count:** `{run_count}` times sent\n"
        f"👥 **Linked Chats (Database):** `{db_chats_count}` chats\n\n"
        f"📝 **Current Custom Message:**\n"
        f"----------------------------------------\n"
        f"{msg_text}\n"
        f"----------------------------------------\n\n"
        f"Use the settings below to manage the automatic broadcast:"
    )

    await callback_query.message.edit_text(
        preview_text,
        reply_markup=get_broadcast_menu_keyboard(is_active, interval, delete_after_mins, max_runs, run_count)
    )

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
            
            # If bot was added as administrator or member
            if status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                await add_joined_chat(chat.id, chat.title or chat.username or "Group/Channel")
                print(f"[AUTO DETECT] Bot added to chat: {chat.title or chat.id} (ID: {chat.id}). Added to broadcast list.")
                
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
                print(f"[AUTO DETECT] Bot left/kicked from chat: {chat.title or chat.id} (ID: {chat.id}). Removed from broadcast list.")
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

@app.on_message(filters.command(["gcast", "groupbroadcast", "bcast_groups", "broadcast_groups"]))
async def group_broadcast_cmd(client: Client, message: Message):
    user_id = message.from_user.id if message.from_user else 0
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    reply = message.reply_to_message
    cmd_text = message.text.split(None, 1)[1] if len(message.text.split(None, 1)) > 1 else ""

    if not reply and not cmd_text:
        await message.reply_text(
            "📢 **Group-Only Broadcast Usage:**\n\n"
            "1️⃣ **Reply to a Message (Photo, Video, Formatted Text, etc.)**:\n"
            "   • `/gcast` — Broadcasts exact replied message with all formatting (`bold`, `> blockquote`, links, etc.).\n"
            "   • `/gcast <extra text>` — Appends your custom text/note to the replied message/caption!\n\n"
            "2️⃣ **Direct Text Broadcast**:\n"
            "   • `/gcast <b>Header Text</b>\n\n> Blockquote text`\n\n"
            "*(Sends exclusively to linked Telegram Supergroups & Groups!)*"
        )
        return

    db_chats = await get_all_joined_chats()
    if not db_chats:
        await message.reply_text("ℹ️ **No linked groups found in database to broadcast.**")
        return

    status_msg = await message.reply_text(f"🚀 **Starting Group Broadcast to `{len(db_chats)}` groups...**")

    sent_count = 0
    failed_count = 0

    for i, chat_info in enumerate(db_chats, 1):
        cid = chat_info.get("chat_id")
        if not cid:
            continue
        try:
            if reply:
                if cmd_text:
                    orig_html = reply.text.html if reply.text else (reply.caption.html if reply.caption else "")
                    combined_text = f"{orig_html}\n\n{cmd_text}".strip()
                    
                    if reply.photo:
                        await client.send_photo(cid, reply.photo.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.video:
                        await client.send_video(cid, reply.video.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.document:
                        await client.send_document(cid, reply.document.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.animation:
                        await client.send_animation(cid, reply.animation.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.audio:
                        await client.send_audio(cid, reply.audio.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    elif reply.voice:
                        await client.send_voice(cid, reply.voice.file_id, caption=combined_text, parse_mode=ParseMode.HTML)
                    else:
                        await client.send_message(cid, combined_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                else:
                    await reply.copy(cid)
            else:
                await client.send_message(cid, cmd_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

            sent_count += 1
            await asyncio.sleep(0.4)
        except Exception as err:
            failed_count += 1
            print(f"[GCAST] Failed for group {cid}: {err}")
            if "kicked" in str(err).lower() or "deactivated" in str(err).lower() or "chat not found" in str(err).lower():
                await remove_joined_chat(cid)

        if i % 10 == 0 or i == len(db_chats):
            try:
                await status_msg.edit(
                    f"📢 **Group Broadcast in Progress...**\n\n"
                    f"• Progress: `{i}/{len(db_chats)}` chats\n"
                    f"• Delivered: `{sent_count}` ✅\n"
                    f"• Failed: `{failed_count}` ❌"
                )
            except Exception:
                pass

    await status_msg.edit(
        f"🎉 **Group Broadcast Completed!**\n\n"
        f"• **Total Groups Targeted:** `{len(db_chats)}`\n"
        f"• **Successfully Delivered:** `{sent_count}` ✅\n"
        f"• **Failed / Unreachable:** `{failed_count}` ❌"
    )
