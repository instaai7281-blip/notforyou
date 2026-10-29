# ---------------------------------------------------
# File Name: stats.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------


import os
import time
import sys
import motor
from toxic import app
from pyrogram import filters
from config import OWNER_ID
from toxic.core.mongo.db import admin_filter
from toxic.core.mongo.users_db import get_users, add_user, get_user, get_all_registered_users
from toxic.core.mongo.plans_db import premium_users
from pyrogram.types import Message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ChatType


@app.on_message(filters.command("id"))
async def id_command(client, message: Message):
    reply = message.reply_to_message

    user = reply.from_user if reply else message.from_user
    
    if user:
        user_id = user.id
        first_name = user.first_name or ""
        last_name = user.last_name or ""
        full_name = f"{first_name} {last_name}".strip() or "N/A"
        username = f"@{user.username}" if user.username else "N/A"
    else:
        user_id = "N/A"
        full_name = "N/A"
        username = "N/A"
        
    chat_id = message.chat.id
    chat_title = message.chat.title or message.chat.first_name or "Private Chat"
    chat_type = str(message.chat.type).split('.')[-1].replace('_', ' ').title()
    msg_id = message.id
    reply_id = reply.message_id if reply else "N/A"

    text = (
        f"👤 **User Details:**\n"
        f"• **Name:** {full_name}\n"
        f"• **Username:** {username}\n"
        f"• **User ID:** `{user_id}`\n\n"
        f"💬 **Chat Details:**\n"
        f"• **Title:** {chat_title}\n"
        f"• **Type:** {chat_type}\n"
        f"• **Chat ID:** `{chat_id}`\n\n"
        f"📎 **Message ID:** `{msg_id}`\n"
        f"🔁 **Reply to Msg ID:** `{reply_id}`"
    )

    await message.reply_text(text, quote=True)


start_time = time.time()

@app.on_message(group=10)
async def chat_watcher_func(_, message):
    try:
        if message.from_user:
            us_in_db = await get_user(message.from_user.id)
            if not us_in_db:
                await add_user(message.from_user.id)
    except:
        pass



def time_formatter():
    minutes, seconds = divmod(int(time.time() - start_time), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    weeks, days = divmod(days, 7)
    tmp = (
        ((str(weeks) + "w:") if weeks else "")
        + ((str(days) + "d:") if days else "")
        + ((str(hours) + "h:") if hours else "")
        + ((str(minutes) + "m:") if minutes else "")
        + ((str(seconds) + "s") if seconds else "")
    )
    if tmp != "":
        if tmp.endswith(":"):
            return tmp[:-1]
        else:
            return tmp
    else:
        return "0 s"


@app.on_message(filters.command("stats") & admin_filter)
async def stats(client, message):
    start = time.time()
    users = len(await get_all_registered_users())
    premium = await premium_users()
    ping = round((time.time() - start) * 1000)
    await message.reply_text(f"""
**Stats of** {(await client.get_me()).mention} :

🏓 **Ping Pong**: {ping}ms

📊 **Total Users** : `{users}`
📈 **Premium Users** : `{len(premium)}`
⚙️ **Bot Uptime** : `{time_formatter()}`
    
🎨 **Python Version**: `{sys.version.split()[0]}`
📑 **Mongo Version**: `{motor.version}`
""")

from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery
)

import datetime
import pytz
from toxic.core.mongo.plans_db import check_premium, add_premium, remove_premium
from pyrogram.enums import ParseMode

# PAGINATION CONFIG
PREMIUM_USERS_PER_PAGE = 8

# /getusers command — Admin/OWNER only, private chat
@app.on_message(filters.command("getusers") & admin_filter & filters.private)
async def getusers_paginated(client, message: Message):
    await show_premium_users_page(client, message.chat.id, page=0)


