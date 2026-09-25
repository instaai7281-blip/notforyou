# ---------------------------------------------------
# File Name: topic_mirror.py
# Description: Advanced Forum Topic Mirroring module with 2-Phase Topic Pre-Creation
#              and Automatic Save-Restricted / Protected Content Bypass.
# ---------------------------------------------------

import os
import re
import time
import asyncio
import random
from pyrogram import filters, Client, raw, types
from pyrogram.errors import FloodWait, RPCError, ChatAdminRequired, ChannelInvalid, ChannelPrivate
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from devgagan import app, get_client, pro_clients
from config import API_ID, API_HASH, OWNER_ID, LOG_GROUP, THUMBNAIL_DIR
from devgagan.core.func import chk_user, humanbytes, TimeFormatter
from devgagan.core.mongo import db

# In-memory tracking of active topic mirroring jobs
active_mirrors = {}

def parse_source_link(link: str):
    """
    Parses various Telegram message link formats and extracts:
    (chat_id, topic_id, message_id)
    """
    if not link:
        return None, None, None
    try:
        clean_link = link.strip()
        
        # Deep link: tg://openmessage?chat_id=-100123456&message_id=500
        if "tg://openmessage" in clean_link:
            chat_match = re.search(r'chat_id=(-?\d+)', clean_link)
            msg_match = re.search(r'message_id=(\d+)', clean_link)
            topic_match = re.search(r'topic_id=(\d+)', clean_link)
            
            chat_id = int(chat_match.group(1)) if chat_match else None
            msg_id = int(msg_match.group(1)) if msg_match else None
            topic_id = int(topic_match.group(1)) if topic_match else None
            return chat_id, topic_id, msg_id

        # Standard web link: https://t.me/c/1234567890/164/500 or https://t.me/c/1234567890/500
        clean_link = re.sub(r'https?://(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/', '', clean_link)
        parts = [p for p in clean_link.split('/') if p]

        if not parts:
            return None, None, None

        if parts[0] == 'c':
            # Private group/channel link
            if len(parts) >= 4:
                # Format: c/channel_id/topic_id/msg_id
                chat_id = int("-100" + parts[1])
                topic_id = int(parts[2])
                msg_id = int(parts[3])
                return chat_id, topic_id, msg_id
            elif len(parts) == 3:
                # Format: c/channel_id/msg_id
                chat_id = int("-100" + parts[1])
                msg_id = int(parts[2])
                return chat_id, None, msg_id
        else:
            # Public username link: username/topic_id/msg_id or username/msg_id
            if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                chat_id = parts[0]
                topic_id = int(parts[1])
                msg_id = int(parts[2])
                return chat_id, topic_id, msg_id
            elif len(parts) == 2 and parts[1].isdigit():
                chat_id = parts[0]
                msg_id = int(parts[1])
                return chat_id, None, msg_id

    except Exception as e:
        print(f"[TopicMirror] Error parsing source link '{link}': {e}")
    return None, None, None


async def get_working_userbot(user_id: int):
    """
    Returns an authenticated Pyrogram Client for the user (their own logged-in session,
    or a pool pro_client as fallback).
    """
    user_data = await db.get_data(user_id)
    user_session = user_data.get("session") if user_data else None

    if user_session:
        try:
            ub = Client(
                f"ub_tm_{user_id}_{int(time.time())}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=user_session,
                no_updates=True,
                max_concurrent_transmissions=128
            )
            await ub.start()
            return ub, True  # True = temporary client that needs .stop() when done
        except Exception as e:
            print(f"[TopicMirror] Failed to start user session client for {user_id}: {e}")

    # Fallback to pool client
    client = get_client()
    if client and client.is_connected:
        return client, False

    if pro_clients:
        for c in pro_clients:
            if c.is_connected:
                return c, False

    return None, False


