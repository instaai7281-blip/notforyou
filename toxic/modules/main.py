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
from pyrogram.types import Message
from toxic.modules.shrink import is_user_verified
async def generate_random_name(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))




users_loop = {}
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
    if users_loop.get(user_id, False):
        await message.reply(
            "You already have an ongoing process. Please wait for it to finish or cancel it with /cancel."
        )
        return

    # Check freemium limits
    if await chk_user(message, user_id) == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID and not await is_user_verified(user_id):
        await message.reply("Freemium service is currently not available. Upgrade to premium for access.")
        return

    # Check cooldown
    can_proceed, response_message = await check_interval(user_id, await chk_user(message, user_id))
    if not can_proceed:
        await message.reply(response_message)
        return

    # Add user to the loop
    users_loop[user_id] = True

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
        if userbot:
            await userbot.stop()
        try:
            await msg.delete()
        except Exception:
            pass


async def initialize_userbot(user_id): # this ensure the single startup .. even if logged in or not
    """Initialize the userbot session for the given user."""
    data = await db.get_data(user_id)
    if data and data.get("session"):
        try:
            device = 'iPhone 16 Pro' # added gareebi text
            userbot = Client(
                f"userbot_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                device_model=device,
                session_string=data.get("session"),
                in_memory=True,
                no_updates=True,
                max_concurrent_transmissions=16
            )
            await userbot.start()
            return userbot
        except Exception:
            return None
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


@app.on_message(filters.command("batch") & filters.private)
async def batch_link(_, message):
    join = await subscribe(_, message)
    if join == 1:
        return
    user_id = message.chat.id
    # Check if a batch process is already running
    if users_loop.get(user_id, False):
        await app.send_message(
            message.chat.id,
            "You already have a batch process running. Please wait for it to complete."
        )
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


@app.on_callback_query(filters.regex(r"^resume_batch$|^new_batch$"))
async def handle_batch_choice(_, query):
    user_id = query.from_user.id
    choice = query.data
    await query.message.delete()
    
    if choice == "new_batch":
        await prompt_new_batch(user_id, query.message)
    elif choice == "resume_batch":
        await prompt_resume_batch(user_id, query.message)


async def prompt_new_batch(user_id, message):
    freecheck = await chk_user(message, user_id)
    if freecheck == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID and not await is_user_verified(user_id):
        await app.send_message(user_id, "Freemium service is currently not available. Upgrade to premium for access.")
        return

    max_batch_size = FREEMIUM_LIMIT if freecheck == 1 else PREMIUM_LIMIT

    # Start link input
    for attempt in range(3):
        await app.send_photo(
            user_id,
            photo="https://i.postimg.cc/BXkchVpY/image.jpg",
            caption="Just Copy Post Link And Send it To Me.\n\nजहाँ से शुरू करना है उस पोस्ट का लिंक भेजो\n\nMake sure the link is correct!"
        )
        start = await app.ask(user_id, "🎯 Send The Link For Where I Need To Start Process From \n\n> You Have Only 3 Tries")
        start_id = start.text.strip().rstrip('/')
        
        # Clean query parameters except for tg:// openmessage
        if 'tg://' not in start_id:
            start_id = start_id.split('?')[0]

        is_tg_openmessage = False
        if 'tg://openmessage' in start_id:
            import urllib.parse
            parsed_url = urllib.parse.urlparse(start_id)
            params = urllib.parse.parse_qs(parsed_url.query)
            msg_id_val = params.get("message_id", [None])[0]
            if msg_id_val and msg_id_val.isdigit():
                cs = int(msg_id_val)
                # Rebuild parameters without message_id
                remaining_params = "&".join([f"{k}={v[0]}" for k, v in params.items() if k != 'message_id'])
                base_url = f"tg://openmessage?{remaining_params}"
                is_tg_openmessage = True
                break
        else:
            s = start_id.split("/")[-1]
            if s.isdigit():
                cs = int(s)
                base_url = '/'.join(start_id.split('/')[:-1])
                is_tg_openmessage = False
                break
        await app.send_message(user_id, "Invalid link. Please send again ...")
    else:
        await app.send_message(user_id, "Maximum attempts exceeded. Try later.")
        return

    # Number of messages input
    for attempt in range(3):
        num_messages = await app.ask(user_id, f"How many messages do you want to process? 🌝\n> Max limit {max_batch_size}")
        try:
            cl = int(num_messages.text.strip())
            if 1 <= cl <= max_batch_size:
                break
            raise ValueError()
        except ValueError:
            await app.send_message(
                user_id, 
                f"Invalid number. Please enter a number between 1 and {max_batch_size}."
            )
    else:
        await app.send_message(user_id, "Maximum attempts exceeded. Try later.")
        return

    await execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck)


