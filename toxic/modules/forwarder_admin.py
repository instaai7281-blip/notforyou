import re
from pyrogram import filters
from toxic import app
from config import OWNER_ID
from toxic.core.mongo.db import add_forward_mapping, remove_forward_mapping, get_all_forward_mappings

# Helper to check if sender is owner
def is_owner(user_id):
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    return any(str(user_id) == str(o) for o in owner_list)

@app.on_message(filters.command("addforward") & filters.private)
async def add_forward_cmd(client, message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    # Parse arguments: /addforward <user_id> <target_chat_id>
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply_text(
            "📝 **Usage:** `/addforward <user_id> <target_chat_id>`\n\n"
            "**Examples:**\n"
            "• `/addforward 868659158 -100123456789` (Channel/Group)\n"
            "• `/addforward 868659158 -100123456789/42` (Group with Topic ID)"
        )
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await message.reply_text("❌ **Error:** User ID must be a valid integer.")
        return

    target_chat = parts[2].strip()
    from toxic.core.get_func import parse_target_chat
    parsed_chat = parse_target_chat(target_chat)
    if parsed_chat:
        target_chat = parsed_chat
    
    # Simple validation of target chat ID
    if not target_chat.startswith("-100") and not target_chat.startswith("@"):
        await message.reply_text("❌ **Error:** Target Chat ID must start with `-100` or `@`.")
        return

    await add_forward_mapping(target_user_id, target_chat)
    await message.reply_text(
        f"✅ **Success:** Mapped User `{target_user_id}` extractions to destination `{target_chat}`."
    )

@app.on_message(filters.command("removeforward") & filters.private)
async def remove_forward_cmd(client, message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    parts = message.text.split()
    if len(parts) < 2:
        await message.reply_text("📝 **Usage:** `/removeforward <user_id>`")
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await message.reply_text("❌ **Error:** User ID must be a valid integer.")
        return

    await remove_forward_mapping(target_user_id)
    await message.reply_text(f"🗑️ **Success:** Removed forward mapping for User `{target_user_id}`.")

@app.on_message(filters.command("listforward") & filters.private)
async def list_forward_cmd(client, message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    mappings = await get_all_forward_mappings()
    if not mappings:
        await message.reply_text("📋 **No active forward mappings configured.**")
        return

    response = "📋 **Active Auto-Forward Mappings:**\n\n"
    for uid, dest in mappings:
        response += f"• **User:** `{uid}` ➔ **Destination:** `{dest}`\n"

    await message.reply_text(response)


import asyncio
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from toxic.core.mongo.db import get_forward_mapping

active_scan_results = {}

@app.on_message(filters.command("logsync") & filters.private)
async def log_sync_cmd(client, message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    status = await message.reply_text("🔍 **Scanning and analyzing log channel (last 150 messages)...**")
    
    from config import LOG_GROUP
    if not LOG_GROUP:
        await status.edit("❌ **Error:** LOG_GROUP is not configured in config!")
        return

    try:
        log_group_chat = int(LOG_GROUP)
    except ValueError:
        await status.edit("❌ **Error:** LOG_GROUP must be a valid integer chat ID.")
        return

    def parse_user_id_from_log(text):
        if not text:
            return None
        match = re.search(r'(?:User ID:.*?`?(\d+)`?|tg://user\?id=(\d+))', text)
        if match:
            return int(match.group(1) or match.group(2))
        return None

    media_by_user = {}
    
    try:
        async for msg in client.get_chat_history(log_group_chat, limit=150):
            uid = None
            media_id = None
            
            if msg.caption:
                uid = parse_user_id_from_log(msg.caption)
                if uid:
                    media_id = msg.id
            
            if not uid and msg.text:
                uid = parse_user_id_from_log(msg.text)
                if uid and msg.reply_to_message_id:
                    media_id = msg.reply_to_message_id
                    
            if uid and media_id:
                if uid not in media_by_user:
                    media_by_user[uid] = []
                if media_id not in media_by_user[uid]:
                    media_by_user[uid].append(media_id)
    except Exception as e:
        await status.edit(f"❌ **Failed to scan log channel:** `{e}`")
        return

    if not media_by_user:
        await status.edit("📋 **Analysis Complete:** No user media logs found in the last 150 messages.")
        return

    report = "📊 **Log Channel Analysis (Last 150 Messages):**\n\n"
    mapped_count = 0
    unmapped_count = 0
    total_messages = 0
    
    scan_id = str(message.id)
    active_scan_results[scan_id] = {
        "media_by_user": media_by_user,
        "log_group_chat": log_group_chat
    }

    for uid, msg_ids in media_by_user.items():
        mapping = await get_forward_mapping(uid)
        count = len(msg_ids)
        total_messages += count
        if mapping:
            report += f"• 👤 **User `{uid}`:** `{count}` messages ➔ 📍 Destination: `{mapping}`\n"
            mapped_count += count
        else:
            report += f"• 👤 **User `{uid}`:** `{count}` messages ➔ ⚠️ (No mapping set)\n"
            unmapped_count += count

    report += f"\n📈 **Summary:**\n"
    report += f"- Total media found: `{total_messages}`\n"
    report += f"- Mapped to forward: `{mapped_count}`\n"
    report += f"- Unmapped: `{unmapped_count}`\n\n"
    
    if mapped_count > 0:
        report += "👉 Click the button below to forward the mapped files to their destinations!"
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Start Forwarding Mapped Files", callback_data=f"start_sync_{scan_id}")
        ]])
    else:
        report += "ℹ️ No mapped user files found to forward."
        markup = None

    await status.delete()
    await message.reply_text(report, reply_markup=markup)


@app.on_callback_query(filters.regex(r"^start_sync_(\d+)$"))
async def start_sync_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_owner(user_id):
        await callback_query.answer("❌ Access Denied!", show_alert=True)
        return

    scan_id = callback_query.data.split("_")[-1]
    scan_data = active_scan_results.get(scan_id)
    if not scan_data:
        await callback_query.answer("⚠️ Scan session expired or invalid. Please run /logsync again.", show_alert=True)
        return

    media_by_user = scan_data["media_by_user"]
    log_group_chat = scan_data["log_group_chat"]

    await callback_query.message.edit_reply_markup(reply_markup=None)
    status_msg = await callback_query.message.reply("⚡ **Synchronizing logs to destination channels...**")

    forwarded_total = 0
    failed_total = 0
    
    for uid, msg_ids in media_by_user.items():
        mapping = await get_forward_mapping(uid)
        if not mapping:
            continue

        dest_chat_id = mapping
        dest_topic_id = None
        if '/' in str(mapping):
            try:
                parts = str(mapping).split('/', 1)
                dest_chat_id = int(parts[0])
                dest_topic_id = int(parts[1])
            except Exception:
                pass

        await status_msg.edit(f"📤 **Forwarding `{len(msg_ids)}` files for User `{uid}` to `{mapping}`...**")
        
        for msg_id in reversed(msg_ids):
            try:
                media_msg = await client.get_messages(log_group_chat, msg_id)
                if media_msg and not media_msg.empty:
                    await media_msg.copy(
                        chat_id=dest_chat_id,
                        message_thread_id=dest_topic_id
                    )
                    forwarded_total += 1
                    await asyncio.sleep(0.5)
            except Exception as e:
                print(f"Sync failed for msg {msg_id}: {e}")
                failed_total += 1

    await status_msg.edit(
        f"✅ **Synchronization Complete!**\n\n"
        f"• Successfully forwarded: `{forwarded_total}` files\n"
        f"• Failed/skipped: `{failed_total}` files"
    )
    
    active_scan_results.pop(scan_id, None)