# Helper: Show paginated list of premium users
async def show_premium_users_page(client, chat_id, page=0, message_to_edit=None):
    p_users = await premium_users()
    if not p_users:
        text = "👑 **Active Premium Users**:\n\nNo active premium users found."
        if message_to_edit:
            await message_to_edit.edit_text(text)
        else:
            await client.send_message(chat_id, text)
        return

    total_users = len(p_users)
    start_idx = page * PREMIUM_USERS_PER_PAGE
    end_idx = start_idx + PREMIUM_USERS_PER_PAGE
    chunk = p_users[start_idx:end_idx]

    text = f"👑 **Active Premium Users** (Page {page + 1} of {((total_users - 1) // PREMIUM_USERS_PER_PAGE) + 1}):\n"
    text += f"Total Premium Members: `{total_users}`\n\n"

    buttons_row = []
    # Build list text and buttons
    for idx, uid in enumerate(chunk):
        num = start_idx + idx + 1
        try:
            user = await client.get_users(uid)
            name = f"{user.first_name or ''}".strip() or str(uid)
            name = name.replace('[', '').replace(']', '')
            mention = f"[{name}](tg://user?id={uid})"
        except:
            mention = f"User (`{uid}`)"
        
        # Expiry details
        data = await check_premium(uid)
        expiry_str = "N/A"
        if data and data.get("expire_date"):
            expiry = data.get("expire_date")
            expiry_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata"))
            expiry_str = expiry_ist.strftime("%d-%m-%Y %I:%M %p")
            
        text += f"{num}. 👤 {mention}\n   ├ Expiry: `{expiry_str}`\n   └ ID: `{uid}`\n\n"
        # Add a management button for this specific user
        buttons_row.append(InlineKeyboardButton(f"{num}", callback_data=f"manage_p_{uid}_{page}"))

    # Layout management buttons (max 4 per row)
    keyboard = []
    chunked_buttons = [buttons_row[i:i + 4] for i in range(0, len(buttons_row), 4)]
    keyboard.extend(chunked_buttons)

    # Page navigation buttons
    nav_buttons = []
    if start_idx > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"p_page_{page - 1}"))
    if end_idx < total_users:
        nav_buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"p_page_{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔄 Refresh List", callback_data=f"p_page_{page}")])

    markup = InlineKeyboardMarkup(keyboard)

    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await client.send_message(chat_id, text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


# Callback Query Handler for Premium Users Page
@app.on_callback_query(filters.regex(r"^p_page_(\d+)$") & admin_filter)
async def handle_p_page_callback(client, query: CallbackQuery):
    page = int(query.matches[0].group(1))
    await show_premium_users_page(client, query.message.chat.id, page, query.message)
    await query.answer()


# Callback Query Handler to Manage a Specific Premium User
@app.on_callback_query(filters.regex(r"^manage_p_(\d+)_(\d+)$") & admin_filter)
async def manage_p_user_callback(client, query: CallbackQuery):
    user_id = int(query.matches[0].group(1))
    page = int(query.matches[0].group(2))
    
    try:
        user = await client.get_users(user_id)
        mention = user.mention
    except:
        mention = f"User (`{user_id}`)"

    data = await check_premium(user_id)
    if not data or not data.get("expire_date"):
        await query.answer("❌ User is no longer premium or not found.", show_alert=True)
        await show_premium_users_page(client, query.message.chat.id, page, query.message)
        return

    expiry = data.get("expire_date")
    expiry_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata"))
    expiry_str_in_ist = expiry_ist.strftime("%d-%m-%Y %I:%M:%S %p")            
    
    current_time = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
    time_left = expiry_ist - current_time
    
    if time_left.total_seconds() > 0:
        days = time_left.days
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_left_str = f"{days}d, {hours}h, {minutes}m"
    else:
        time_left_str = "Expired"

    text = (
        f"👑 **Manage Premium User**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **User:** {mention}\n"
        f"🆔 **ID:** `{user_id}`\n"
        f"⏰ **Time Left:** `{time_left_str}`\n"
        f"⌛ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [
            InlineKeyboardButton("➕ Extend 1 Day", callback_data=f"extend_p_{user_id}_1_{page}"),
            InlineKeyboardButton("➕ Extend 7 Days", callback_data=f"extend_p_{user_id}_7_{page}")
        ],
        [
            InlineKeyboardButton("➕ Extend 30 Days", callback_data=f"extend_p_{user_id}_30_{page}")
        ],
        [
            InlineKeyboardButton("🗑️ Revoke Premium", callback_data=f"revoke_p_{user_id}_{page}")
        ],
        [
            InlineKeyboardButton("◀️ Back to List", callback_data=f"p_page_{page}")
        ]
    ]

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)
    await query.answer()


# Callback Query Handler to Extend Premium
@app.on_callback_query(filters.regex(r"^extend_p_(\d+)_(\d+)_(\d+)$") & admin_filter)
async def extend_p_user_callback(client, query: CallbackQuery):
    user_id = int(query.matches[0].group(1))
    days_to_add = int(query.matches[0].group(2))
    page = int(query.matches[0].group(3))

    data = await check_premium(user_id)
    current_expiry = None
    if data and data.get("expire_date"):
        current_expiry = data.get("expire_date")

    now = datetime.datetime.now()
    if current_expiry and current_expiry > now:
        new_expiry = current_expiry + datetime.timedelta(days=days_to_add)
    else:
        new_expiry = now + datetime.timedelta(days=days_to_add)

    await add_premium(user_id, new_expiry)
    await query.answer(f"✅ Extended by {days_to_add} days!", show_alert=True)
    
    # Re-trigger management menu to show updated expiry
    class DummyQuery:
        def __init__(self, q):
            self.message = q.message
            self.from_user = q.from_user
            self.data = q.data
            self.matches = q.matches
        async def answer(self, *args, **kwargs):
            pass

    class Match:
        def __init__(self, u, p):
            self.u = str(u)
            self.p = str(p)
        def group(self, idx):
            return self.u if idx == 1 else self.p

    dummy = DummyQuery(query)
    dummy.matches = [Match(user_id, page)]
    await manage_p_user_callback(client, dummy)