async def prompt_resume_batch(user_id, message):
    freecheck = await chk_user(message, user_id)
    if freecheck == 1 and FREEMIUM_LIMIT == 0 and user_id not in OWNER_ID and not await is_user_verified(user_id):
        await app.send_message(user_id, "Freemium service is currently not available. Upgrade to premium for access.")
        return

    max_batch_size = FREEMIUM_LIMIT if freecheck == 1 else PREMIUM_LIMIT
    last_url = load_user_data(user_id, "last_batch_url")
    if not last_url:
        await app.send_message(user_id, "No saved batch progress found.")
        return

    # Parse saved URL
    if 'tg://' not in last_url:
        last_url = last_url.split('?')[0]

    is_tg_openmessage = False
    if 'tg://openmessage' in last_url:
        import urllib.parse
        parsed_url = urllib.parse.urlparse(last_url)
        params = urllib.parse.parse_qs(parsed_url.query)
        msg_id_val = params.get("message_id", [None])[0]
        if msg_id_val and msg_id_val.isdigit():
            cs = int(msg_id_val)
            remaining_params = "&".join([f"{k}={v[0]}" for k, v in params.items() if k != 'message_id'])
            base_url = f"tg://openmessage?{remaining_params}"
            is_tg_openmessage = True
        else:
            await app.send_message(user_id, "Failed to parse saved batch link.")
            return
    else:
        s = last_url.split("/")[-1]
        if s.isdigit():
            cs = int(s)
            base_url = '/'.join(last_url.split('/')[:-1])
            is_tg_openmessage = False
        else:
            await app.send_message(user_id, "Failed to parse saved batch link.")
            return

    # Number of messages input
    for attempt in range(3):
        num_messages = await app.ask(user_id, f"How many messages do you want to process starting from message ID `{cs}`? 🌝\n> Max limit {max_batch_size}")
        try:
            cl = int(num_messages.text.strip())
            if 1 <= cl <= max_batch_size:
                break
            raise ValueError()
        except ValueError:
            await app.send_message(
                user_id, 
                f"Invalid number. Please enter a number between 1 and {max_batch_size}."
            )
    else:
        await app.send_message(user_id, "Maximum attempts exceeded. Try later.")
        return

    await execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck)


