# ---------------------------------------------------
# File Name: main.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# More readable 
# ---------------------------------------------------

import time
import random
import string
import asyncio
from pyrogram import filters, Client
from toxic import app, task_semaphore
from config import API_ID, API_HASH, FREEMIUM_LIMIT, PREMIUM_LIMIT, OWNER_ID
from toxic.core.get_func import get_msg, save_user_data, load_user_data, get_target_chat_id
from toxic.core.func import *
from toxic.core.mongo import db
from pyrogram.errors import FloodWait
from datetime import datetime, timedelta
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import subprocess
from pyrogram.enums import ParseMode
from pyrogram.types import Message
from toxic.modules.shrink import is_user_verified
async def generate_random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))




users_loop = {}
batch_active_loops = {}
interval_set = {}
batch_mode = {}

async def process_and_upload_link(userbot, user_id, msg_id, link, retry_count, message):
    try:
        await get_msg(userbot, user_id, msg_id, link, retry_count, message)
    finally:
        pass

# Function to check if the user can proceed
async def check_interval(user_id, freecheck):
    if freecheck != 1 or await is_user_verified(user_id):  # Premium or owner users can always proceed
        return True, None

    now = datetime.now()

    # Check if the user is on cooldown
    if user_id in interval_set:
        cooldown_end = interval_set[user_id]
        if now < cooldown_end:
            remaining_time = (cooldown_end - now).seconds
            return False, f"Please wait {remaining_time} seconds(s) before sending another link. Alternatively, purchase premium for instant access.\n\n> Hey 👋 You can use /token to use the bot free for 3 hours without any time limit."
        else:
            del interval_set[user_id]  # Cooldown expired, remove user from interval set

    return True, None

async def set_interval(user_id, interval_minutes=45):
    now = datetime.now()
    # Set the cooldown interval for the user (converted minutes to seconds for timedelta)
    interval_set[user_id] = now + timedelta(minutes=interval_minutes)
    

import re

