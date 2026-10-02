# ---------------------------------------------------
# File Name: range_forwarder.py
# Description: Range-Based Link-to-Link Batch Forwarder & Copier
#              Supports Public & Private Channels, Supergroups, and Forum Topics
# ---------------------------------------------------

import os
import re
import time
import math
import asyncio
import urllib.parse
from pyrogram import filters, Client, types, enums
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from toxic import app, get_client
from config import OWNER_ID, LOG_GROUP
from toxic.core.func import chk_user, TimeFormatter
from toxic.core.mongo import db
from toxic.core.get_func import get_user_branding_tag, format_caption_to_html

active_range_jobs = {}


def parse_tg_advanced_link(link_str: str):
    """
    Parses any Telegram link (channel post, group post, forum topic link, openmessage URI, or raw chat ID/@username)
    and returns a tuple: (chat_id, topic_id, message_id)
    """
    if not link_str:
        return None, None, None

    link_str = link_str.strip()

    # Case 1: Raw integer Chat ID (e.g. -1001234567890 or 1234567890)
    if re.match(r'^-?\d+$', link_str):
        c_id = int(link_str)
        if c_id > 0 and not str(c_id).startswith("100"):
            c_id = int(f"-100{c_id}")
        return c_id, None, None

    # Case 2: Raw Username (e.g. @mychannel or mychannel)
    if re.match(r'^@?[a-zA-Z0-9_]{4,32}$', link_str):
        uname = link_str.lstrip('@')
        return uname, None, None

    # Case 3: tg://openmessage URI scheme
    if link_str.startswith("tg://openmessage"):
        parsed = urllib.parse.urlparse(link_str)
        params = urllib.parse.parse_qs(parsed.query)
        chat_id_val = params.get("chat_id", [None])[0]
        topic_id_val = params.get("topic_id", [None])[0]
        msg_id_val = params.get("message_id", [None])[0] or params.get("msg_id", [None])[0]

        chat_id = int(chat_id_val) if chat_id_val and chat_id_val.lstrip('-').isdigit() else chat_id_val
        topic_id = int(topic_id_val) if topic_id_val and topic_id_val.isdigit() else None
        msg_id = int(msg_id_val) if msg_id_val and msg_id_val.isdigit() else None
        return chat_id, topic_id, msg_id

    # Case 4: Web Links (t.me, telegram.me, telegram.dog)
    # Examples:
    # https://t.me/c/1234567890/50/100 (private topic message)
    # https://t.me/c/1234567890/100 (private message)
    # https://t.me/c/1234567890/50 (private topic link)
    # https://t.me/channel_name/50/100 (public topic message)
    # https://t.me/channel_name/100 (public message)
    # https://t.me/channel_name/50 (public topic link)
    try:
        clean_url = re.sub(r'^https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', link_str)
        clean_url = clean_url.split('?')[0].rstrip('/')
        parts = [p for p in clean_url.split('/') if p]

        if not parts:
            return None, None, None

        if parts[0] == 'c' or parts[0] == 'b':
            if len(parts) >= 2:
                chat_id = int(f"-100{parts[1]}")
                if len(parts) == 3:
                    # Could be chat_id/msg_id OR chat_id/topic_id
                    # If second num is large, it's msg_id. But usually t.me/c/12345/100 is msg_id=100
                    val = int(parts[2])
                    msg_id = val
                    topic_id = None
                    return chat_id, topic_id, msg_id
                elif len(parts) >= 4:
                    topic_id = int(parts[2])
                    msg_id = int(parts[3])
                    return chat_id, topic_id, msg_id
                else:
                    return chat_id, None, None
        else:
            chat_id = parts[0]
            if chat_id.isdigit():
                chat_id = int(f"-100{chat_id}")

            if len(parts) == 2:
                msg_id = int(parts[1]) if parts[1].isdigit() else None
                return chat_id, None, msg_id
            elif len(parts) >= 3:
                topic_id = int(parts[1]) if parts[1].isdigit() else None
                msg_id = int(parts[2]) if parts[2].isdigit() else None
                return chat_id, topic_id, msg_id
    except Exception as e:
        print(f"[RangeForwarder] Link parsing exception for '{link_str}': {e}")

    return None, None, None


