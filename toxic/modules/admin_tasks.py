# ---------------------------------------------------
# File Name: admin_tasks.py
# Description: Owner & Admin Master Task Control Panel
#              Allows Bot Owners and Admins to view, inspect,
#              stop, resume, and sync all active tasks across all users.
# Author: Antigravity
# ---------------------------------------------------

import time
import asyncio
from typing import Dict, Any, List
from pyrogram import filters, Client, enums
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from toxic import app
from toxic.core.mongo import db
from toxic.core.mongo.db import is_admin_or_owner


def format_duration(seconds: float) -> str:
    """Formats seconds into human-readable duration."""
    sec = int(seconds)
    if sec < 60:
        return f"{sec}s"
    elif sec < 3600:
        return f"{sec // 60}m {sec % 60}s"
    else:
        return f"{sec // 3600}h {(sec % 3600) // 60}m"


async def get_all_active_tasks() -> List[Dict[str, Any]]:
    """Aggregates all running tasks across topic mirror, batch, and range forwarder."""
    tasks = []

    # 1. Topic Mirror & C2T active tasks
    try:
        from toxic.modules.topic_mirror import active_mirrors
        for uid, state in list(active_mirrors.items()):
            if isinstance(state, dict) and state.get("running"):
                tasks.append({
                    "user_id": uid,
                    "type": state.get("task_type", "Forum Topic Mirror"),
                    "src_title": state.get("src_title") or f"Chat {state.get('src_chat_id', 'N/A')}",
                    "tgt_title": state.get("tgt_title") or f"Chat {state.get('tgt_chat_id', 'N/A')}",
                    "src_chat_id": state.get("src_chat_id"),
                    "tgt_chat_id": state.get("tgt_chat_id"),
                    "current_topic": state.get("current_topic", "In Progress"),
                    "progress": state.get("progress_str", ""),
                    "copied_count": state.get("copied_count", 0),
                    "total_count": state.get("total_count", 0),
                    "start_time": state.get("start_time", time.time()),
                    "module": "topic_mirror"
                })
    except Exception as e:
        print(f"[AdminTasks] Error reading active_mirrors: {e}")

    # 2. Batch extraction tasks
    try:
        from toxic.modules.main import batch_active_loops
        for uid, is_running in list(batch_active_loops.items()):
            if is_running:
                # Check if not already covered by mirror
                if not any(t["user_id"] == uid for t in tasks):
                    tasks.append({
                        "user_id": uid,
                        "type": "Batch Message Extraction",
                        "src_title": "Telegram Channel / Chat",
                        "tgt_title": "Target Destination",
                        "current_topic": "Sequential Clone",
                        "progress": "Active",
                        "copied_count": 0,
                        "total_count": 0,
                        "start_time": time.time(),
                        "module": "batch"
                    })
    except Exception as e:
        print(f"[AdminTasks] Error reading batch_active_loops: {e}")

    # 3. Range forwarder tasks
    try:
        from toxic.modules.range_forwarder import active_range_jobs
        for uid, state in list(active_range_jobs.items()):
            if isinstance(state, dict) and state.get("running"):
                if not any(t["user_id"] == uid for t in tasks):
                    tasks.append({
                        "user_id": uid,
                        "type": "Range Forwarder",
                        "src_title": f"Chat {state.get('src_chat_id', 'N/A')}",
                        "tgt_title": f"Chat {state.get('tgt_chat_id', 'N/A')}",
                        "src_chat_id": state.get("src_chat_id"),
                        "tgt_chat_id": state.get("tgt_chat_id"),
                        "current_topic": "Forwarding Range",
                        "progress": f"Post #{state.get('current_id', 0)}",
                        "start_time": time.time(),
                        "module": "range_forwarder"
                    })
    except Exception as e:
        print(f"[AdminTasks] Error reading active_range_jobs: {e}")

    return tasks


