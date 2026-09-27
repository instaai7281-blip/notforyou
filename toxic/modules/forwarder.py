import asyncio
import time
import re
from datetime import timedelta
from pyrogram import filters, Client
from toxic import app, get_client
from config import OWNER_ID, LOG_GROUP
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from toxic.core.func import chk_user
from toxic.core.mongo import db

def parse_tg_link(link):
    try:
        parts = [p for p in link.split("/") if p]
        if 't.me/c/' in link or 't.me/b/' in link:
            if 't.me/b/' in link:
                chat = parts[-2]
                msg_id = int(parts[-1])
            else:
                chat = int('-100' + parts[parts.index('c') + 1])
                msg_id = int(parts[-1])
            return chat, msg_id
        elif 't.me/' in link or 'telegram.me/' in link or 'telegram.dog/' in link:
            domain = "t.me/" if "t.me/" in link else "telegram.me/" if "telegram.me/" in link else "telegram.dog/"
            subparts = [p for p in link.split(domain)[1].split("/") if p]
            chat = subparts[0]
            if chat.isdigit():
                chat = int("-100" + chat)
            msg_id = int(subparts[-1])
            return chat, msg_id
    except Exception as e:
        print(f"Error parsing link {link}: {e}")
    return None, None

@app.on_message(filters.command("logforward"))
async def log_forward_cmd(_, message):
    # Always authorize and prompt using the sender's user ID so it works in groups/channels and private DMs
    if not message.from_user:
        await message.reply("❌ **Error:** This command must be sent by a user.")
        return
        
    user_id = message.from_user.id
    
    # Check authorization (Owner or Premium User)
    if await chk_user(message, user_id) != 0:
        await message.reply("❌ **Access Denied:** Only premium users or the bot owner can use this command.")
        return

    # 1. Ask for Target Identifier (User ID or Username)
    try:
        target_prompt = await app.ask(
            user_id,
            "🎯 **Send the User ID or Username of the target person:**\n\n*(e.g., `8014313443` or `_Himanshu_`)*\n\nSend `/cancel` to abort.",
            timeout=300
        )
    except Exception as e:
        await message.reply(
            "❌ **Interactive Prompt Failed:**\n"
            "Please start the bot first in private DM (@" + (await app.get_me()).username + ") "
            "so I can send you the configuration prompts!"
        )
        return

    if target_prompt.text == "/cancel":
        await app.send_message(user_id, "❌ Process cancelled.")
        return
        
    target_val = target_prompt.text.strip()
    if not target_val:
        await app.send_message(user_id, "❌ Invalid input. Process cancelled.")
        return

    # 2. Ask for Destination Channel/Group ID
    try:
        dest_prompt = await app.ask(
            user_id,
            "📥 **Send the Destination Channel/Group ID:**\n\n*(Must start with `-100`)*\n\nSend `/cancel` to abort.",
            timeout=300
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Session expired or error: `{e}`")
        return

    if dest_prompt.text == "/cancel":
        await app.send_message(user_id, "❌ Process cancelled.")
        return
        
    dest_chat_str = dest_prompt.text.strip()
    try:
        dest_chat_id = int(dest_chat_str)
    except ValueError:
        await app.send_message(user_id, "❌ Invalid chat ID format. Process cancelled.")
        return

    # 3. Ask for Starting Post Link
    try:
        link_prompt = await app.ask(
            user_id,
            "🔗 **Send the Start Post Link from the log channel:**\n\n*(I will only scan messages newer than this post for maximum speed)*\n\nSend `/cancel` to abort.",
            timeout=300
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Session expired or error: `{e}`")
        return

    if link_prompt.text == "/cancel":
        await app.send_message(user_id, "❌ Process cancelled.")
        return

    start_link = link_prompt.text.strip()
    log_group_chat, start_msg_id = parse_tg_link(start_link)
    if not log_group_chat or not start_msg_id:
        await app.send_message(user_id, "❌ **Invalid link format.** Must be a valid Telegram message link. Process cancelled.")
        return

    status_msg = await app.send_message(user_id, "⌛ **Initializing scanning session using user session...**")

    success_count = 0
    fail_count = 0
    skipped_count = 0
    start_time = time.time()
    
    try:
        # Use user session to bypass BOT_METHOD_INVALID
        client_to_use = get_client() or app
        
        # Verify access to LOG_GROUP
        try:
            await client_to_use.get_chat(log_group_chat)
        except Exception as e:
            await status_msg.edit(f"❌ **Cannot access Log Group using user session:** `{e}`\n\nPlease make sure your user account has joined/access to the log group.")
            return

        # Verify access to target chat (using app/bot or user session)
        try:
            await app.get_chat(dest_chat_id)
        except Exception as e:
            await status_msg.edit(f"❌ **Cannot access Destination Channel:** `{e}`\n\nPlease make sure the bot is an **Admin** in the target channel.")
            return

        await status_msg.edit(f"🔍 **Scanning Log Group starting from message ID {start_msg_id}...**")
        
        # Fetch user filters
        user_data = await db.get_data(user_id) or {}
        filters_data = user_data.get("filters", {})
        
        # Fetch log group messages
        messages_scanned = 0
        
        # We scan the history starting from the newest. We stop immediately once message ID is less than start_msg_id
        async for msg in client_to_use.get_chat_history(log_group_chat, limit=10000):
            if msg.id < start_msg_id:
                break
                
            messages_scanned += 1
            if messages_scanned % 10 == 0:
                try:
                    await status_msg.edit(
                        f"🔍 **Scanning Log Group...**\n\n"
                        f"📊 **Scanned:** `{messages_scanned}`\n"
                        f"✨ **Forwarded:** `{success_count}`\n"
                        f"⏭️ **Skipped:** `{skipped_count}`\n"
                        f"❌ **Failed:** `{fail_count}`"
                    )
                except:
                    pass

            # Check both msg.text (for text replies) and msg.caption (for media log copies)
            msg_text = msg.text or msg.caption or ""
            if msg_text and ("log info" in msg_text.lower() or "saved by" in msg_text.lower()):
                msg_text_clean = msg_text.lower()
                # Remove underscores and spaces from log text to perform high-accuracy fuzzy matching
                msg_text_fuzzy = re.sub(r'[\s_]+', '', msg_text_clean)
                
                # Resolve target identifiers for matching
                target_val_clean = target_val.replace("@", "").lower().strip()
                target_val_fuzzy = re.sub(r'[\s_]+', '', target_val_clean)

                # Check fuzzy match
                if (target_val_clean in msg_text_clean) or (target_val_fuzzy and target_val_fuzzy in msg_text_fuzzy):
                    parent_media_id = None
                    
                    # Case 1: The message is a reply to the media message
                    if msg.reply_to_message:
                        parent_media_id = msg.reply_to_message.id
                    elif getattr(msg, "reply_to_message_id", None):
                        parent_media_id = msg.reply_to_message_id
                        
                    # Case 2: The message itself is the media message
                    if not parent_media_id and (msg.video or msg.photo or msg.document or msg.audio or msg.voice):
                        parent_media_id = msg.id

                    if parent_media_id:
                        try:
                            # Fetch the actual media message to evaluate its type against filters
                            media_msg = await client_to_use.get_messages(log_group_chat, parent_media_id)
                            
                            # Determine media type
                            media_type = None
                            if media_msg.video:
                                media_type = "video"
                            elif media_msg.photo:
                                media_type = "photo"
                            elif media_msg.document:
                                media_type = "document"
                            elif media_msg.audio or media_msg.voice:
                                media_type = "audio"
                            elif media_msg.text:
                                media_type = "text"
                            
                            # Skip if media type is turned OFF in settings
                            if media_type and not filters_data.get(media_type, True):
                                skipped_count += 1
                                continue
                            
                            # Forward the parent media message to the destination (using user session or app)
                            try:
                                await app.copy_message(
                                    chat_id=dest_chat_id,
                                    from_chat_id=log_group_chat,
                                    message_id=parent_media_id
                                )
                            except Exception:
                                # Fallback to copy via user session client if bot fails
                                await client_to_use.copy_message(
                                    chat_id=dest_chat_id,
                                    from_chat_id=log_group_chat,
                                    message_id=parent_media_id
                                )
                                
                            success_count += 1
                            # Delay to prevent FloodWait rate limits
                            await asyncio.sleep(0.3)
                        except FloodWait as e:
                            await asyncio.sleep(e.value + 2)
                            try:
                                await app.copy_message(
                                    chat_id=dest_chat_id,
                                    from_chat_id=log_group_chat,
                                    message_id=parent_media_id
                                )
                                success_count += 1
                            except:
                                fail_count += 1
                        except Exception as e:
                            print(f"Failed to forward message {parent_media_id}: {e}")
                            fail_count += 1

        elapsed_time = time.time() - start_time
        
        await status_msg.edit(
            f"✅ **Log Forwarding Completed!**\n\n"
            f"👤 **Filter:** `{target_val}`\n"
            f"📥 **Destination:** `{dest_chat_id}`\n"
            f"📊 **Total Scanned:** `{messages_scanned}`\n"
            f"✨ **Successfully Forwarded:** `{success_count}`\n"
            f"⏭️ **Skipped (Filters):** `{skipped_count}`\n"
            f"❌ **Failed:** `{fail_count}`\n"
            f"⏱ **Time Elapsed:** `{int(elapsed_time)}s`"
        )
        
    except Exception as e:
        await status_msg.edit(f"❌ **An error occurred during log forwarding:** `{str(e)}`")