async def apply_custom_caption(user_id: int, original_caption: str) -> str:
    """
    Applies user-specific caption filters, replacements, and branding tag.
    """
    caption = original_caption or ""
    try:
        data = await db.get_data(user_id)
        if data:
            # Remove clean words
            clean_words = data.get("clean_words") or []
            for word in clean_words:
                if word:
                    caption = caption.replace(word, "")

            # Text replacements
            to_replace = data.get("to_replace")
            replace_txt = data.get("replace_txt")
            if to_replace and replace_txt:
                caption = caption.replace(to_replace, replace_txt)

            # Custom template caption if configured
            custom_cap = data.get("caption")
            if custom_cap:
                caption = f"{custom_cap}\n\n{caption}".strip()
    except Exception as e:
        print(f"[TopicMirror] Caption cleaning error: {e}")

    return caption.strip()


async def fetch_all_messages_for_topic(userbot, src_chat_id, topic_id: int, max_limit: int = 5000):
    """
    Fetches all messages belonging to a topic using multiple strategies:
    1. Pyrogram get_discussion_replies (topics are reply threads to the topic creation message).
    2. Raw RPC messages.GetReplies.
    3. Fallback: get_chat_history scanning for messages matching message_thread_id / reply_to_top_id.
    """
    collected_messages = []
    seen_ids = set()

    # Strategy 1: get_discussion_replies (Standard Telegram Forum Topic mechanism)
    if topic_id and topic_id != 1:
        try:
            async for m in userbot.get_discussion_replies(src_chat_id, topic_id, limit=max_limit):
                if m and m.id not in seen_ids:
                    seen_ids.add(m.id)
                    collected_messages.append(m)
        except Exception as disc_err:
            print(f"[TopicMirror] get_discussion_replies notice for topic {topic_id}: {disc_err}")

    # Strategy 2: Raw RPC GetReplies if empty
    if not collected_messages and topic_id and topic_id != 1:
        try:
            peer = await userbot.resolve_peer(src_chat_id)
            offset_id = 0
            while len(collected_messages) < max_limit:
                res = await userbot.invoke(raw.functions.messages.GetReplies(
                    peer=peer,
                    msg_id=topic_id,
                    offset_id=offset_id,
                    offset_date=0,
                    add_offset=0,
                    limit=100,
                    max_id=0,
                    min_id=0,
                    hash=0
                ))
                raw_msgs = getattr(res, "messages", [])
                if not raw_msgs:
                    break
                new_found = 0
                for rm in raw_msgs:
                    parsed_m = await types.Message._parse(userbot, rm, {u.id: u for u in getattr(res, "users", [])}, {c.id: c for c in getattr(res, "chats", [])})
                    if parsed_m and parsed_m.id not in seen_ids:
                        seen_ids.add(parsed_m.id)
                        collected_messages.append(parsed_m)
                        new_found += 1
                offset_id = raw_msgs[-1].id
                if new_found == 0:
                    break
        except Exception as rpc_err:
            print(f"[TopicMirror] Raw GetReplies notice for topic {topic_id}: {rpc_err}")

    # Strategy 3: General topic or Fallback get_chat_history scan
    if not collected_messages:
        try:
            async for m in userbot.get_chat_history(src_chat_id, limit=max_limit):
                if not m or m.id in seen_ids:
                    continue
                # For General topic (id 1): only top-level messages without thread id or thread_id == 1
                if topic_id == 1:
                    m_thread = getattr(m, "message_thread_id", None)
                    reply_to = getattr(m, "reply_to_message_id", None)
                    if m_thread in (None, 1) and (not reply_to or reply_to == 1):
                        seen_ids.add(m.id)
                        collected_messages.append(m)
                else:
                    # Check if message belongs to this topic
                    m_thread = getattr(m, "message_thread_id", None)
                    reply_to = getattr(m, "reply_to_message_id", None)
                    if m_thread == topic_id or reply_to == topic_id:
                        seen_ids.add(m.id)
                        collected_messages.append(m)
        except Exception as scan_err:
            print(f"[TopicMirror] get_chat_history scan notice for topic {topic_id}: {scan_err}")

    # Sort messages chronologically (oldest first)
    collected_messages.sort(key=lambda x: x.id)
    return collected_messages