async def execute_batch(user_id, base_url, cs, cl, is_tg_openmessage, freecheck):
    # Interval check
    can_proceed, response_message = await check_interval(user_id, freecheck)
    if not can_proceed:
        await app.send_message(user_id, response_message)
        return

    join_button = InlineKeyboardButton("Join Channel", url="https://t.me/+7R-7p7jVoz9mM2M1")
    stop_button = InlineKeyboardButton("🚫 Stop Batch", callback_data=f"stop_batch_{user_id}")
    keyboard = InlineKeyboardMarkup([[join_button], [stop_button]])
    
    pin_msg = await app.send_message(
        user_id,
        f"🚀 **Batch process started!**\n\n✅ **Processed:** 0/{cl}\n❌ **Failed:** 0\n⏳ **Status:** Initializing...",
        reply_markup=keyboard
    )
    await pin_msg.pin(both_sides=True)

    users_loop[user_id] = True
    userbot = None
    success_count = 0
    fail_count = 0
    start_time_batch = time.time()
    
    try:
        userbot = await initialize_userbot(user_id)
        
        for i in range(cs, cs + cl):
            if user_id not in users_loop or not users_loop[user_id]:
                break
            
            if is_tg_openmessage:
                url = f"{base_url}&message_id={i}"
            else:
                url = f"{base_url}/{i}"
            link = url
            
            # Check link type
            is_special = any(x in link for x in ['t.me/b/', 't.me/c/', 'tg://openmessage', 'telegram.me/c/', 'telegram.dog/c/'])
            if is_special and not userbot:
                fail_count += 1
                continue
            
            # Save batch progress to MongoDB before processing so they can continue from the exact failure/stop point
            save_user_data(user_id, "last_batch_url", url)
            
            try:
                # Process the message
                await get_msg(userbot, user_id, None, link, 0, pin_msg)
                success_count += 1
                # Adaptive delay to avoid flood waits
                await asyncio.sleep(0.5) 
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                # Retry once after flood wait
                try:
                    await get_msg(userbot, user_id, None, link, 0, pin_msg)
                    success_count += 1
                except:
                    fail_count += 1
            except Exception as e:
                print(f"Error at {i}: {e}")
                fail_count += 1
            
            # Update progress
            done = success_count + fail_count
            if done % 2 == 0 or done == cl:
                # Calculate ETA
                elapsed_time = time.time() - start_time_batch
                avg_time_per_msg = elapsed_time / done if done > 0 else 1.5
                remaining_msgs = cl - done
                eta_seconds = int(remaining_msgs * avg_time_per_msg)
                eta_str = str(timedelta(seconds=eta_seconds))
                
                try:
                    await pin_msg.edit_text(
                        f"🚀 **Batch process in progress...**\n\n"
                        f"✅ **Processed:** {success_count}/{cl}\n"
                        f"❌ **Failed:** {fail_count}\n"
                        f"⏳ **ETA:** `{eta_str}`\n"
                        f"📍 **Current ID:** `{i}`\n\n"
                        f"⚝**",
                        reply_markup=keyboard
                    )
                except:
                    pass

        final_status = "completed" if users_loop.get(user_id) else "stopped"
        
        # If successfully completed, save the next URL index for subsequent batches
        if final_status == "completed":
            if is_tg_openmessage:
                next_url = f"{base_url}&message_id={cs + cl}"
            else:
                next_url = f"{base_url}/{cs + cl}"
            save_user_data(user_id, "last_batch_url", next_url)
            
        await pin_msg.edit_text(
            f"✅ **Batch {final_status}!**\n\n✨ **Success:** {success_count}\n❌ **Failed:** {fail_count}\n📊 **Total:** {cl}\n\n⚝__**",
            reply_markup=InlineKeyboardMarkup([[join_button]])
        )
        await app.send_message(user_id, f"Batch process {final_status}! ✨\nSuccess: {success_count} | Failed: {fail_count}")
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
                    [InlineKeyboardButton("💬 Contact Now", url="https://t.me/SRC_PRO_BOT")],
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
                    await app.send_message(chat_id, "> **✅ 𝗖ꪮ𝗺𝗽𝗹𝗲𝘁𝗲 𝗛ꪮ 𝗚𝗮𝘆𝗮 𝗕ꪮ$$ 😎**", reply_to_message_id=topic_id)
                except Exception as e:
                    print(f"Failed to send complete message to target chat: {e}")

    except Exception as e:
        await app.send_message(user_id, f"Critical Error: {e}")
    finally:
        users_loop.pop(user_id, None)
        if userbot:
            await userbot.stop()

@app.on_callback_query(filters.regex(r"stop_batch_(\d+)"))
async def stop_batch_callback(_, query):
    user_id = int(query.matches[0].group(1))
    if query.from_user.id != user_id:
        return await query.answer("This is not your process!", show_alert=True)
    
    if user_id in users_loop:
        users_loop[user_id] = False
        await query.answer("Batch process stopping...", show_alert=True)
    else:
        await query.answer("No active batch process found.", show_alert=True)

@app.on_message(filters.command("cancel"))
async def stop_batch_command(_, message):
    user_id = message.chat.id
    if user_id in users_loop:
        users_loop[user_id] = False
        await message.reply("Batch process stopping... 🛑")
    else:
        await message.reply("No active batch process to cancel.")