async def get_user_userbot(user_id: int):
    """Retrieves an authorized Userbot client for private/restricted group access."""
    try:
        client, is_temp = await get_client(user_id)
        if client:
            return client, is_temp
    except Exception:
        pass
    return None, False


@app.on_message(filters.command(["rangeforward", "linkbatch", "batchcopy", "rf", "range"]))
async def range_forward_command(client: Client, message: types.Message):
    """
    Main entry point for Range-Based Link-to-Link Batch Forwarder & Copier.
    Allows specifying source start post link, end post link / range count, and target destination link/ID/topic.
    """
    if not message.from_user:
        await message.reply("❌ **Error:** Command must be sent by a user.")
        return

    user_id = message.from_user.id
    if await chk_user(message, user_id) != 0:
        await message.reply("❌ **Access Denied:** Only premium users or the bot owner can use this feature.")
        return

    # Check if a range job is already running for this user
    if active_range_jobs.get(user_id, {}).get("running", False):
        await message.reply(
            "⚠️ **A range forwarder job is already active!**\n"
            "Send `/stoprange` to cancel the current job before starting a new one."
        )
        return

    # Parse arguments if passed inline, e.g. /rangeforward <start_link> <end_link_or_count> <target_link_or_id>
    args = message.text.split(maxsplit=3)[1:]

    src_start_link = None
    src_end_val = None
    tgt_link = None

    if len(args) >= 3:
        src_start_link = args[0]
        src_end_val = args[1]
        tgt_link = args[2]

    # Step 1: Prompt for Source Start Link if not provided
    if not src_start_link:
        try:
            start_prompt = await app.ask(
                user_id,
                "🔗 <b>Send the Source Start Post Link:</b>\n\n"
                "*(e.g., <code>https://t.me/c/1234567890/100</code> or <code>https://t.me/channel_name/100</code> or topic link)*\n\n"
                "Send <code>/cancel</code> to abort.",
                timeout=300
            )
            if not start_prompt or start_prompt.text == "/cancel":
                await app.send_message(user_id, "❌ Process cancelled.")
                return
            src_start_link = start_prompt.text.strip()
        except Exception as e:
            await message.reply(f"❌ Interactive prompt timed out or failed: `{e}`")
            return

    src_chat_id, src_topic_id, src_start_id = parse_tg_advanced_link(src_start_link)
    if not src_chat_id or not src_start_id:
        await app.send_message(
            user_id,
            "❌ <b>Invalid Source Start Link!</b>\n"
            "Please make sure the link includes a valid post message ID (e.g. <code>https://t.me/c/1234567890/100</code>)."
        )
        return

    # Step 2: Prompt for Source End Link or Range Count if not provided
    if not src_end_val:
        try:
            end_prompt = await app.ask(
                user_id,
                f"🎯 <b>Send the Source End Post Link OR Range Count:</b>\n\n"
                f"• <b>End Post Link:</b> <code>https://t.me/c/1234567890/150</code>\n"
                f"• <b>Or Count:</b> Send a number (e.g. <code>50</code> to copy 50 messages from post #{src_start_id})\n\n"
                f"Send <code>/cancel</code> to abort.",
                timeout=300
            )
            if not end_prompt or end_prompt.text == "/cancel":
                await app.send_message(user_id, "❌ Process cancelled.")
                return
            src_end_val = end_prompt.text.strip()
        except Exception as e:
            await app.send_message(user_id, f"❌ Interactive prompt timed out: `{e}`")
            return

    src_end_id = None
    if src_end_val.isdigit():
        count = int(src_end_val)
        src_end_id = src_start_id + count - 1
    else:
        _, _, parsed_end_id = parse_tg_advanced_link(src_end_val)
        if parsed_end_id:
            src_end_id = parsed_end_id
        else:
            await app.send_message(user_id, "❌ <b>Invalid End Post Link or Count format!</b>")
            return

    if src_end_id < src_start_id:
        # Swap if user provided end link smaller than start link
        src_start_id, src_end_id = src_end_id, src_start_id

    total_count = (src_end_id - src_start_id) + 1

    # Step 3: Prompt for Target Destination if not provided
    if not tgt_link:
        try:
            tgt_prompt = await app.ask(
                user_id,
                "📥 <b>Send Target Destination (Link / ID / Topic Link):</b>\n\n"
                "• <b>Target Channel / Group Link:</b> <code>https://t.me/c/9876543210</code> or <code>@my_target_channel</code>\n"
                "• <b>Target Forum Topic Link:</b> <code>https://t.me/c/9876543210/50</code>\n"
                "• <b>Or Raw Chat ID:</b> <code>-1009876543210</code>\n\n"
                "Send <code>/cancel</code> to abort.",
                timeout=300
            )
            if not tgt_prompt or tgt_prompt.text == "/cancel":
                await app.send_message(user_id, "❌ Process cancelled.")
                return
            tgt_link = tgt_prompt.text.strip()
        except Exception as e:
            await app.send_message(user_id, f"❌ Interactive prompt timed out: `{e}`")
            return

    tgt_chat_id, tgt_topic_id, _ = parse_tg_advanced_link(tgt_link)
    if not tgt_chat_id:
        await app.send_message(user_id, "❌ <b>Invalid Target Destination format!</b>")
        return

    # High-Speed Execution Start
    stop_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Stop Range Forwarder", callback_data="stop_range_job")]])
    
    status_msg = await app.send_message(
        user_id,
        f"⚡ <b>Initializing Link-to-Link Batch Forwarder...</b>\n\n"
        f"• <b>Source Chat:</b> <code>{src_chat_id}</code>\n"
        f"• <b>Range:</b> Post #{src_start_id} ➔ #{src_end_id} (Total: <code>{total_count}</code>)\n"
        f"• <b>Target:</b> <code>{tgt_chat_id}</code>" + (f" (Topic: <code>{tgt_topic_id}</code>)" if tgt_topic_id else ""),
        parse_mode=ParseMode.HTML
    )

    userbot, is_temp = await get_user_userbot(user_id)
    fetch_client = userbot if userbot else app

    active_range_jobs[user_id] = {
        "running": True,
        "copied": 0,
        "failed": 0,
        "skipped": 0,
        "total": total_count,
        "status_msg": status_msg
    }

    start_time = time.time()
    last_edit_time = start_time
    copied_count = 0
    failed_count = 0
    skipped_count = 0

    try:
        for current_id in range(src_start_id, src_end_id + 1):
            if not active_range_jobs.get(user_id, {}).get("running", True):
                await app.send_message(user_id, "🛑 <b>Range Forwarder job stopped by user!</b>")
                break

            # Fetch source message
            msg = None
            try:
                msg = await fetch_client.get_messages(src_chat_id, current_id)
            except Exception as get_err:
                print(f"[RangeForwarder] Error fetching msg #{current_id}: {get_err}")

            if not msg or getattr(msg, "empty", False) or getattr(msg, "service", False):
                skipped_count += 1
                continue

            # Deliver message to Target (handling forum topic destination cleanly)
            copied_success = False
            for retry in range(3):
                try:
                    kwargs = {}
                    if tgt_topic_id:
                        kwargs["reply_to_message_id"] = tgt_topic_id

                    # Clean direct copy
                    await fetch_client.copy_message(
                        chat_id=tgt_chat_id,
                        from_chat_id=src_chat_id,
                        message_id=msg.id,
                        **kwargs
                    )
                    copied_success = True
                    break
                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 1)
                except Exception as copy_err:
                    print(f"[RangeForwarder] Copy error for msg #{msg.id} (attempt {retry+1}): {copy_err}")
                    # Fallback to app client if fetch_client failed
                    if fetch_client != app:
                        try:
                            await app.copy_message(
                                chat_id=tgt_chat_id,
                                from_chat_id=src_chat_id,
                                message_id=msg.id,
                                **kwargs
                            )
                            copied_success = True
                            break
                        except Exception as app_err:
                            print(f"[RangeForwarder] App fallback copy error: {app_err}")
                    await asyncio.sleep(1)

            if copied_success:
                copied_count += 1
            else:
                failed_count += 1

            # Update progress UI card every 3.5 seconds
            now = time.time()
            if now - last_edit_time > 3.5:
                last_edit_time = now
                processed = (current_id - src_start_id) + 1
                pct = int((processed / total_count) * 100)
                filled = int(pct / 10)
                bar = "█" * filled + "░" * (10 - filled)
                elapsed = now - start_time
                speed = copied_count / elapsed if elapsed > 0 else 0
                eta = int((total_count - processed) / speed) if speed > 0 else 0

                progress_text = (
                    f"⚡ <b>Link-to-Link Batch Forwarder Progress</b>\n\n"
                    f"• <b>Progress:</b> [{bar}] {pct}%\n"
                    f"• <b>Transferred:</b> <code>{copied_count}</code> / <code>{total_count}</code>\n"
                    f"• <b>Failed:</b> <code>{failed_count}</code> | <b>Skipped:</b> <code>{skipped_count}</code>\n"
                    f"• <b>Speed:</b> <code>{speed:.1f}</code> msgs/sec | <b>ETA:</b> <code>{TimeFormatter(eta*1000)}</code>"
                )
                try:
                    await status_msg.edit(progress_text, parse_mode=ParseMode.HTML)
                except Exception:
                    pass

        # Send Final Completion Message strictly to Target Destination Topic / Chat
        completion_text = (
            "<blockquote><b>✅ 𝗖ꪮ𝗺𝗽𝗹𝗲𝘁𝗲 𝗛ꪮ 𝗚𝗮𝘆𝗮 𝗕ꪮ$$ 😎</b></blockquote>\n\n"
            f"• <b>Total Content in Topic:</b> 📁 <code>{copied_count}</code> files"
        )

        try:
            if tgt_topic_id:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=completion_text,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=tgt_topic_id
                )
            else:
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=completion_text,
                    parse_mode=ParseMode.HTML
                )
        except Exception as send_tgt_err:
            print(f"[RangeForwarder] Failed sending completion message to target: {send_tgt_err}")

        # Final Status Update in User DM
        final_summary = (
            f"✅ <b>Link-to-Link Batch Forwarder Finished!</b>\n\n"
            f"• <b>Total Transferred:</b> 📁 <code>{copied_count}</code> files\n"
            f"• <b>Failed:</b> <code>{failed_count}</code> | <b>Skipped:</b> <code>{skipped_count}</code>\n"
            f"• <b>Target:</b> <code>{tgt_chat_id}</code>" + (f" (Topic: <code>{tgt_topic_id}</code>)" if tgt_topic_id else "")
        )
        try:
            await status_msg.edit(final_summary, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    except Exception as exec_err:
        print(f"[RangeForwarder] Critical execution error: {exec_err}")
        try:
            await status_msg.edit(f"❌ <b>Batch Forwarder Error:</b> `{exec_err}`")
        except Exception:
            pass
    finally:
        active_range_jobs.pop(user_id, None)


@app.on_message(filters.command(["stoprange", "cancelrange"]))
async def stop_range_command(client: Client, message: types.Message):
    user_id = message.from_user.id
    if user_id in active_range_jobs:
        active_range_jobs[user_id]["running"] = False
        await message.reply("🛑 <b>Stopping range forwarder job...</b>", parse_mode=ParseMode.HTML)
    else:
        await message.reply("❌ <b>No active range forwarder job found.</b>", parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex(r"^stop_range_job$"))
async def stop_range_callback(client: Client, query):
    user_id = query.from_user.id
    if user_id in active_range_jobs:
        active_range_jobs[user_id]["running"] = False
        await query.answer("🛑 Stopping range forwarder...", show_alert=True)
    else:
        await query.answer("❌ No active range forwarder job found.", show_alert=True)