async def transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id: int):
    """
    Attempts server-side copy first. If protected/restricted (CHAT_FORWARDS_RESTRICTED),
    falls back to downloading via userbot and directly uploading to the target topic.
    """
    # 1. First Attempt: Fast server-side copy via userbot or app
    try:
        try:
            await userbot.copy_message(
                chat_id=tgt_chat_id,
                from_chat_id=src_chat_id,
                message_id=msg.id,
                reply_to_message_id=tgt_topic_id
            )
            return True, "copied"
        except Exception as forward_err:
            err_str = str(forward_err).upper()
            if "CHAT_FORWARDS_RESTRICTED" not in err_str and "CHATFORWARDSRESTRICTED" not in err_str:
                try:
                    await app.copy_message(
                        chat_id=tgt_chat_id,
                        from_chat_id=src_chat_id,
                        message_id=msg.id,
                        reply_to_message_id=tgt_topic_id
                    )
                    return True, "copied"
                except Exception:
                    pass
            # If it's a forward restriction or failed, proceed to restricted content bypass
            raise forward_err

    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)

    except Exception as e:
        err_msg = str(e).upper()

        # If pure text message without media:
        if msg.text:
            try:
                text_to_send = await apply_custom_caption(user_id, msg.text)
                await app.send_message(
                    chat_id=tgt_chat_id,
                    text=text_to_send if text_to_send else msg.text,
                    reply_to_message_id=tgt_topic_id,
                    disable_web_page_preview=True
                )
                return True, "text_sent"
            except FloodWait as fw:
                await asyncio.sleep(fw.value + 1)
                return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)
            except Exception as txt_err:
                print(f"[TopicMirror] Failed to send text msg {msg.id}: {txt_err}")
                return False, str(txt_err)

        # If message contains media:
        temp_file = None
        try:
            os.makedirs("./temp_mirror", exist_ok=True)
            # Download media via userbot
            temp_file = await userbot.download_media(
                msg,
                file_name=f"./temp_mirror/{user_id}_{src_chat_id}_{msg.id}_"
            )

            if not temp_file or not os.path.isfile(temp_file):
                return False, "Download failed"

            # Prepare caption
            orig_cap = msg.caption if msg.caption else ""
            final_caption = await apply_custom_caption(user_id, orig_cap)

            # Upload to target topic
            if msg.video:
                duration = msg.video.duration or 0
                width = msg.video.width or 0
                height = msg.video.height or 0
                await app.send_video(
                    chat_id=tgt_chat_id,
                    video=temp_file,
                    caption=final_caption,
                    duration=duration,
                    width=width,
                    height=height,
                    reply_to_message_id=tgt_topic_id,
                    supports_streaming=True
                )
            elif msg.document:
                await app.send_document(
                    chat_id=tgt_chat_id,
                    document=temp_file,
                    caption=final_caption,
                    reply_to_message_id=tgt_topic_id
                )
            elif msg.photo:
                await app.send_photo(
                    chat_id=tgt_chat_id,
                    photo=temp_file,
                    caption=final_caption,
                    reply_to_message_id=tgt_topic_id
                )
            elif msg.audio:
                await app.send_audio(
                    chat_id=tgt_chat_id,
                    audio=temp_file,
                    caption=final_caption,
                    duration=msg.audio.duration or 0,
                    performer=msg.audio.performer,
                    title=msg.audio.title,
                    reply_to_message_id=tgt_topic_id
                )
            elif msg.voice:
                await app.send_voice(
                    chat_id=tgt_chat_id,
                    voice=temp_file,
                    caption=final_caption,
                    reply_to_message_id=tgt_topic_id
                )
            elif msg.animation:
                await app.send_animation(
                    chat_id=tgt_chat_id,
                    animation=temp_file,
                    caption=final_caption,
                    reply_to_message_id=tgt_topic_id
                )
            elif msg.sticker:
                await app.send_sticker(
                    chat_id=tgt_chat_id,
                    sticker=temp_file,
                    reply_to_message_id=tgt_topic_id
                )
            else:
                # Default generic document fallback
                await app.send_document(
                    chat_id=tgt_chat_id,
                    document=temp_file,
                    caption=final_caption,
                    reply_to_message_id=tgt_topic_id
                )

            return True, "download_uploaded"

        except FloodWait as fw:
            await asyncio.sleep(fw.value + 1)
            return await transfer_single_message(userbot, app, src_chat_id, tgt_chat_id, tgt_topic_id, msg, user_id)
        except Exception as dl_up_err:
            print(f"[TopicMirror] Save-Restricted bypass error for msg {msg.id}: {dl_up_err}")
            return False, str(dl_up_err)
        finally:
            if temp_file and os.path.isfile(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass


@app.on_message(filters.command(["cancel_mirror", "cancelmirror"]))
async def cancel_mirror_cmd(_, message):
    user_id = message.from_user.id if message.from_user else message.chat.id
    if user_id in active_mirrors:
        active_mirrors[user_id] = False
        await message.reply("🛑 **Cancellation signal sent.** Topic mirror operation will stop shortly.")
    else:
        await message.reply("ℹ️ You have no active topic mirroring process running.")


@app.on_callback_query(filters.regex(r"^tmirror_cancel_(\d+)$"))
async def cancel_mirror_callback(_, query: CallbackQuery):
    req_uid = int(query.data.split("_")[2])
    user_id = query.from_user.id
    if user_id == req_uid or str(user_id) in [str(o) for o in (OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID])]:
        active_mirrors[req_uid] = False
        await query.answer("🛑 Cancelling topic mirror process...", show_alert=True)
    else:
        await query.answer("❌ You are not authorized to cancel this task.", show_alert=True)


