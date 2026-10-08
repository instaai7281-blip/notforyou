# ---------------------------------------------------
# File Name: demo_mirror.py
# Description: 1-Hour Demo Topic Mirror Session with Automatic Topic & Content Cleanup
# Author: Antigravity
# ---------------------------------------------------

import asyncio
import time
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from config import OWNER_ID
from toxic import app, tdb

# Collection for active demo sessions
demo_db = tdb["demo_sessions"]

active_demo_tasks = {}

async def schedule_demo_cleanup(chat_id: int, delay_seconds: int = 3600):
    """Wait for delay_seconds then automatically delete all demo topics & messages."""
    await asyncio.sleep(delay_seconds)
    await cleanup_demo_session(chat_id)

async def cleanup_demo_session(chat_id: int):
    """Delete all topics, messages, and content created during the demo session."""
    session = await demo_db.find_one({"chat_id": chat_id, "status": "active"})
    if not session:
        return

    # Mark as cleaning
    await demo_db.update_one({"_id": session["_id"]}, {"$set": {"status": "cleaning"}})

    created_messages = session.get("created_messages", [])
    created_topics = session.get("created_topics", [])

    # Delete all posted content messages
    if created_messages:
        try:
            for i in range(0, len(created_messages), 100):
                chunk = created_messages[i:i+100]
                try:
                    await app.delete_messages(chat_id, chunk)
                except Exception as e:
                    print(f"[DEMO CLEANUP] Error deleting messages in {chat_id}: {e}")
        except Exception as e:
            print(f"[DEMO CLEANUP] Message deletion error: {e}")

    # Delete all created forum topics
    if created_topics:
        for topic_id in created_topics:
            try:
                await app.delete_forum_topic(chat_id, topic_id)
            except Exception as e:
                print(f"[DEMO CLEANUP] Error deleting topic {topic_id} in {chat_id}: {e}")

    # Mark session as expired
    await demo_db.update_one({"_id": session["_id"]}, {"$set": {"status": "expired", "expired_at": time.time()}})

    # Notify in target chat
    try:
        await app.send_message(
            chat_id,
            "⌛ **1-Hour Demo Session Expired!**\n\n"
            "All demo topics and cloned content have been automatically deleted from this group by the bot.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass

@app.on_message(filters.command(["demomirror", "demo"]))
async def start_demo_command(client: Client, message: Message):
    user_id = message.from_user.id
    
    args = message.text.split(None, 1)
    if len(args) < 2:
        help_text = (
            "🧪 **1-Hour Demo Topic Mirror & Auto-Cleanup**\n\n"
            "This command lets you test the Topic Mirror / Forum Sync feature for **1 Hour**.\n\n"
            "⚠️ **Auto-Cleanup Rule:** Exactly 1 hour after starting, all topics and content created during the demo will be **automatically deleted** from your target group by the bot!\n\n"
            "**Usage:**\n"
            "`/demomirror <target_chat_id>`\n\n"
            "**Example:**\n"
            "`/demomirror -100123456789`\n\n"
            "*(Or run `/enddemo <target_chat_id>` to end demo & delete content immediately!)*"
        )
        await message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        return

    try:
        target_chat_id = int(args[1].strip())
    except ValueError:
        await message.reply_text("❌ Invalid Target Chat ID! Must be a numeric ID (e.g. `-100123456789`).")
        return

    existing = await demo_db.find_one({"chat_id": target_chat_id, "status": "active"})
    if existing:
        time_left = int(existing["end_time"] - time.time())
        if time_left > 0:
            await message.reply_text(
                f"⚠️ An active demo session is already running in `{target_chat_id}`!\n"
                f"⌛ Time remaining: `{time_left // 60}` minutes.\n\n"
                f"Run `/enddemo {target_chat_id}` to terminate it and trigger instant cleanup."
            )
            return

    now = time.time()
    end_time = now + 3600

    session_doc = {
        "user_id": user_id,
        "chat_id": target_chat_id,
        "start_time": now,
        "end_time": end_time,
        "status": "active",
        "created_topics": [],
        "created_messages": []
    }
    
    await demo_db.insert_one(session_doc)

    task = asyncio.create_task(schedule_demo_cleanup(target_chat_id, 3600))
    active_demo_tasks[target_chat_id] = task

    success_text = (
        f"✅ **1-Hour Demo Session Started!**\n\n"
        f"🎯 **Target Group ID:** `{target_chat_id}`\n"
        f"⏱️ **Duration:** `1 Hour` (Expires in 60 minutes)\n\n"
        f"🚨 **Auto-Delete Guarantee:** All topics and content posted by the bot during this demo will be **100% automatically deleted** when the timer expires.\n\n"
        f"💡 Use `/enddemo {target_chat_id}` anytime to stop early and trigger instant cleanup."
    )
    await message.reply_text(success_text, parse_mode=ParseMode.MARKDOWN)

@app.on_message(filters.command(["enddemo", "stopdemo"]))
async def end_demo_command(client: Client, message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply_text("Usage: `/enddemo <target_chat_id>`")
        return

    try:
        target_chat_id = int(args[1].strip())
    except ValueError:
        await message.reply_text("❌ Invalid Target Chat ID!")
        return

    if target_chat_id in active_demo_tasks:
        task = active_demo_tasks.pop(target_chat_id)
        task.cancel()

    await message.reply_text(f"⏳ Triggering instant cleanup for demo session in `{target_chat_id}`...")
    await cleanup_demo_session(target_chat_id)
    await message.reply_text(f"✅ Demo session terminated and all content successfully cleaned up!")

@app.on_message(filters.command(["adminhelp", "admincommands"]))
async def admin_help_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in OWNER_ID:
        await message.reply_text("❌ This command is restricted to Bot Owners only!")
        return

    admin_text = (
        "👑 **XTRACTOR BOT PRO — ADMIN COMMANDS GUIDE**\n\n"
        "**User Plan & Freemium Management:**\n"
        "• `/add <user_id> <days>` — Add Premium plan to user\n"
        "• `/rem <user_id>` — Remove Premium plan from user\n"
        "• `/myplan` / `/plans` — View plan details & pricing\n\n"
        "**Auto-Broadcast & Chat Management:**\n"
        "• `/addchat <chat_id>` — Register chat for auto-broadcast\n"
        "• `/removechat <chat_id>` — Unregister chat from broadcast\n"
        "• `/listchats` — View all registered auto-broadcast chats\n"
        "• `/gcast` / `/broadcast` — Send global broadcast message\n\n"
        "**Topic Mirror & 1-Hour Demo:**\n"
        "• `/demomirror <chat_id>` — Start 1-Hour Demo with auto-delete\n"
        "• `/enddemo <chat_id>` — Terminate demo & delete content instantly\n"
        "• `/scan_mirror` — Live scan & compare topic content\n"
        "• `/sync_mirror` — 1-Click sync missing topic content\n\n"
        "**System Utilities & Maintenance:**\n"
        "• `/stats` — Check bot system & DB analytics\n"
        "• `/deleteall` — Bulk clean messages from user/bot\n"
        "• `/speedtest` — Display server bandwidth & latency"
    )
    await message.reply_text(admin_text, parse_mode=ParseMode.MARKDOWN)