@app.on_message(filters.private & (filters.forwarded | ~filters.text))
async def handle_forwarded_or_media(client, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    from toxic.core.func import chk_user
    if await chk_user(message, user_id) == 1:
        return

    if message.text and re.search(r'https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)', message.text):
        return

    from toxic.core.get_func import get_target_chat_id, extract_message_topic_id
    target_chat_id = get_target_chat_id(user_id)
    if target_chat_id == user_id:
        await message.reply_text("📢 **Please set a destination Chat ID first in /settings or via button!**")
        return

    topic_id = None
    if '/' in str(target_chat_id):
        try:
            target_chat_id, topic_id = map(int, str(target_chat_id).split('/', 1))
        except ValueError:
            pass
    else:
        topic_id = extract_message_topic_id(message)

    msg = await message.reply_text("🔄 **Forwarding/Copying message...**")
    try:
        await message.copy(
            chat_id=target_chat_id,
            message_thread_id=topic_id
        )
        await msg.edit("✅ **Message successfully forwarded/copied to destination!**")
    except Exception as e:
        await msg.edit(f"❌ **Failed to forward:** `{e}`")


@app.on_message(
    filters.regex(r'https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/[^\s]+|tg://openmessage\?(?:user_id|chat_id)=-?\d+&message_id=\d+')
    & filters.private
)
async def single_link(_, message):
    user_id = message.chat.id

    # Check subscription and batch mode
    if await subscribe(_, message) == 1 or user_id in batch_mode:
        return

    # Check if user is already in a loop
    if batch_active_loops.get(user_id, False):
        await message.reply(
            "You already have an ongoing process. Please wait for it to finish or cancel it with /cancel."
        )
        return

    # Check freemium limits
    if await chk_user(message, user_id) == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID:
        from toxic.core.func import get_upgrade_premium_card
        text, kb = get_upgrade_premium_card(message.from_user)
        photo_url = "https://freeimage.host/i/n04TxVa"
        try:
            await message.reply_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    # Check cooldown
    can_proceed, response_message = await check_interval(user_id, await chk_user(message, user_id))
    if not can_proceed:
        await message.reply(response_message)
        return

    # Add user to the loop
    batch_active_loops[user_id] = True

    link = message.text if "tg://openmessage" in message.text else get_link(message.text)
    msg = await message.reply("Processing...")

    userbot = await initialize_userbot(user_id)
    try:
        if await is_normal_tg_link(link):
            # Pass userbot if available; handle normal Telegram links
            await process_and_upload_link(userbot, user_id, msg.id, link, 0, message)
            await set_interval(user_id, interval_minutes=45)
        else:
            # Handle special Telegram links
            await process_special_links(userbot, user_id, msg, link)
    except FloodWait as fw:
        await msg.edit_text(f'Try again after {fw.x} seconds due to floodwait from Telegram.')
    except Exception as e:
        await msg.edit_text(f"Link: `{link}`\n\n**Error:** {str(e)}")
    finally:
        users_loop[user_id] = False
        # Userbot is globally managed by userbot_manager; keep alive
        try:
            await msg.delete()
        except Exception:
            pass


async def initialize_userbot(user_id):
    """Returns the shared unified userbot session for the given user."""
    try:
        from toxic.core.userbot_manager import get_or_create_userbot
        return await get_or_create_userbot(user_id)
    except Exception as e:
        print(f"[Main] initialize_userbot error for {user_id}: {e}")
        return None


async def is_normal_tg_link(link: str) -> bool:
    """Check if the link is a standard Telegram link."""
    # Updated to handle more domains and topic links robustly
    special_identifiers = ['t.me/+', 't.me/c/', 't.me/b/', 'tg://openmessage', 'telegram.me/+', 'telegram.me/c/', 'telegram.dog/+', 'telegram.dog/c/']
    return any(domain in link for domain in ['t.me/', 'telegram.me/', 'telegram.dog/']) and not any(x in link for x in special_identifiers)
    
async def process_special_links(userbot, user_id, msg, link):
    """Handle special Telegram links."""
    if 't.me/+' in link:
        result = await userbot_join(userbot, link)
        await msg.edit_text(result)
    elif any(sub in link for sub in ['t.me/c/', 't.me/b/', '/s/', 'tg://openmessage', 'telegram.me/c/', 'telegram.dog/c/', 'telegram.me/s/', 'telegram.dog/s/']):
        await process_and_upload_link(userbot, user_id, msg.id, link, 0, msg)
        await set_interval(user_id, interval_minutes=45)
    else:
        await msg.edit_text("Invalid link format.")


def parse_batch_link_endpoint(link_str: str):
    """
    Parses any Telegram link format (public post, private channel, forum topic post, openmessage URI)
    and returns (base_url, msg_id, is_tg_openmessage)
    """
    if not link_str:
        return None, None, False

    clean_link = link_str.strip()
    if 'tg://' not in clean_link:
        clean_link = clean_link.split('?')[0].rstrip('/')

    # Format 1: tg://openmessage
    if 'tg://openmessage' in clean_link:
        import urllib.parse
        parsed_url = urllib.parse.urlparse(clean_link)
        params = urllib.parse.parse_qs(parsed_url.query)
        msg_id_val = params.get("message_id", [None])[0] or params.get("msg_id", [None])[0]
        if msg_id_val and msg_id_val.isdigit():
            cs = int(msg_id_val)
            remaining_params = "&".join([f"{k}={v[0]}" for k, v in params.items() if k not in ('message_id', 'msg_id')])
            base_url = f"tg://openmessage?{remaining_params}" if remaining_params else "tg://openmessage"
            return base_url, cs, True
        return None, None, True

    # Format 2: Web Links (t.me/c/..., t.me/..., telegram.me/...)
    parts = clean_link.split('/')
    if parts and parts[-1].isdigit():
        cs = int(parts[-1])
        base_url = '/'.join(parts[:-1])
        return base_url, cs, False

    return None, None, False


@app.on_message(filters.command("batch") & filters.private)
async def batch_link(_, message):
    join = await subscribe(_, message)
    if join == 1:
        return
    from toxic.core.func import is_free_user, get_upgrade_premium_card, chk_user
    from config import FREEMIUM_LIMIT
    from toxic.modules.shrink import is_user_verified

    user_id = message.chat.id
    freecheck = await chk_user(message, user_id)
    if freecheck == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID:
        text, kb = get_upgrade_premium_card(message.from_user)
        photo_url = "https://freeimage.host/i/n04TxVa"
        try:
            await message.reply_photo(photo=photo_url, caption=text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    # Check if a batch process is already running
    if batch_active_loops.get(user_id, False):
        await app.send_message(
            message.chat.id,
            "⚠️ You already have a batch process running. Please wait for it to complete or use /stop."
        )
        return

    # Check if command has inline arguments: /batch <start_link> <end_link_or_count>
    args = message.text.split(maxsplit=2)[1:]
    if len(args) >= 2:
        start_arg = args[0].strip()
        end_or_count_arg = args[1].strip()
        base_url, cs, is_tg_openmessage = parse_batch_link_endpoint(start_arg)
        if base_url and cs:
            max_batch_size = FREEMIUM_LIMIT if freecheck == 1 else PREMIUM_LIMIT
            cl = None
            if end_or_count_arg.isdigit():
                cl = int(end_or_count_arg)
            else:
                _, end_id, _ = parse_batch_link_endpoint(end_or_count_arg)
                if end_id:
                    if end_id < cs:
                        cs, end_id = end_id, cs
                    cl = (end_id - cs) + 1

            if cl and 1 <= cl <= max_batch_size:
                await execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck)
                return

    # Check if they have saved progress
    last_url = load_user_data(user_id, "last_batch_url")
    if last_url:
        buttons = [
            [InlineKeyboardButton("▶️ Continue Last Batch", callback_data="resume_batch")],
            [InlineKeyboardButton("🆕 Start New Batch", callback_data="new_batch")]
        ]
        await app.send_message(
            user_id,
            f"Found previous batch progress! 📂\n\n🔗 **Last URL:** `{last_url}`\n\nWould you like to continue from this point or start a new batch?",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    await prompt_new_batch(user_id, message)


async def prompt_new_batch(user_id, message):
    freecheck = await chk_user(message, user_id)
    if freecheck == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID:
        from toxic.core.func import get_upgrade_premium_card
        text, kb = get_upgrade_premium_card(message.from_user if hasattr(message, "from_user") else None)
        await app.send_message(user_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    max_batch_size = FREEMIUM_LIMIT if freecheck == 1 else PREMIUM_LIMIT

    # Start link input
    base_url = None
    cs = None
    is_tg_openmessage = False
    for attempt in range(3):
        await app.send_photo(
            user_id,
            photo="https://freeimage.host/i/n7cbXDX",
            caption="Just Copy Post Link And Send it To Me.\n\nजहाँ से शुरू करना है उस पोस्ट का लिंक भेजो\n\nMake sure the link is correct!"
        )
        start = await app.ask(user_id, "🎯 Send The Link For Where I Need To Start Process From \n\n> You Have Only 3 Tries")
        if not start or not start.text:
            continue
        start_id = start.text.strip()
        base_url, cs, is_tg_openmessage = parse_batch_link_endpoint(start_id)
        if base_url and cs:
            break
        await app.send_message(user_id, "❌ Invalid link format. Please send a valid Telegram post link...")
    else:
        await app.send_message(user_id, "Maximum attempts exceeded. Try later.")
        return

    # End link or Number of messages input
    cl = None
    for attempt in range(3):
        prompt_txt = (
            f"🎯 **Send End Post Link OR Total Count:** 🌝\n\n"
            f"• **Option 1:** Send the number of messages (e.g. `50`)\n"
            f"• **Option 2:** Send the End Post Link (e.g. `https://t.me/c/1234567890/150`)\n\n"
            f"> Max limit: `{max_batch_size}` messages"
        )
        end_input = await app.ask(user_id, prompt_txt)
        if not end_input or not end_input.text:
            continue
        text_val = end_input.text.strip()
        if text_val.isdigit():
            val = int(text_val)
            if 1 <= val <= max_batch_size:
                cl = val
                break
        else:
            _, end_id, _ = parse_batch_link_endpoint(text_val)
            if end_id:
                if end_id < cs:
                    cs, end_id = end_id, cs
                val = (end_id - cs) + 1
                if 1 <= val <= max_batch_size:
                    cl = val
                    break
        await app.send_message(
            user_id, 
            f"❌ Invalid count or end link. Please enter a valid number (1 to {max_batch_size}) or an end post link."
        )
    else:
        await app.send_message(user_id, "Maximum attempts exceeded. Try later.")
        return

    await execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck)


async def prompt_resume_batch(user_id, message):
    freecheck = await chk_user(message, user_id)
    if freecheck == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID:
        from toxic.core.func import get_upgrade_premium_card
        text, kb = get_upgrade_premium_card(message.from_user if hasattr(message, "from_user") else None)
        await app.send_message(user_id, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        return

    max_batch_size = FREEMIUM_LIMIT if freecheck == 1 else PREMIUM_LIMIT
    last_url = load_user_data(user_id, "last_batch_url")
    if not last_url:
        await app.send_message(user_id, "No saved batch progress found.")
        return

    base_url, cs, is_tg_openmessage = parse_batch_link_endpoint(last_url)
    if not base_url or not cs:
        await app.send_message(user_id, "Failed to parse saved batch link.")
        return

    # End link or Number of messages input
    cl = None
    for attempt in range(3):
        prompt_txt = (
            f"🎯 Resuming from message ID `{cs}`!\n\n"
            f"• **Option 1:** Send count (e.g. `50`)\n"
            f"• **Option 2:** Send End Post Link (e.g. `https://t.me/c/1234567890/150`)\n\n"
            f"> Max limit: `{max_batch_size}` messages"
        )
        end_input = await app.ask(user_id, prompt_txt)
        if not end_input or not end_input.text:
            continue
        text_val = end_input.text.strip()
        if text_val.isdigit():
            val = int(text_val)
            if 1 <= val <= max_batch_size:
                cl = val
                break
        else:
            _, end_id, _ = parse_batch_link_endpoint(text_val)
            if end_id:
                if end_id < cs:
                    cs, end_id = end_id, cs
                val = (end_id - cs) + 1
                if 1 <= val <= max_batch_size:
                    cl = val
                    break
        await app.send_message(
            user_id, 
            f"❌ Invalid count or end link. Please enter a valid number (1 to {max_batch_size}) or an end post link."
        )
    else:
        await app.send_message(user_id, "Maximum attempts exceeded. Try later.")
        return

    await execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck)


async def execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck):
    can_proceed, response_message = await check_interval(user_id, freecheck)
    if not can_proceed:
        await app.send_message(user_id, response_message)
        return

    join_button = InlineKeyboardButton("Join Channel", url="https://t.me/+7R-7p7jVoz9mM2M1")
    stop_button = InlineKeyboardButton("🚫 Stop Batch", callback_data=f"stop_batch_{user_id}")
    keyboard = InlineKeyboardMarkup([[join_button], [stop_button]])
    
    pin_msg = await app.send_message(
        user_id,
        f"🚀 **Batch process started!**\n\n"
        f"📊 **Progress:** [░░░░░░░░░░] 0%\n"
        f"✅ **Extracted:** `0/{cl}`\n"
        f"⏩ **Skipped:** `0`\n"
        f"❌ **Failed:** `0`\n"
        f"⏳ **Status:** Initializing...",
        reply_markup=keyboard
    )
    try:
        await pin_msg.pin(both_sides=True)
    except Exception:
        pass

    batch_active_loops[user_id] = True
    userbot = None
    success_count = 0
    fail_count = 0
    skipped_count = 0
    start_time_batch = time.time()
    last_ui_update = start_time_batch

    # Reusable background status message to prevent FloodWait
    status_msg = None
    try:
        status_msg = await app.send_message(user_id, "⚡ **Batch process running in background...**")
    except Exception:
        pass
    status_edit_id = status_msg.id if status_msg else None

    try:
        # Guarantee userbot initialization for user
        userbot = await initialize_userbot(user_id)
        
        for i in range(cs, cs + cl):
            if user_id not in batch_active_loops or not batch_active_loops[user_id]:
                break
            
            if is_tg_openmessage:
                url = f"{base_url}&message_id={i}"
            else:
                url = f"{base_url}/{i}"
            link = url
            
            # Check link type and guarantee userbot connectivity
            is_special = any(x in link for x in ['t.me/b/', 't.me/c/', 'tg://openmessage', 'telegram.me/c/', 'telegram.dog/c/'])
            if not userbot or not getattr(userbot, "is_connected", False):
                userbot = await initialize_userbot(user_id)
                if not userbot and is_special:
                    fail_count += 1
                    continue
            
            # Save batch progress to MongoDB before processing so user can resume exactly here
            save_user_data(user_id, "last_batch_url", url)
            
            try:
                # Process the message
                res = await get_msg(userbot, user_id, status_edit_id, link, 0, pin_msg)
                if res is True:
                    success_count += 1
                elif res == "skipped":
                    skipped_count += 1
                else:
                    fail_count += 1
                await asyncio.sleep(0.3) 
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                try:
                    res = await get_msg(userbot, user_id, status_edit_id, link, 0, pin_msg)
                    if res is True:
                        success_count += 1
                    elif res == "skipped":
                        skipped_count += 1
                    else:
                        fail_count += 1
                except Exception:
                    fail_count += 1
            except Exception as e:
                print(f"Error at {i}: {e}")
                reconnected = False
                if is_special:
                    try:
                        userbot = await initialize_userbot(user_id)
                        if userbot and getattr(userbot, "is_connected", False):
                            await asyncio.sleep(1)
                            res = await get_msg(userbot, user_id, status_edit_id, link, 0, pin_msg)
                            if res is True:
                                success_count += 1
                                reconnected = True
                            elif res == "skipped":
                                skipped_count += 1
                                reconnected = True
                    except Exception as retry_err:
                        print(f"Batch retry error at {i}: {retry_err}")
                if not reconnected:
                    fail_count += 1
            
            # Live progress UI update every 3 seconds
            now = time.time()
            done = success_count + fail_count + skipped_count
            if (now - last_ui_update > 3.0) or done == cl:
                last_ui_update = now
                elapsed_time = now - start_time_batch
                avg_time_per_msg = elapsed_time / done if done > 0 else 1.0
                remaining_msgs = cl - done
                eta_seconds = max(0, int(remaining_msgs * avg_time_per_msg))
                eta_str = str(timedelta(seconds=eta_seconds))
                pct = int((done / cl) * 100) if cl > 0 else 0
                filled = int(pct / 10)
                bar = "█" * filled + "░" * (10 - filled)
                
                try:
                    await pin_msg.edit_text(
                        f"🚀 **Batch process in progress...**\n\n"
                        f"📊 **Progress:** [{bar}] {pct}%\n"
                        f"✅ **Extracted:** `{success_count}/{cl}`\n"
                        f"⏩ **Skipped (Empty/Deleted):** `{skipped_count}`\n"
                        f"❌ **Failed:** `{fail_count}`\n"
                        f"⏳ **ETA:** `{eta_str}`\n"
                        f"📍 **Current ID:** `{i}`",
                        reply_markup=keyboard
                    )
                except Exception:
                    pass

        final_status = "completed" if batch_active_loops.get(user_id) else "stopped"
        
        # Clean up temporary status message
        if status_msg:
            try:
                await status_msg.delete()
            except Exception:
                pass

        # If successfully completed, save the next URL index for subsequent batches
        if final_status == "completed":
            if is_tg_openmessage:
                next_url = f"{base_url}&message_id={cs + cl}"
            else:
                next_url = f"{base_url}/{cs + cl}"
            save_user_data(user_id, "last_batch_url", next_url)
            
        await pin_msg.edit_text(
            f"✅ **Batch {final_status}!**\n\n"
            f"✨ **Extracted:** `{success_count}`\n"
            f"⏩ **Skipped (Empty/Deleted):** `{skipped_count}`\n"
            f"❌ **Failed:** `{fail_count}`\n"
            f"📊 **Total Scanned:** `{cl}`",
            reply_markup=InlineKeyboardMarkup([[join_button]])
        )
        await app.send_message(user_id, f"Batch process {final_status}! ✨\nExtracted: {success_count} | Skipped: {skipped_count} | Failed: {fail_count}")
        if final_status == "completed" and freecheck == 1:
            upgrade_msg = (
                "⚡ **𝖴𝗉𝗀𝗋𝖺𝖽𝖾 𝗍𝗈 𝖯𝖱𝖮!** ⚡\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "✨ **𝖴𝗇𝗅𝗈𝖼𝗄 𝖯𝗋𝖾𝗆𝗂𝗎𝗆 𝖥𝖾𝖺𝗍𝗎𝗋𝖾𝗌:**\n"
                "• **𝖴𝗇𝗅𝗂𝗆𝗂𝗍𝖾𝖽 𝖡𝖺𝗍𝖼𝗁 𝖫𝗂𝗆𝗂𝗍𝗌** (5000+ files!)\n"
                "• **𝖲𝗎𝗉𝖾𝗋 𝖥𝖺𝗌𝗍 𝖯𝖺𝗋𝖺𝗅𝗅𝖾𝗅 𝖣𝗈𝗐𝗇𝗅𝗈𝖺𝖽𝗂𝗀** 🚀\n"
                "• **𝖭𝗈 𝖠𝖽𝗌 & 𝖢𝗎𝗌𝗍𝗈𝗆 𝖡𝗋𝖺𝗇𝖽𝗂𝗇𝗀** 🏷️\n"
                "• **𝖣𝗂𝗋𝖾𝖼𝗍 𝖱𝖾𝗌𝖾𝗅𝗅𝖾𝗋 𝖲𝗎𝗉𝗉𝗈𝗋𝗍** 👑\n\n"
                "👉 Use `/plans` to view details & upgrade today!"
            )
            buttons = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
                    [InlineKeyboardButton("💬 Contact Now", url="https://t.me/CrazyxDeveloper_Bot")],
                ]
            )
            await app.send_message(user_id, upgrade_msg, reply_markup=buttons)
        
        if final_status == "completed":
            target_chat_id = get_target_chat_id(user_id)
            if target_chat_id and target_chat_id != user_id:
                chat_id = target_chat_id
                topic_id = None
                if isinstance(chat_id, str) and '/' in chat_id:
                    try:
                        parts = chat_id.split('/', 1)
                        chat_id = int(parts[0])
                        topic_id = int(parts[1])
                    except Exception:
                        pass
                try:
                    await app.send_message(chat_id, "> **✅ 𝗖ꪮ𝗺𝗽𝗹𝗲𝘁𝗲 𝗛ꪮ 𝗚𝘆𝗮 𝗕ꪮ$$ 😎**", reply_to_message_id=topic_id)
                except Exception as e:
                    print(f"Failed to send complete message to target chat: {e}")

    except Exception as e:
        await app.send_message(user_id, f"Critical Error: {e}")
    finally:
        batch_active_loops.pop(user_id, None)