@app.on_message(filters.command(["topicmirror", "tmirror", "mirror"]))
async def topic_mirror_cmd(client, message):
    if not message.from_user:
        await message.reply("❌ **Error:** This command must be sent by a user.")
        return

    user_id = message.from_user.id

    # Check Premium/Owner Authorization
    if await chk_user(message, user_id) != 0:
        await message.reply("❌ **Access Denied:** You need an active premium plan or owner access to use Topic Mirror.")
        return

    if user_id in active_mirrors and active_mirrors[user_id]:
        await message.reply("⚠️ **A mirroring operation is already running!** Send `/cancel_mirror` to abort it first.")
        return

    # STEP 1: Ask for Source Message/Topic Link
    try:
        prompt_1 = await app.ask(
            user_id,
            "🔗 **Send any message link from the SOURCE Topics group / channel:**\n\n"
            "*(e.g., `https://t.me/c/1234567890/164/500` or `https://t.me/username/100`)*\n\n"
            "Send `/cancel` to abort.",
            timeout=180
        )
    except Exception as e:
        await message.reply(
            "❌ **Interactive Prompt Failed:**\n"
            "Please start the bot first in private DM (@" + (await app.get_me()).username + ") to configure prompts!"
        )
        return

    if prompt_1.text == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    src_link = prompt_1.text.strip()
    src_chat_id, detected_topic_id, src_msg_id = parse_source_link(src_link)

    if not src_chat_id:
        await app.send_message(user_id, "❌ **Invalid Telegram link format.** Please provide a valid message link.")
        return

    # STEP 2: Ask for Target Supergroup ID
    user_db_data = await db.get_data(user_id)
    saved_target = user_db_data.get("chat_id") if user_db_data else None

    default_prompt_text = f"\n*(Default from settings: `{saved_target}` — send `ok` to use it)*" if saved_target else ""
    try:
        prompt_2 = await app.ask(
            user_id,
            f"📥 **Send the TARGET Supergroup ID:**\n\n"
            f"*(Must start with `-100`, e.g. `-100987654321`)*{default_prompt_text}\n\n"
            f"Send `/cancel` to abort.",
            timeout=180
        )
    except Exception as e:
        await app.send_message(user_id, f"❌ Session timed out or error: {e}")
        return

    if prompt_2.text == "/cancel":
        await app.send_message(user_id, "❌ Operation cancelled.")
        return

    target_input = prompt_2.text.strip()
    if target_input.lower() == "ok" and saved_target:
        tgt_chat_id = int(str(saved_target).split('/')[0])
    else:
        try:
            tgt_chat_id = int(target_input.split('/')[0])
        except ValueError:
            await app.send_message(user_id, "❌ **Invalid target chat ID.** Must be an integer starting with `-100`.")
            return

    # STEP 3: Ask Mirror Mode (All Topics vs Single Topic)
    mirror_all_topics = True
    if detected_topic_id:
        try:
            prompt_3 = await app.ask(
                user_id,
                f"🎛️ **Topic Selection Detected:**\n\n"
                f"• Source Topic ID detected: `{detected_topic_id}`\n\n"
                f"Reply with:\n"
                f"**1** — 🌐 Mirror **ALL Topics** from the source group (Recommended)\n"
                f"**2** — 🎯 Mirror **ONLY Topic `{detected_topic_id}`**\n\n"
                f"Send `/cancel` to abort.",
                timeout=180
            )
            if prompt_3.text == "/cancel":
                await app.send_message(user_id, "❌ Operation cancelled.")
                return
            if prompt_3.text.strip() == "2":
                mirror_all_topics = False
        except Exception:
            mirror_all_topics = True

    cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🛑 Cancel Mirroring", callback_data=f"tmirror_cancel_{user_id}")]])

    status_msg = await app.send_message(
        user_id,
        "🔄 **Initializing Userbot Session & Verifying Group Access...**",
        reply_markup=cancel_btn
    )

    userbot, is_temp_userbot = await get_working_userbot(user_id)
    if not userbot:
        await status_msg.edit(
            "❌ **No working userbot session available!**\n\n"
            "Please use `/login` in the bot to login your Telegram account session so the bot can access private source groups."
        )
        return

    active_mirrors[user_id] = True

    try:
        # Resolve source chat
        try:
            src_chat = await userbot.get_chat(src_chat_id)
            src_title = src_chat.title or str(src_chat_id)
        except Exception as e:
            await status_msg.edit(
                f"❌ **Could not access source group (`{src_chat_id}`):**\n`{e}`\n\n"
                f"Make sure your logged-in userbot account is a **member** of this group!"
            )
            return

        # Resolve target chat
        try:
            tgt_chat = await app.get_chat(tgt_chat_id)
            tgt_title = tgt_chat.title or str(tgt_chat_id)
        except Exception as e:
            await status_msg.edit(
                f"❌ **Could not access target group (`{tgt_chat_id}`):**\n`{e}`\n\n"
                f"Make sure the bot is an **Admin** in the target group!"
            )
            return

        # Ensure Topics / Forum is enabled in Target Supergroup
        try:
            await app.invoke(raw.functions.channels.ToggleForum(
                channel=await app.resolve_peer(tgt_chat_id),
                enabled=True,
                tabs=False
            ))
        except Exception as tf_err:
            print(f"[TopicMirror] ToggleForum notice: {tf_err}")

        await status_msg.edit(
            f"🔍 **Phase 1: Scanning Source Topics & Pre-Creating Target Topics...**\n\n"
            f"📤 **Source:** `{src_title}`\n"
            f"📥 **Target:** `{tgt_title}`",
            reply_markup=cancel_btn
        )

        # -------------------------------------------------------------
        # PHASE 1: DISCOVER ALL SOURCE TOPICS & PRE-CREATE IN TARGET
        # -------------------------------------------------------------
        source_topics = []  # list of dicts: {"id": int, "title": str, "icon_color": int, "icon_emoji_id": int}
        
        # Discover source topics
        try:
            async for forum_topic in userbot.get_forum_topics(src_chat_id):
                source_topics.append({
                    "id": forum_topic.message_thread_id,
                    "title": forum_topic.title,
                    "icon_color": getattr(forum_topic, "icon_color", None),
                    "icon_emoji_id": getattr(forum_topic, "icon_emoji_id", None)
                })
        except Exception as scan_err:
            print(f"[TopicMirror] Pyrogram get_forum_topics scan fallback: {scan_err}")
            # Raw RPC fallback
            try:
                peer = await userbot.resolve_peer(src_chat_id)
                res = await userbot.invoke(raw.functions.messages.GetForumTopics(
                    peer=peer,
                    offset_date=0,
                    offset_id=0,
                    offset_topic=0,
                    limit=100
                ))
                for t in getattr(res, "topics", []):
                    source_topics.append({
                        "id": t.id,
                        "title": t.title,
                        "icon_color": getattr(t, "icon_color", None),
                        "icon_emoji_id": getattr(t, "icon_emoji_id", None)
                    })
            except Exception as rpc_err:
                print(f"[TopicMirror] Raw RPC GetForumTopics failed: {rpc_err}")

        # If only mirroring a specific topic
        if not mirror_all_topics and detected_topic_id:
            source_topics = [t for t in source_topics if t["id"] == detected_topic_id]
            if not source_topics:
                # If not detected via list, create placeholder entry
                source_topics = [{"id": detected_topic_id, "title": f"Topic {detected_topic_id}", "icon_color": None, "icon_emoji_id": None}]

        # If source has no topics or regular group
        if not source_topics:
            if detected_topic_id:
                source_topics = [{"id": detected_topic_id, "title": f"Topic {detected_topic_id}", "icon_color": None, "icon_emoji_id": None}]
            else:
                source_topics = [{"id": 1, "title": "General", "icon_color": None, "icon_emoji_id": None}]

        # Get existing topics in target supergroup to avoid duplicates
        target_existing_topics = {}  # lowercase title -> message_thread_id
        try:
            async for tgt_topic in app.get_forum_topics(tgt_chat_id):
                target_existing_topics[tgt_topic.title.strip().lower()] = tgt_topic.message_thread_id
        except Exception as tgt_scan_err:
            print(f"[TopicMirror] Could not scan existing target topics: {tgt_scan_err}")

        # Map each source topic to target topic (create if missing)
        topic_map = {}  # src_topic_id -> tgt_topic_id
        topic_names = {} # src_topic_id -> title

        for st in source_topics:
            st_id = st["id"]
            st_title = st["title"].strip()
            topic_names[st_id] = st_title

            # General topic (id 1) always maps to target General topic (1 or None)
            if st_id == 1 or st_title.lower() == "general":
                topic_map[st_id] = 1
                continue

            # Check if topic already exists in target
            lower_title = st_title.lower()
            if lower_title in target_existing_topics:
                topic_map[st_id] = target_existing_topics[lower_title]
                continue

            # Create topic in target supergroup
            new_tgt_topic_id = None
            try:
                created = await app.create_forum_topic(
                    chat_id=tgt_chat_id,
                    title=st_title,
                    icon_color=st.get("icon_color"),
                    icon_emoji_id=st.get("icon_emoji_id")
                )
                new_tgt_topic_id = created.message_thread_id
                target_existing_topics[lower_title] = new_tgt_topic_id
            except Exception as create_err:
                print(f"[TopicMirror] High-level create topic failed for '{st_title}': {create_err}. Trying raw RPC...")
                try:
                    peer = await app.resolve_peer(tgt_chat_id)
                    res = await app.invoke(raw.functions.messages.CreateForumTopic(
                        peer=peer,
                        title=st_title,
                        random_id=random.randint(1000000, 9999999)
                    ))
                    # Extract created topic id from updates
                    for upd in getattr(res, "updates", []):
                        if hasattr(upd, "message_thread_id"):
                            new_tgt_topic_id = upd.message_thread_id
                            break
                        elif hasattr(upd, "id"):
                            new_tgt_topic_id = upd.id
                            break
                    if new_tgt_topic_id:
                        target_existing_topics[lower_title] = new_tgt_topic_id
                except Exception as rpc_create_err:
                    print(f"[TopicMirror] Raw CreateForumTopic error for '{st_title}': {rpc_create_err}")

            topic_map[st_id] = new_tgt_topic_id if new_tgt_topic_id else 1
            await asyncio.sleep(0.5)  # slight delay to avoid flood on topic creations

        total_topics_count = len(topic_map)
        await status_msg.edit(
            f"✅ **Phase 1 Complete:** Discovered & Mapped `{total_topics_count}` Topics!\n\n"
            f"🚀 **Starting Phase 2:** Extracting & Mirroring messages topic-by-topic...\n\n"
            f"*(Click below or send `/cancel_mirror` at any time to stop)*",
            reply_markup=cancel_btn
        )
        await asyncio.sleep(2)

        # -------------------------------------------------------------
        # PHASE 2: EXTRACT & MIRROR MESSAGES TOPIC BY TOPIC
        # -------------------------------------------------------------
        overall_copied = 0
        overall_failed = 0
        topic_stats = {}  # src_topic_id -> {"copied": int, "failed": int, "title": str}

        current_topic_index = 0

        for src_topic_id, tgt_topic_id in topic_map.items():
            if not active_mirrors.get(user_id, False):
                break

            current_topic_index += 1
            topic_title = topic_names.get(src_topic_id, f"Topic {src_topic_id}")
            topic_stats[src_topic_id] = {"copied": 0, "failed": 0, "title": topic_title}

            # Fetch messages in this topic using enhanced topic thread resolution
            messages_to_copy = await fetch_all_messages_for_topic(userbot, src_chat_id, src_topic_id)
            total_msgs_in_topic = len(messages_to_copy)

            last_edit_time = time.time()

            for idx, msg in enumerate(messages_to_copy, 1):
                if not active_mirrors.get(user_id, False):
                    break

                # Skip service/action messages
                if getattr(msg, "service", False) or getattr(msg, "empty", False):
                    continue

                success, method = await transfer_single_message(
                    userbot=userbot,
                    app=app,
                    src_chat_id=src_chat_id,
                    tgt_chat_id=tgt_chat_id,
                    tgt_topic_id=tgt_topic_id if tgt_topic_id != 1 else None,
                    msg=msg,
                    user_id=user_id
                )

                if success:
                    overall_copied += 1
                    topic_stats[src_topic_id]["copied"] += 1
                else:
                    overall_failed += 1
                    topic_stats[src_topic_id]["failed"] += 1

                # Update status message every 4 seconds
                if time.time() - last_edit_time > 4:
                    last_edit_time = time.time()
                    percent = int((idx / total_msgs_in_topic) * 100) if total_msgs_in_topic > 0 else 0
                    bar_blocks = int(percent // 10)
                    progress_bar_str = "❤️" * bar_blocks + "🤍" * (10 - bar_blocks)
                    
                    status_text = (
                        f"⚡ **Topic Mirroring in Progress...**\n\n"
                        f"📁 **Active Topic [{current_topic_index}/{total_topics_count}]:** `{topic_title}`\n"
                        f"📊 **Topic Progress:** {progress_bar_str} `{percent}%` ({idx}/{total_msgs_in_topic})\n\n"
                        f"✅ **Total Copied:** `{overall_copied}`\n"
                        f"❌ **Total Failed:** `{overall_failed}`\n"
                        f"🛡️ **Protected Bypass:** Active\n\n"
                        f"*(Click below or send `/cancel_mirror` to abort)*"
                    )
                    try:
                        await status_msg.edit(status_text, reply_markup=cancel_btn)
                    except Exception:
                        pass

                await asyncio.sleep(0.3)

        # -------------------------------------------------------------
        # FINAL REPORT DASHBOARD
        # -------------------------------------------------------------
        breakdown_lines = []
        for tid, stat in topic_stats.items():
            breakdown_lines.append(f"• **{stat['title']}**: ✅ `{stat['copied']}` | ❌ `{stat['failed']}`")

        breakdown_text = "\n".join(breakdown_lines) if breakdown_lines else "No messages processed."
        status_label = "🛑 **Mirror Cancelled by User**" if not active_mirrors.get(user_id, True) else "🎉 **Mirror Complete!**"

        final_report = (
            f"{status_label}\n\n"
            f"📤 **From:** `{src_title}`\n"
            f"📥 **To:** `{tgt_title}`\n\n"
            f"📊 **Overall Stats:**\n"
            f"• **Topics Processed:** `{len(topic_stats)}/{total_topics_count}`\n"
            f"• **Total Copied:** ✅ `{overall_copied}`\n"
            f"• **Total Failed:** ❌ `{overall_failed}`\n\n"
            f"📂 **Per-Topic Breakdown:**\n"
            f"{breakdown_text}\n\n"
            f"**__Pwrd by CHOSEN ONE ⚝__**"
        )

        try:
            await status_msg.edit(final_report)
        except Exception:
            await app.send_message(user_id, final_report)

    except Exception as general_err:
        print(f"[TopicMirror] General error: {general_err}")
        try:
            await status_msg.edit(f"❌ **Topic Mirror Failed with Error:**\n`{general_err}`")
        except Exception:
            pass
    finally:
        active_mirrors.pop(user_id, None)
        if is_temp_userbot and userbot:
            try:
                await userbot.stop()
            except Exception:
                pass