async def build_admin_tasks_panel() -> tuple:
    """Builds the text report and control keyboard for all active tasks."""
    try:
        from toxic.core.userbot_manager import get_current_bot_username
        bot_uname = get_current_bot_username()
    except Exception:
        bot_uname = "CurrentBot"

    active_tasks = await get_all_active_tasks()
    count = len(active_tasks)

    header = (
        f"👑 <b>BOT OWNER & ADMIN MASTER TASK CONTROL PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot:</b> <code>@{bot_uname}</code>\n"
        f"⚡ <b>Active Running Tasks:</b> <code>{count}</code>\n"
        f"🕒 <b>Live Snapshot:</b> <code>{time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    if count == 0:
        body = (
            "💤 <b>No Active Tasks Running Right Now!</b>\n\n"
            "• Bot memory and processors are currently completely idle.\n"
            "• Sabhi users ke tasks finish ho chuke hain ya stopped hain.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="adm_tasks_refresh")],
            [InlineKeyboardButton("📋 View Saved Sessions", callback_data="adm_view_all_sessions")]
        ])
        return header + body, kb

    body_lines = []
    buttons = []

    for idx, t in enumerate(active_tasks, 1):
        uid = t["user_id"]
        # Fetch user profile info
        u_label = f"<code>{uid}</code>"
        try:
            u_obj = await app.get_users(uid)
            if u_obj:
                full_name = f"{u_obj.first_name} {u_obj.last_name or ''}".strip()
                uname = f"@{u_obj.username}" if u_obj.username else ""
                u_label = f"<b>{full_name}</b> ({uname} | <code>{uid}</code>)"
        except Exception:
            pass

        duration_str = format_duration(time.time() - t["start_time"])
        prog_display = t.get("progress")
        if not prog_display and t.get("total_count", 0) > 0:
            pct = int((t["copied_count"] / t["total_count"]) * 100)
            prog_display = f"{t['copied_count']}/{t['total_count']} ({pct}%)"
        elif not prog_display:
            prog_display = "Running..."

        item_text = (
            f"<b>{idx}. User:</b> {u_label}\n"
            f"├ 🚀 <b>Type:</b> <code>{t['type']}</code>\n"
            f"├ 📤 <b>Source:</b> <code>{t['src_title']}</code>\n"
            f"├ 📥 <b>Target:</b> <code>{t['tgt_title']}</code>\n"
            f"├ 📂 <b>Topic:</b> <code>{t['current_topic']}</code>\n"
            f"├ 📊 <b>Progress:</b> <code>{prog_display}</code>\n"
            f"└ ⏱️ <b>Running Time:</b> <code>{duration_str}</code>\n"
        )
        body_lines.append(item_text)

        # Action buttons for this specific user
        buttons.append([
            InlineKeyboardButton(f"🛑 Stop User {uid}", callback_data=f"adm_stop_u_{uid}"),
            InlineKeyboardButton(f"⚡ Sync User {uid}", callback_data=f"adm_sync_u_{uid}")
        ])

    body = "\n".join(body_lines) + "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    buttons.append([
        InlineKeyboardButton("🔄 Refresh Dashboard", callback_data="adm_tasks_refresh"),
        InlineKeyboardButton("🛑 STOP ALL TASKS", callback_data="adm_stop_all_confirm")
    ])

    return header + body, InlineKeyboardMarkup(buttons)


@app.on_message(filters.command(["tasks", "admintasks", "alltasks", "running", "runningtasks"]))
async def admin_tasks_command(_, message: Message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    if not is_admin_or_owner(user_id):
        await message.reply_text("⛔ <b>Access Denied:</b> This command is strictly restricted to Bot Owners and Admins.", parse_mode=enums.ParseMode.HTML)
        return

    text, kb = await build_admin_tasks_panel()
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=kb)


@app.on_callback_query(filters.regex(r"^adm_tasks_refresh$"))
async def admin_tasks_refresh_callback(_, query: CallbackQuery):
    user_id = query.from_user.id
    if not is_admin_or_owner(user_id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    text, kb = await build_admin_tasks_panel()
    try:
        await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=kb)
        await query.answer("🔄 Dashboard Refreshed!")
    except Exception:
        await query.answer("Already up to date!")