@app.on_callback_query(filters.regex(r"^(resume_batch|new_batch)$"))
async def batch_choice_callback(_, query):
    user_id = query.from_user.id
    action = query.data
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass

    if action == "resume_batch":
        await prompt_resume_batch(user_id, query.message)
    elif action == "new_batch":
        await prompt_new_batch(user_id, query.message)

@app.on_callback_query(filters.regex(r"stop_batch_(\d+)"))
async def stop_batch_callback(_, query):
    user_id = int(query.matches[0].group(1))
    if query.from_user.id != user_id:
        return await query.answer("This is not your process!", show_alert=True)
    
    if user_id in batch_active_loops:
        batch_active_loops[user_id] = False
        await query.answer("Batch process stopping...", show_alert=True)
    else:
        await query.answer("No active batch process found.", show_alert=True)

@app.on_message(filters.command(["cancel", "stop", "cancel_mirror", "stop_mirror"]))
async def stop_batch_command(_, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    
    # 1. Stop all batch processes
    for uid in list(users_loop.keys()):
        users_loop[uid] = False
    for uid in list(batch_active_loops.keys()):
        batch_active_loops[uid] = False

    # 2. Stop all topic mirror and extraction tasks
    stopped_mirrors = 0
    try:
        from toxic.modules.topic_mirror import stop_all_active_mirrors
        stopped_mirrors = stop_all_active_mirrors()
    except Exception as e:
        print(f"Error stopping mirrors: {e}")

    # 3. Stop range forwarder tasks
    try:
        from toxic.modules.range_forwarder import active_range_jobs
        for uid in list(active_range_jobs.keys()):
            active_range_jobs[uid]["running"] = False
    except Exception:
        pass

    stop_card = (
        "<blockquote>🛑 <b>All Bot Tasks Stopped Successfully!</b></blockquote>\n\n"
        "✨ <b>Status:</b> All active tasks (Topic Mirror, Batch, Downloads) aborted\n"
        "💾 <b>Checkpoints:</b> Safely preserved in database!\n\n"
        "<i>Ab koi bhi background task run nahi ho raha hai. Aap jab chahein naya task fresh shuru kar sakte hain.</i>"
    )
    await message.reply_text(stop_card, parse_mode=ParseMode.HTML)