# Callback Query Handler to Revoke Premium
@app.on_callback_query(filters.regex(r"^revoke_p_(\d+)_(\d+)$") & admin_filter)
async def revoke_p_user_callback(client, query: CallbackQuery):
    user_id = int(query.matches[0].group(1))
    page = int(query.matches[0].group(2))

    await remove_premium(user_id)
    
    # Terminate active token session if exists
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        from config import MONGO_DB
        tclient = AsyncIOMotorClient(MONGO_DB)
        tdb = tclient["telegram_bot"]
        await tdb["tokens"].delete_one({"user_id": user_id})
    except Exception:
        pass

    try:
        await client.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ **NOTICE: PREMIUM EXPIRED/TERMINATED** ⚠️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Hello, your premium subscription or token session for \n"
                f"🖤 **Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝** has been terminated or expired.\n\n"
                f"💬 If you think this is a mistake or wish to renew, please contact @CrazyxDeveloper_Bot.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        )
    except Exception:
        pass

    await query.answer("🗑️ Premium revoked!", show_alert=True)
    await show_premium_users_page(client, query.message.chat.id, page, query.message)


# ─── Total Community & Channel Member Counter Command (/community) ───
@app.on_message(filters.command(["community", "totalmembers", "channelsmembers", "allmembers", "membercount"]) & admin_filter)
async def community_count_command(client, message: Message):
    """
    Counts total combined members across all channels and groups where the bot is added,
    calculating the total size of the network/community.
    Admin/Owner only.
    """
    status_msg = await message.reply_text("🔍 **Scanning all channels and groups to count total community members...**\n<i>Please wait a few seconds...</i>", parse_mode=ParseMode.HTML)
    
    from toxic.core.mongo.db import get_all_broadcast_chats, joined_chats_db
    from toxic.core.mongo.users_db import get_all_registered_users
    import asyncio

    # Discover chats from DB and active bot dialogs
    seen_chat_ids = set()
    chat_list = []

    # 1. From database records
    try:
        all_db_chats = await get_all_broadcast_chats()
        for c in all_db_chats:
            cid = c.get("chat_id")
            if cid and cid < 0 and cid not in seen_chat_ids:
                seen_chat_ids.add(cid)
                chat_list.append((cid, c.get("title", f"Chat {cid}"), c.get("chat_type")))
    except Exception as e:
        print(f"[CommunityCount] Error loading from DB: {e}")

    # 2. From active bot dialogs if available
    try:
        async for dialog in client.get_dialogs():
            chat = dialog.chat
            if chat and chat.id < 0 and chat.id not in seen_chat_ids:
                seen_chat_ids.add(chat.id)
                c_type = "channel" if chat.type == ChatType.CHANNEL else "supergroup"
                chat_list.append((chat.id, chat.title or str(chat.id), c_type))
            await asyncio.sleep(0.02)
    except Exception:
        pass

    total_channels = 0
    total_groups = 0
    total_channel_members = 0
    total_group_members = 0
    breakdown_lines = []

    for cid, title, c_type in chat_list:
        try:
            chat_obj = await client.get_chat(cid)
            members = getattr(chat_obj, "members_count", 0) or 0
            is_ch = chat_obj.type == ChatType.CHANNEL or c_type == "channel"
            if is_ch:
                total_channels += 1
                total_channel_members += members
            else:
                total_groups += 1
                total_group_members += members

            breakdown_lines.append({
                "id": cid,
                "title": chat_obj.title or title,
                "type": "Channel 📢" if is_ch else "Group 👥",
                "members": members
            })
        except Exception:
            # Bot might have been removed or lost access
            continue
        await asyncio.sleep(0.05)

    # Registered Bot DM Users
    total_bot_users = 0
    try:
        reg_users = await get_all_registered_users()
        total_bot_users = len(reg_users)
    except Exception:
        pass

    grand_total = total_channel_members + total_group_members

    # Sort top 10 channels/groups by member count
    breakdown_lines.sort(key=lambda x: x["members"], reverse=True)
    top_chats_text = ""
    for idx, c in enumerate(breakdown_lines[:15], 1):
        top_chats_text += f"{idx}. <b>{c['title']}</b> ({c['type']}): <code>{c['members']:,}</code> members\n"

    result_text = (
        f"<blockquote>🌐 <b>COMMUNITY & NETWORK MEMBER STATS</b> 🌐</blockquote>\n\n"
        f"👑 <b>Total Community Reach:</b> <code>{grand_total:,}</code> members\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>Channels:</b> <code>{total_channels}</code> channels\n"
        f"👥 <b>Channel Members:</b> <code>{total_channel_members:,}</code>\n\n"
        f"🏢 <b>Groups / Supergroups:</b> <code>{total_groups}</code> groups\n"
        f"👥 <b>Group Members:</b> <code>{total_group_members:,}</code>\n\n"
        f"🤖 <b>Direct Bot Users (DMs):</b> <code>{total_bot_users:,}</code> users\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b><u>Top Channels & Groups Breakdown:</u></b>\n"
        f"{top_chats_text or '<i>No channels or groups accessible.</i>'}\n"
        f"<i>Note: Data is refreshed live via Telegram API.</i>"
    )

    try:
        await status_msg.edit_text(result_text, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(result_text, parse_mode=ParseMode.HTML)