@app.on_callback_query(filters.regex(r"^adm_stop_u_(\d+)$"))
async def admin_stop_single_user_callback(_, query: CallbackQuery):
    admin_id = query.from_user.id
    if not is_admin_or_owner(admin_id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    target_uid = int(query.matches[0].group(1))

    # Stop mirror
    from toxic.modules.topic_mirror import stop_user_active_mirror
    stop_user_active_mirror(target_uid)

    # Stop batch
    try:
        from toxic.modules.main import batch_active_loops, users_loop
        batch_active_loops[target_uid] = False
        users_loop[target_uid] = False
    except Exception:
        pass

    # Stop range
    try:
        from toxic.modules.range_forwarder import active_range_jobs
        if target_uid in active_range_jobs:
            active_range_jobs[target_uid]["running"] = False
    except Exception:
        pass

    # Notify the user
    try:
        await app.send_message(
            target_uid,
            "🛑 <b>Admin Action:</b> Your active extraction/mirroring task has been safely paused by Bot Admin.\n"
            "💾 Checkpoints have been safely preserved in MongoDB! You can resume anytime using <code>/mirror</code>.",
            parse_mode=enums.ParseMode.HTML
        )
    except Exception:
        pass

    await query.answer(f"🛑 Task for User {target_uid} has been stopped!", show_alert=True)
    await asyncio.sleep(1.0)

    # Refresh panel
    text, kb = await build_admin_tasks_panel()
    try:
        await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^adm_sync_u_(\d+)$"))
async def admin_sync_single_user_callback(_, query: CallbackQuery):
    admin_id = query.from_user.id
    if not is_admin_or_owner(admin_id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    target_uid = int(query.matches[0].group(1))

    # Fetch user's latest mirror session from MongoDB
    sessions = await db.get_user_mirror_sessions(target_uid)
    if not sessions:
        await query.answer(f"❌ No saved mirror session found for user {target_uid}!", show_alert=True)
        return

    latest_sess = sessions[0]
    src_id = latest_sess.get("src_chat_id")
    tgt_id = latest_sess.get("tgt_chat_id")
    is_c2t = (latest_sess.get("session_type") == "c2t")

    await query.answer(f"⚡ Triggering 1-Click Sync for User {target_uid}...", show_alert=True)

    # Trigger sync in background for user
    if is_c2t:
        from toxic.modules.topic_mirror import run_channel_to_topics_mirror
        asyncio.create_task(run_channel_to_topics_mirror(
            user_id=target_uid,
            src_chat_id=src_id,
            tgt_chat_id=tgt_id,
            is_auto_update=True
        ))
    else:
        from toxic.modules.topic_mirror import run_topic_mirror
        asyncio.create_task(run_topic_mirror(
            user_id=target_uid,
            src_chat_id=src_id,
            tgt_chat_id=tgt_id,
            mirror_all_topics=True,
            force_sync=True,
            is_auto_update=True
        ))

    await asyncio.sleep(1.5)
    text, kb = await build_admin_tasks_panel()
    try:
        await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^adm_stop_all_confirm$"))
async def admin_stop_all_confirm_callback(_, query: CallbackQuery):
    admin_id = query.from_user.id
    if not is_admin_or_owner(admin_id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    confirm_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ YES, STOP ALL TASKS", callback_data="adm_stop_all_execute"),
            InlineKeyboardButton("❌ Cancel", callback_data="adm_tasks_refresh")
        ]
    ])
    await query.message.edit_text(
        "⚠️ <b>CONFIRM EMERGENCY STOP ALL TASKS:</b>\n\n"
        "Are you sure you want to abort ALL running mirroring and batch tasks across ALL users on this bot?\n\n"
        "<i>All checkpoints will remain safely saved in database.</i>",
        parse_mode=enums.ParseMode.HTML,
        reply_markup=confirm_kb
    )


@app.on_callback_query(filters.regex(r"^adm_stop_all_execute$"))
async def admin_stop_all_execute_callback(_, query: CallbackQuery):
    admin_id = query.from_user.id
    if not is_admin_or_owner(admin_id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    from toxic.modules.topic_mirror import stop_all_active_mirrors
    stopped_count = stop_all_active_mirrors()

    try:
        from toxic.modules.main import batch_active_loops, users_loop
        for uid in list(batch_active_loops.keys()):
            batch_active_loops[uid] = False
        for uid in list(users_loop.keys()):
            users_loop[uid] = False
    except Exception:
        pass

    try:
        from toxic.modules.range_forwarder import active_range_jobs
        for uid in list(active_range_jobs.keys()):
            active_range_jobs[uid]["running"] = False
    except Exception:
        pass

    await query.answer(f"🛑 All {stopped_count} active tasks have been stopped!", show_alert=True)
    await asyncio.sleep(1.0)

    text, kb = await build_admin_tasks_panel()
    try:
        await query.message.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=kb)
    except Exception:
        pass


@app.on_callback_query(filters.regex(r"^adm_view_all_sessions$"))
async def admin_view_all_sessions_callback(_, query: CallbackQuery):
    admin_id = query.from_user.id
    if not is_admin_or_owner(admin_id):
        await query.answer("⛔ Access Denied!", show_alert=True)
        return

    from toxic.core.mongo.db import mirror_db
    cursor = mirror_db.find().sort("updated_at", -1).limit(20)
    sessions = await cursor.to_list(length=20)

    if not sessions:
        await query.answer("No sessions saved in MongoDB yet.", show_alert=True)
        return

    lines = [
        "📋 <b>DATABASE SAVED SESSIONS (RECENT 20)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    ]
    for s in sessions:
        uid = s.get("user_id", "N/A")
        src_t = s.get("src_title") or s.get("src_chat_id", "N/A")
        tgt_t = s.get("tgt_title") or s.get("tgt_chat_id", "N/A")
        s_type = s.get("session_type", "Mirror")
        last_id = s.get("last_msg_id", 0)
        lines.append(f"• <b>User {uid}</b> [{s_type}]:\n  <code>{src_t}</code> ➔ <code>{tgt_t}</code> (Post #{last_id})\n")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Tasks Dashboard", callback_data="adm_tasks_refresh")]
    ])
    await query.message.edit_text("\n".join(lines), parse_mode=enums.ParseMode.HTML, reply_markup=kb)
