# ---------------------------------------------------
# File Name: gcast.py
# Description: Forward/Announce broadcast module for Pyrogram bot.
# ---------------------------------------------------

import asyncio
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked, PeerIdInvalid
from toxic import app
from toxic.core.mongo.db import admin_filter
from toxic.core.mongo.users_db import get_all_registered_users

# ────── Forward/Announce Broadcast Command (/acast /announce) ──────

@app.on_message(filters.command(["acast", "announce", "fwdcast"]) & admin_filter)
async def announced_broadcast_cmd(client: Client, message: Message):
    """Forwards the replied message directly to all registered bot users."""
    if not message.reply_to_message:
        await message.reply_text(
            "📢 <b>Announced / Forward Broadcast Usage</b>:\n\n"
            "• Reply to any message/post with <code>/acast</code> to forward it directly to all bot users in PM.",
            parse_mode=ParseMode.HTML
        )
        return

    to_send_id = message.reply_to_message.id
    source_chat_id = message.chat.id

    raw_users = await get_all_registered_users()
    users = [u for u in raw_users if isinstance(u, int) and u > 0]

    if not users:
        await message.reply_text("ℹ️ **No registered users found in database to forward.**")
        return

    status_msg = await message.reply_text(f"🚀 **Starting Forward Broadcast to `{len(users)}` users...**")
    done_users = 0
    failed_users = 0
    total_users = len(users)
    start_time = asyncio.get_event_loop().time()

    for i, target_user in enumerate(users, 1):
        try:
            await client.forward_messages(
                chat_id=int(target_user),
                from_chat_id=source_chat_id,
                message_ids=to_send_id
            )
            done_users += 1
            await asyncio.sleep(0.1)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            try:
                await client.forward_messages(
                    chat_id=int(target_user),
                    from_chat_id=source_chat_id,
                    message_ids=to_send_id
                )
                done_users += 1
            except Exception:
                failed_users += 1
        except Exception:
            failed_users += 1

        if i % 25 == 0 or i == total_users:
            percent = int((i / total_users) * 100)
            try:
                await status_msg.edit(
                    f"📢 **Forward Broadcast in Progress...**\n\n"
                    f"• Progress: `{i}/{total_users}` ({percent}%)\n"
                    f"• Delivered: `{done_users}` ✅\n"
                    f"• Failed: `{failed_users}` ❌"
                )
            except Exception:
                pass

    elapsed = round(asyncio.get_event_loop().time() - start_time, 1)
    await status_msg.edit(
        f"🎉 **Forward Broadcast Completed!**\n\n"
        f"• **Targeted Users:** `{total_users}`\n"
        f"• **Successfully Delivered:** `{done_users}` ✅\n"
        f"• **Failed:** `{failed_users}` ❌\n"
        f"• **Time Taken:** `{elapsed}s` ⏱️"
    )
