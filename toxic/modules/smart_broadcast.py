# ---------------------------------------------------
# File Name: smart_broadcast.py
# Description: Advanced High-Speed Smart Auto-Broadcast & Real-Time Deletion Engine
# Features:
#   - Concurrent High-Speed Worker Pool (Blazing Fast parallel dispatch)
#   - Independent Sub-Second Real-Time Deletion Worker (Never blocked by broadcast rounds)
#   - Instant in-memory deletion timers for immediate deletion on time
#   - 3-Tier Channel & Group Deletion Engine (High-Level + Raw RPC channels.DeleteMessages)
#   - Dual-Client Execution (Bot App + Connected Userbots)
#   - Comprehensive Auto-Discovery across all userbots, MongoDB collections & dialogs
#   - Zero False Deletions: Channels & Groups are NEVER purged on temporary MTProto errors
#   - Bulk Addition Support for Channels & Groups (/addchannels, /addgroups)
#   - Full Target Routing (Groups, Channels, DMs) & Real-Time Live UI Progress Tracker
# ---------------------------------------------------

import asyncio
import datetime
import time
import re
from pyrogram import filters, Client, types, raw
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMemberUpdated
from pyrogram.enums import ChatType, ChatMemberStatus, ParseMode
from pyrogram.errors import FloodWait, RPCError

from toxic import app
from config import OWNER_ID, MONGO_DB
from motor.motor_asyncio import AsyncIOMotorClient

# ─── Independent MongoDB Collections ───
_mongo_cli = AsyncIOMotorClient(MONGO_DB)
_sb_db = _mongo_cli.smart_broadcast_system
_dest_col = _sb_db.destinations
_cfg_col = _sb_db.config
_del_col = _sb_db.deletions

def is_owner(user_id: int) -> bool:
    if not user_id:
        return False
    from toxic.core.mongo.db import is_admin_or_owner
    return is_admin_or_owner(user_id)

def extract_message_id(sent_msg):
    """Safely extracts integer message ID from any Pyrogram response format."""
    if not sent_msg:
        return None
    if isinstance(sent_msg, int):
        return sent_msg
    if isinstance(sent_msg, list) and len(sent_msg) > 0:
        return extract_message_id(sent_msg[0])
    return getattr(sent_msg, "id", None) or getattr(sent_msg, "message_id", None)

# ─── Database Helpers ───
async def get_sb_config():
    cfg = await _cfg_col.find_one({"_id": "global_config"})
    if not cfg:
        default_cfg = {
            "_id": "global_config",
            "is_active": False,
            "enable_groups": True,
            "enable_channels": True,
            "enable_dms": True,
            "disable_web_page_preview": True,
            "interval_mins": 30,
            "delete_after_seconds": 300,  # 5 mins default
            "max_runs": 0,
            "run_count": 0,
            "fast_forward_mode": True,
            "content_type": "text",
            "message_text": "⚡ **Welcome to Smart Auto-Broadcast!**\n\n> Configure your settings using `/smartbroadcast`.",
            "source_chat_id": None,
            "source_msg_id": None,
            "last_run": None,
            "last_broadcast_round": 0
        }
        await _cfg_col.insert_one(default_cfg)
        return default_cfg
    return cfg

async def update_sb_config(update_dict: dict):
    await _cfg_col.update_one({"_id": "global_config"}, {"$set": update_dict}, upsert=True)

async def add_sb_destination(chat_id: int, title: str, chat_type: str):
    try:
        cid = int(chat_id)
        if cid > 0:
            actual_type = "private"
        else:
            if chat_type in ("channel", "group", "supergroup"):
                actual_type = chat_type
            else:
                actual_type = "channel" if str(cid).startswith("-100") else "supergroup"

        existing = await _dest_col.find_one({"chat_id": cid})
        # If already known as a channel, don't overwrite with generic supergroup
        if existing and existing.get("chat_type") == "channel" and actual_type in ("group", "supergroup"):
            actual_type = "channel"

        await _dest_col.update_one(
            {"chat_id": cid},
            {"$set": {"chat_id": cid, "title": title, "chat_type": actual_type, "updated_at": datetime.datetime.now()}},
            upsert=True
        )
    except Exception as e:
        print(f"[SmartBroadcast DB] Error adding chat {chat_id}: {e}")

async def remove_sb_destination(chat_id: int):
    try:
        await _dest_col.delete_one({"chat_id": int(chat_id)})
    except Exception as e:
        print(f"[SmartBroadcast DB] Error removing chat {chat_id}: {e}")

async def sync_all_broadcast_destinations():
    """
    Auto-discovers and syncs all destinations from:
    1. Active userbots (pro_clients, owner userbots, connected userbots) via get_dialogs()
    2. All joined chats, channels, forward targets, mirror sessions from MongoDB (db.get_all_broadcast_chats)
    3. Registered users in MongoDB (users_db.get_all_registered_users)
    Guarantees:
      - NEVER deletes stored channels or groups on temporary MTProto/peer_id errors.
      - Discovers all channels & groups where bot or userbots are members/admins.
    """
    try:
        print("[SmartBroadcast Sync] Starting comprehensive channels & groups discovery...")

        # Fix any corrupted chat_type records in MongoDB
        try:
            await _dest_col.update_many(
                {"chat_id": {"$gt": 0}, "chat_type": {"$ne": "private"}},
                {"$set": {"chat_type": "private"}}
            )
            await _dest_col.update_many(
                {"chat_id": {"$lt": 0}, "chat_type": "private"},
                {"$set": {"chat_type": "supergroup"}}
            )
        except Exception:
            pass

        from toxic.core.mongo.db import add_joined_chat, get_all_broadcast_chats, get_auth_channels, get_log_channel

        # 1. Discover dialogs from all active userbots & owner userbots (Telethon & Pyrogram)
        userbots_to_scan = []
        try:
            from toxic.core.mongo.db import get_all_active_userbots
            ubs = await get_all_active_userbots()
            for ub in (ubs or []):
                if ub and ub not in userbots_to_scan:
                    userbots_to_scan.append(ub)
        except Exception:
            pass

        try:
            from toxic import pro_clients
            for pc in (pro_clients or []):
                if pc and pc not in userbots_to_scan:
                    userbots_to_scan.append(pc)
        except Exception:
            pass

        try:
            from toxic.core.userbot_manager import get_or_create_userbot
            owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
            for oid in owner_list:
                if not oid:
                    continue
                try:
                    ub = await get_or_create_userbot(int(oid))
                    if ub and ub not in userbots_to_scan:
                        userbots_to_scan.append(ub)
                except Exception:
                    pass
        except Exception:
            pass

        discovered_count = 0
        for ub in userbots_to_scan:
            try:
                if not getattr(ub, "is_connected", False):
                    try:
                        await ub.start()
                    except Exception:
                        continue
                async for dialog in ub.get_dialogs(limit=500):
                    chat = dialog.chat
                    if chat and chat.id < 0:
                        c_type = "channel" if chat.type == ChatType.CHANNEL else "supergroup"
                        title = chat.title or chat.username or f"Chat {chat.id}"
                        await add_sb_destination(chat.id, title, c_type)
                        await add_joined_chat(chat.id, title, chat_type=c_type)
                        discovered_count += 1
            except Exception as e:
                print(f"[SmartBroadcast Sync] Userbot scan notice: {e}")

        # 2. Gather auth channels & log channels
        auth_channels_list = set()
        try:
            for ac in (await get_auth_channels() or []):
                try:
                    auth_channels_list.add(int(ac))
                except Exception:
                    pass
            log_ch = await get_log_channel()
            if log_ch:
                try:
                    auth_channels_list.add(int(log_ch))
                except Exception:
                    pass
        except Exception:
            pass

        for ac_id in auth_channels_list:
            await add_sb_destination(ac_id, f"Auth/Log Channel {ac_id}", "channel")
            await add_joined_chat(ac_id, f"Auth/Log Channel {ac_id}", chat_type="channel")

        # 3. Aggregate all chats stored across all MongoDB collections
        all_chats = await get_all_broadcast_chats()
        for j in all_chats:
            cid = j.get("chat_id")
            if not cid or cid >= 0:
                continue
            try:
                cid = int(cid)
            except Exception:
                continue

            title = j.get("title", f"Chat {cid}")
            c_type = j.get("chat_type")

            if cid in auth_channels_list:
                c_type = "channel"

            # Check existing destination in _dest_col to preserve already identified channel type
            if not c_type:
                existing_doc = await _dest_col.find_one({"chat_id": cid})
                if existing_doc and existing_doc.get("chat_type"):
                    c_type = existing_doc["chat_type"]

            # If still unknown, attempt resolving via bot WITHOUT DELETING on error
            if not c_type:
                try:
                    chat_obj = await app.get_chat(cid)
                    if chat_obj.type == ChatType.CHANNEL:
                        c_type = "channel"
                    elif chat_obj.type in (ChatType.SUPERGROUP, ChatType.GROUP):
                        c_type = "supergroup"
                    if chat_obj.title:
                        title = chat_obj.title
                except Exception:
                    # Keep safe fallback - NEVER delete from DB!
                    c_type = "channel" if str(cid).startswith("-100") else "supergroup"

            await add_sb_destination(cid, title, c_type)
            await add_joined_chat(cid, title, chat_type=c_type)

        # 4. Sync registered users from users_db.get_all_registered_users()
        try:
            from toxic.core.mongo.users_db import get_all_registered_users
            users = await get_all_registered_users()
            registered_uids = set()
            for u in users:
                if isinstance(u, int) or (isinstance(u, str) and u.isdigit()):
                    uid = int(u)
                    if uid > 0:
                        registered_uids.add(uid)
                        await add_sb_destination(uid, f"User {uid}", "private")
                await asyncio.sleep(0.005)

            # Clean up only non-registered private contacts from destinations collection
            await _dest_col.delete_many({
                "chat_type": "private",
                "chat_id": {"$nin": list(registered_uids)}
            })
        except Exception as u_err:
            print(f"[SmartBroadcast Sync] User sync notice: {u_err}")

        total_synced = await _dest_col.count_documents({})
        print(f"[SmartBroadcast Sync] Synchronization finished cleanly. Total reachable destinations: {total_synced}")

    except Exception as err:
        print(f"[SmartBroadcast Sync] Sync error: {err}")

_last_dest_sync_time = 0

async def get_sb_destinations(cfg: dict = None):
    global _last_dest_sync_time
    if cfg is None:
        cfg = await get_sb_config()

    # Non-blocking background sync (throttled to once every 10 minutes)
    now = time.time()
    if now - _last_dest_sync_time > 600:
        _last_dest_sync_time = now
        asyncio.create_task(sync_all_broadcast_destinations())

    enable_groups = bool(cfg.get("enable_groups", True))
    enable_channels = bool(cfg.get("enable_channels", True))
    enable_dms = bool(cfg.get("enable_dms", True))

    if not enable_groups and not enable_channels and not enable_dms:
        return []

    dest_list = []
    seen_cids = set()
    try:
        async for doc in _dest_col.find({}):
            cid = doc.get("chat_id")
            if not cid or cid in seen_cids:
                continue

            try:
                cid = int(cid)
            except Exception:
                continue

            ctype = doc.get("chat_type", "")
            if cid > 0:
                # Private User DM — STRICT check
                if enable_dms:
                    seen_cids.add(cid)
                    doc["chat_type"] = "private"
                    dest_list.append(doc)
            else:
                # Group or Channel (cid < 0)
                if ctype == "channel":
                    if enable_channels:
                        seen_cids.add(cid)
                        dest_list.append(doc)
                elif ctype in ("group", "supergroup"):
                    if enable_groups:
                        seen_cids.add(cid)
                        dest_list.append(doc)
                else:
                    if str(cid).startswith("-100"):
                        if enable_channels or enable_groups:
                            seen_cids.add(cid)
                            dest_list.append(doc)
                    elif enable_groups:
                        seen_cids.add(cid)
                        dest_list.append(doc)
    except Exception as e:
        print(f"[SmartBroadcast DB] Error fetching destinations: {e}")
    return dest_list

async def add_sb_deletion(chat_id: int, message_id: int, delete_at: datetime.datetime, title: str = "Chat", round_num: int = 1):
    try:
        await _del_col.insert_one({
            "chat_id": chat_id,
            "message_id": message_id,
            "delete_at": delete_at,
            "title": title,
            "round_num": round_num
        })
    except Exception as e:
        print(f"[SmartBroadcast DB] Error adding deletion entry: {e}")

async def get_pending_sb_deletions():
    pending = []
    now = datetime.datetime.now()
    try:
        async for doc in _del_col.find({"delete_at": {"$lte": now}}):
            pending.append(doc)
    except Exception as e:
        print(f"[SmartBroadcast DB] Error fetching deletions: {e}")
    return pending

async def remove_sb_deletion(deletion_id):
    try:
        await _del_col.delete_one({"_id": deletion_id})
    except Exception as e:
        print(f"[SmartBroadcast DB] Error removing deletion entry: {e}")

# ─── Instant Sub-Second In-Memory Deletion Task ───
async def in_memory_auto_delete(chat_id: int, message_id: int, delay_seconds: int):
    """
    Executes precise message deletion the exact second the timer expires,
    independent of whether broadcast sending is still ongoing.
    """
    try:
        if delay_seconds <= 0:
            return
        await asyncio.sleep(delay_seconds)
        del_ok, _ = await delete_single_sb_message(chat_id, message_id)
        if del_ok:
            await _del_col.delete_one({"chat_id": chat_id, "message_id": message_id})
    except Exception as e:
        print(f"[SmartBroadcast] In-memory auto-delete exception: {e}")

# ─── 3-Tier Multi-Client Deletion Engine ───
async def delete_single_sb_message(chat_id: int, message_id: int, userbot_client=None):
    """
    STRICT BOT-FIRST DELETION ENGINE:
    Always uses the Bot (app) to delete its sent broadcast message first.
    Admin or userbot accounts are strictly reserved as a fallback ONLY if the Bot
    lacks permissions in that channel/group.
    Private DMs (chat_id > 0) are exclusively handled by the Bot and never touch user accounts.
    """
    try:
        chat_id = int(chat_id)
        message_id = int(message_id)
    except Exception:
        return False, "Invalid ID"

    # ──── STEP 1: STRICT BOT DELETION (Primary) ────
    # 1A. Standard delete_messages via Bot with revoke=True
    try:
        res = await app.delete_messages(chat_id, message_id, revoke=True)
        if res:
            return True, "Bot High-Level Delete (Revoke)"
    except FloodWait as fw:
        await asyncio.sleep(fw.value + 1)
        try:
            res = await app.delete_messages(chat_id, message_id, revoke=True)
            if res:
                return True, "Bot High-Level Delete (Post-Wait)"
        except Exception:
            pass
    except Exception:
        pass

    # 1B. List-based delete_messages via Bot (Channels & Supergroups)
    try:
        res = await app.delete_messages(chat_id, [message_id])
        if res:
            return True, "Bot High-Level Delete (List)"
    except Exception:
        pass

    # 1C. Raw MTProto RPC via Bot
    if chat_id < 0:
        try:
            peer = await app.resolve_peer(chat_id)
            if isinstance(peer, (raw.types.InputPeerChannel, raw.types.InputChannel)):
                chan_input = raw.types.InputChannel(channel_id=peer.channel_id, access_hash=peer.access_hash)
                await app.invoke(raw.functions.channels.DeleteMessages(
                    channel=chan_input,
                    id=[message_id]
                ))
                return True, "Bot Raw RPC Channel Delete"
            elif isinstance(peer, (raw.types.InputPeerChat, raw.types.InputChat)):
                await app.invoke(raw.functions.messages.DeleteMessages(
                    id=[message_id],
                    revoke=True
                ))
                return True, "Bot Raw RPC Group Delete"
        except Exception:
            pass
    else:
        # Private user DM - bot directly invokes messages.DeleteMessages
        try:
            await app.invoke(raw.functions.messages.DeleteMessages(
                id=[message_id],
                revoke=True
            ))
            return True, "Bot Raw RPC DM Delete"
        except Exception:
            pass

    # For Private DMs (chat_id > 0), user accounts cannot delete bot messages, stop here
    if chat_id > 0:
        return False, "Bot DM delete failed"

    # ──── STEP 2: FALLBACK TO USERBOT ONLY IF BOT FAILED (Groups/Channels Only) ────
    fallback_clients = []
    if userbot_client and getattr(userbot_client, "is_connected", False):
        fallback_clients.append(userbot_client)

    try:
        from toxic.core.mongo.db import get_all_active_userbots
        active_ubs = await get_all_active_userbots()
        for ub in (active_ubs or []):
            if ub and ub not in fallback_clients and getattr(ub, "is_connected", False):
                fallback_clients.append(ub)
    except Exception:
        pass

    for ub in fallback_clients:
        try:
            res = await ub.delete_messages(chat_id, [message_id])
            if res:
                return True, "Fallback Userbot List Delete"
        except Exception:
            pass

        try:
            peer = await ub.resolve_peer(chat_id)
            if isinstance(peer, (raw.types.InputPeerChannel, raw.types.InputChannel)):
                chan_input = raw.types.InputChannel(channel_id=peer.channel_id, access_hash=peer.access_hash)
                await ub.invoke(raw.functions.channels.DeleteMessages(
                    channel=chan_input,
                    id=[message_id]
                ))
                return True, "Fallback Userbot Raw RPC Delete"
        except Exception:
            pass

    return False, "Failed"

async def delete_all_active_sb_messages(filter_query: dict = None):
    """Deletes active broadcast messages matching query using parallel workers."""
    deleted_ok = 0
    failed_chats = []

    userbot_client = None
    try:
        from toxic.core.mongo.db import get_all_active_userbots
        ubs = await get_all_active_userbots()
        if ubs:
            userbot_client = ubs[0]
    except Exception:
        pass

    query = filter_query if filter_query else {}
    docs_to_delete = []
    try:
        async for doc in _del_col.find(query):
            docs_to_delete.append(doc)
    except Exception as e:
        print(f"[SmartBroadcast] Deletion query error: {e}")

    if not docs_to_delete:
        return 0, []

    sem = asyncio.Semaphore(15)
    lock = asyncio.Lock()

    async def _worker_delete(doc):
        nonlocal deleted_ok
        cid = doc["chat_id"]
        mid = doc["message_id"]
        title = doc.get("title", f"Chat `{cid}`")

        async with sem:
            success, _ = await delete_single_sb_message(cid, mid, userbot_client)
            async with lock:
                if success:
                    deleted_ok += 1
                    await _del_col.delete_one({"_id": doc["_id"]})
                else:
                    retries = doc.get("retries", 0) + 1
                    if retries >= 3:
                        failed_chats.append(f"• **{title}** (`{cid}`)")
                        await _del_col.delete_one({"_id": doc["_id"]})
                    else:
                        await _del_col.update_one({"_id": doc["_id"]}, {"$set": {"retries": retries}})

    await asyncio.gather(*(_worker_delete(d) for d in docs_to_delete))
    return deleted_ok, failed_chats

# ─── Formatted Time Helpers ───
def format_time_duration(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "Disabled ❌"
    if seconds < 60:
        return f"{seconds} Seconds ⚡"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins} Minutes ⏱️"
    hours = seconds // 3600
    return f"{hours} Hours ⏳"

# ─── Dedicated Independent Deletion Background Worker ───
async def smart_broadcast_dedicated_deletion_worker():
    """
    Independent 24/7 background worker for message auto-deletions.
    Runs every 2 seconds completely decoupled from broadcast sending.
    """
    while True:
        try:
            pending_dels = await get_pending_sb_deletions()
            if pending_dels:
                userbot_client = None
                owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
                del_success_count = 0
                del_fail_list = []

                # Fetch active userbot safely without stopping it
                try:
                    from toxic.core.userbot_manager import get_active_userbot_sync
                    for oid in owner_list:
                        if oid:
                            userbot_client = get_active_userbot_sync(int(oid))
                            if userbot_client and getattr(userbot_client, "is_connected", False):
                                break
                except Exception:
                    pass

                sem = asyncio.Semaphore(15)
                lock = asyncio.Lock()

                async def _proc_del(item):
                    nonlocal del_success_count
                    c_id = item["chat_id"]
                    m_id = item["message_id"]
                    c_title = item.get("title", f"Chat `{c_id}`")

                    async with sem:
                        del_success, del_method = await delete_single_sb_message(c_id, m_id, userbot_client)
                        async with lock:
                            if del_success:
                                del_success_count += 1
                                await remove_sb_deletion(item["_id"])
                            else:
                                retries = item.get("retries", 0) + 1
                                if retries >= 3:
                                    del_fail_list.append(f"• **{c_title}** (`{c_id}`)")
                                    await remove_sb_deletion(item["_id"])
                                else:
                                    next_try = datetime.datetime.now() + datetime.timedelta(seconds=15)
                                    await _del_col.update_one(
                                        {"_id": item["_id"]},
                                        {"$set": {"retries": retries, "delete_at": next_try}}
                                    )

                await asyncio.gather(*(_proc_del(item) for item in pending_dels))

                if del_fail_list:
                    fail_summary = "\n".join(del_fail_list[:10])
                    if len(del_fail_list) > 10:
                        fail_summary += f"\n... and {len(del_fail_list) - 10} more."

                    del_report = (
                        f"⚠️ **[AUTO-DELETE SCHEDULED REPORT]** ⚠️\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"✅ **Deleted Successfully:** `{del_success_count}` chats\n"
                        f"❌ **Failed to Delete:** `{len(del_fail_list)}` chats\n\n"
                        f"📌 **Failed Deletion Details:**\n"
                        f"{fail_summary}\n\n"
                        f"👉 *Click the button below to force delete manually:*",
                    )
                    for oid in owner_list:
                        try:
                            await app.send_message(int(oid), del_report[0], reply_markup=get_sb_report_keyboard())
                        except Exception:
                            pass
        except Exception as e:
            print(f"[SmartBroadcast Deletion Worker Error]: {e}")

        await asyncio.sleep(2)

# ─── High-Speed Concurrent Broadcast Execution Engine ───
async def execute_smart_broadcast_round(manual: bool = False, status_msg: Message = None):
    cfg = await get_sb_config()
    delete_seconds = cfg.get("delete_after_seconds", 0)
    fast_forward = cfg.get("fast_forward_mode", True)
    disable_preview = cfg.get("disable_web_page_preview", True)
    run_count = cfg.get("run_count", 0)
    
    src_chat_id = cfg.get("source_chat_id")
    src_msg_id = cfg.get("source_msg_id")
    msg_text = cfg.get("message_text")

    destinations = await get_sb_destinations(cfg)
    if not destinations:
        return 0, 0, [], "No target destinations enabled or found in database."

    total_dests = len(destinations)
    if status_msg:
        try:
            await status_msg.edit_text(f"🚀 **Starting High-Speed Broadcast to `{total_dests}` chats...**")
        except Exception:
            pass

    # Load all available userbots (from STRINGS and MongoDB sessions)
    active_userbots = []
    try:
        from toxic.core.mongo.db import get_all_active_userbots
        active_userbots = await get_all_active_userbots()
    except Exception as e:
        print(f"[SmartBroadcast] Failed to load userbots: {e}")

    clients_pool = [app] + [ub for ub in active_userbots if getattr(ub, "is_connected", False)]

    # 15 parallel workers for high-speed delivery without exceeding Telegram flood thresholds
    sem = asyncio.Semaphore(15)
    lock = asyncio.Lock()

    sent_count = 0
    failed_count = 0
    processed_count = 0
    failed_details = []
    last_ui_update = 0
    current_chat_title = ["Starting..."]

    async def _send_worker(item):
        nonlocal sent_count, failed_count, processed_count, last_ui_update
        cid = item["chat_id"]
        title = item.get("title", f"Chat `{cid}`")
        sent_msg = None
        sent_success = False
        last_err_text = "Could not send broadcast"

        async with sem:
            current_chat_title[0] = title
            clients_to_try = [app] if cid > 0 else clients_pool

            for client in clients_to_try:
                if not getattr(client, "is_connected", True):
                    continue
                try:
                    if src_chat_id and src_msg_id:
                        if fast_forward:
                            try:
                                sent_msg = await client.copy_message(chat_id=cid, from_chat_id=src_chat_id, message_id=src_msg_id)
                            except Exception:
                                try:
                                    sent_msg = await client.forward_messages(chat_id=cid, from_chat_id=src_chat_id, message_ids=src_msg_id)
                                except Exception:
                                    sent_msg = await client.copy_message(chat_id=cid, from_chat_id=src_chat_id, message_id=src_msg_id, message_thread_id=1)
                        else:
                            try:
                                sent_msg = await client.forward_messages(chat_id=cid, from_chat_id=src_chat_id, message_ids=src_msg_id)
                            except Exception:
                                try:
                                    sent_msg = await client.copy_message(chat_id=cid, from_chat_id=src_chat_id, message_id=src_msg_id)
                                except Exception:
                                    sent_msg = await client.forward_messages(chat_id=cid, from_chat_id=src_chat_id, message_ids=src_msg_id)
                    elif msg_text:
                        html_text = None
                        try:
                            from toxic.core.func import format_caption_to_html
                            html_text = format_caption_to_html(msg_text)
                        except Exception:
                            pass
                        try:
                            sent_msg = await client.send_message(
                                cid, 
                                html_text or msg_text, 
                                disable_web_page_preview=disable_preview
                            )
                        except Exception:
                            try:
                                sent_msg = await client.send_message(
                                    cid,
                                    html_text or msg_text,
                                    disable_web_page_preview=disable_preview,
                                    message_thread_id=1
                                )
                            except Exception:
                                sent_msg = await client.send_message(
                                    cid,
                                    html_text or msg_text,
                                    disable_web_page_preview=disable_preview,
                                    reply_to_message_id=1
                                )

                    msg_id = extract_message_id(sent_msg)
                    if msg_id:
                        sent_success = True
                        if delete_seconds > 0:
                            del_at = datetime.datetime.now() + datetime.timedelta(seconds=delete_seconds)
                            await add_sb_deletion(cid, msg_id, del_at, title=title, round_num=run_count)
                            # Instant in-memory deletion task for exact second precision
                            asyncio.create_task(in_memory_auto_delete(cid, msg_id, delete_seconds))
                        break

                except FloodWait as fw:
                    await asyncio.sleep(fw.value + 1)
                    try:
                        if src_chat_id and src_msg_id:
                            sent_msg = await client.copy_message(chat_id=cid, from_chat_id=src_chat_id, message_id=src_msg_id)
                        elif msg_text:
                            sent_msg = await client.send_message(cid, msg_text, disable_web_page_preview=disable_preview)
                        msg_id = extract_message_id(sent_msg)
                        if msg_id:
                            sent_success = True
                            if delete_seconds > 0:
                                del_at = datetime.datetime.now() + datetime.timedelta(seconds=delete_seconds)
                                await add_sb_deletion(cid, msg_id, del_at, title=title, round_num=run_count)
                                asyncio.create_task(in_memory_auto_delete(cid, msg_id, delete_seconds))
                            break
                    except Exception as retry_err:
                        last_err_text = str(retry_err)
                except Exception as err:
                    last_err_text = str(err)
                    continue

            async with lock:
                processed_count += 1
                if sent_success:
                    sent_count += 1
                else:
                    failed_count += 1
                    err_lower = last_err_text.lower()
                    # Only remove if definitively a deactivated/blocked private user
                    if cid > 0 and any(k in err_lower for k in ["user_is_blocked", "user_deactivated", "input_user_deactivated", "bot was blocked"]):
                        try:
                            await remove_sb_destination(cid)
                        except Exception:
                            pass
                    failed_details.append(f"• **{title}** (`{cid}`): {last_err_text}")

                # Live progress updates to UI (throttled every 2 seconds or at completion)
                now_t = time.time()
                if status_msg and (now_t - last_ui_update >= 2.0 or processed_count == total_dests):
                    last_ui_update = now_t
                    percent = int((processed_count / total_dests) * 100)
                    try:
                        await status_msg.edit_text(
                            f"⚡ **Smart Broadcast in Progress (High Speed)...**\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                            f"• **Progress:** `{processed_count}/{total_dests}` chats ({percent}%)\n"
                            f"• **Delivered:** `{sent_count}` ✅\n"
                            f"• **Failed / Skipped:** `{failed_count}` ❌\n"
                            f"• **Current Chat:** **{current_chat_title[0]}**\n\n"
                            f"🚀 *High-speed parallel dispatch with real-time auto-delete active...*"
                        )
                    except Exception:
                        pass

            await asyncio.sleep(0.03)

    # Launch all workers in parallel
    await asyncio.gather(*(_send_worker(item) for item in destinations))

    await update_sb_config({"last_broadcast_round": run_count})
    return sent_count, failed_count, failed_details, None

# ─── UI Keyboard Builders ───
def get_sb_main_keyboard(cfg: dict):
    is_active = cfg.get("is_active", False)
    interval_m = cfg.get("interval_mins", 30)
    del_s = cfg.get("delete_after_seconds", 0)
    max_r = cfg.get("max_runs", 0)
    fast_f = cfg.get("fast_forward_mode", True)
    no_preview = cfg.get("disable_web_page_preview", True)

    eg = cfg.get("enable_groups", True)
    ec = cfg.get("enable_channels", True)
    ed = cfg.get("enable_dms", True)

    del_str = format_time_duration(del_s)
    max_r_str = f"{max_r} Rounds" if max_r > 0 else "Infinite ♾️"
    mode_str = "Fast Copy ⚡" if fast_f else "Forward Tag ⏩"
    preview_str = "OFF ❌" if no_preview else "ON 🌐"

    buttons = [
        [
            InlineKeyboardButton(f"⚡ Status: {'ACTIVE ✅' if is_active else 'INACTIVE ❌'}", callback_data="sb_toggle_status"),
            InlineKeyboardButton(f"🔗 Link Preview: {preview_str}", callback_data="sb_toggle_preview")
        ],
        [
            InlineKeyboardButton(f"👥 Groups: {'ON ✅' if eg else 'OFF ❌'}", callback_data="sb_toggle_target_groups"),
            InlineKeyboardButton(f"📢 Channels: {'ON ✅' if ec else 'OFF ❌'}", callback_data="sb_toggle_target_channels"),
            InlineKeyboardButton(f"👤 DMs: {'ON ✅' if ed else 'OFF ❌'}", callback_data="sb_toggle_target_dms")
        ],
        [
            InlineKeyboardButton("👁️ Preview Broadcast Message", callback_data="sb_preview_msg")
        ],
        [
            InlineKeyboardButton("🛑 Stop Next Broadcast", callback_data="sb_stop_next"),
            InlineKeyboardButton("🗑️ Delete Last Broadcast Now", callback_data="sb_delete_last")
        ],
        [
            InlineKeyboardButton("📝 Set Payload / Reply", callback_data="sb_set_message"),
            InlineKeyboardButton(f"⏩ Mode: {mode_str}", callback_data="sb_toggle_mode")
        ],
        [
            InlineKeyboardButton(f"⏱️ Interval: {interval_m}m", callback_data="sb_set_interval"),
            InlineKeyboardButton(f"🗑️ Auto-Delete: {del_str}", callback_data="sb_set_delete_timer")
        ],
        [
            InlineKeyboardButton(f"🔢 Rounds Limit: {max_r_str}", callback_data="sb_set_max_runs"),
            InlineKeyboardButton("🔄 Reset Count", callback_data="sb_reset_count")
        ],
        [
            InlineKeyboardButton("🚀 Launch Broadcast Now", callback_data="sb_launch_now"),
            InlineKeyboardButton("🧹 Force Delete All Broadcasts", callback_data="sb_force_delete_all")
        ],
        [
            InlineKeyboardButton("📊 Destination Stats", callback_data="sb_view_stats"),
            InlineKeyboardButton("🔄 Sync Chats", callback_data="sb_sync_chats")
        ],
        [
            InlineKeyboardButton("❌ Close", callback_data="sb_close")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_sb_report_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛑 Stop Next Broadcast", callback_data="sb_stop_next"),
            InlineKeyboardButton("🗑️ Delete Last Broadcast Now", callback_data="sb_delete_last")
        ],
        [
            InlineKeyboardButton("🧹 Force Delete All Broadcasts", callback_data="sb_force_delete_all"),
            InlineKeyboardButton("🎛️ Control Panel", callback_data="sb_back")
        ]
    ])

def get_sb_interval_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("5 Mins", callback_data="sb_int_5"), InlineKeyboardButton("15 Mins", callback_data="sb_int_15"), InlineKeyboardButton("30 Mins", callback_data="sb_int_30")],
        [InlineKeyboardButton("1 Hour", callback_data="sb_int_60"), InlineKeyboardButton("2 Hours", callback_data="sb_int_120"), InlineKeyboardButton("4 Hours", callback_data="sb_int_240")],
        [InlineKeyboardButton("12 Hours", callback_data="sb_int_720"), InlineKeyboardButton("24 Hours", callback_data="sb_int_1440")],
        [InlineKeyboardButton("✏️ Set Custom Minutes", callback_data="sb_int_custom")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="sb_back")]
    ])

def get_sb_delete_timer_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Disabled ❌ (Keep Messages)", callback_data="sb_del_0")],
        [InlineKeyboardButton("30 Secs", callback_data="sb_del_30"), InlineKeyboardButton("2 Mins", callback_data="sb_del_120"), InlineKeyboardButton("5 Mins", callback_data="sb_del_300")],
        [InlineKeyboardButton("10 Mins", callback_data="sb_del_600"), InlineKeyboardButton("30 Mins", callback_data="sb_del_1800"), InlineKeyboardButton("1 Hour", callback_data="sb_del_3600")],
        [InlineKeyboardButton("24 Hours", callback_data="sb_del_86400")],
        [InlineKeyboardButton("✏️ Set Custom Seconds / Minutes", callback_data="sb_del_custom")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="sb_back")]
    ])

def get_sb_rounds_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Infinite ♾️ (No Limit)", callback_data="sb_rnd_0")],
        [InlineKeyboardButton("1 Round (Single)", callback_data="sb_rnd_1"), InlineKeyboardButton("3 Rounds", callback_data="sb_rnd_3"), InlineKeyboardButton("5 Rounds", callback_data="sb_rnd_5")],
        [InlineKeyboardButton("10 Rounds", callback_data="sb_rnd_10"), InlineKeyboardButton("20 Rounds", callback_data="sb_rnd_20"), InlineKeyboardButton("50 Rounds", callback_data="sb_rnd_50")],
        [InlineKeyboardButton("✏️ Set Custom Rounds Count", callback_data="sb_rnd_custom")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="sb_back")]
    ])

# ─── Main Menu Renderer ───
async def render_smart_broadcast_menu(client: Client, message_or_query):
    cfg = await get_sb_config()
    all_dests = await get_sb_destinations(cfg)
    
    all_stored = []
    try:
        async for doc in _dest_col.find({}):
            all_stored.append(doc)
    except Exception:
        pass

    groups_count = len([d for d in all_stored if int(d.get("chat_id", 0)) < 0 and d.get("chat_type") in ("group", "supergroup")])
    channels_count = len([d for d in all_stored if int(d.get("chat_id", 0)) < 0 and d.get("chat_type") == "channel"])
    dms_count = len([d for d in all_stored if int(d.get("chat_id", 0)) > 0])

    is_active = cfg.get("is_active", False)
    interval_m = cfg.get("interval_mins", 30)
    del_s = cfg.get("delete_after_seconds", 0)
    max_r = cfg.get("max_runs", 0)
    run_c = cfg.get("run_count", 0)
    fast_f = cfg.get("fast_forward_mode", True)
    no_preview = cfg.get("disable_web_page_preview", True)
    msg_text = cfg.get("message_text", "None")
    src_msg_id = cfg.get("source_msg_id")

    eg = cfg.get("enable_groups", True)
    ec = cfg.get("enable_channels", True)
    ed = cfg.get("enable_dms", True)

    del_str = format_time_duration(del_s)
    max_r_str = f"{max_r} Rounds" if max_r > 0 else "Infinite ♾️"
    mode_str = "Fast Copy (No Forward Tag) ⚡" if fast_f else "Standard Forward Tag ⏩"
    preview_str = "OFF ❌ (No Link Cards)" if no_preview else "ON 🌐 (Show Link Cards)"

    target_status = []
    if eg: target_status.append("Groups ✅")
    if ec: target_status.append("Channels ✅")
    if ed: target_status.append("DMs ✅")
    t_status_str = ", ".join(target_status) if target_status else "None ❌ (All Disabled)"

    preview_content = f"Reply Message ID: `{src_msg_id}`" if src_msg_id else f"```\n{msg_text[:300]}\n```"

    text = (
        f"🤖 **[SMART AUTO-BROADCAST CONTROL PANEL]** 🤖\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⚡ **System Status:** `{'ACTIVE ✅' if is_active else 'INACTIVE ❌'}`\n"
        f"🎯 **Active Targets:** `{t_status_str}`\n"
        f"🔗 **Link Preview:** `{preview_str}`\n"
        f"⏩ **Broadcast Mode:** `{mode_str}`\n"
        f"⏱️ **Interval Frequency:** `Every {interval_m} minutes`\n"
        f"🗑️ **Auto-Delete Timer:** `{del_str}`\n"
        f"🔢 **Round Limit:** `{max_r_str}`\n"
        f"📊 **Executed Rounds:** `{run_c}` rounds completed\n\n"
        f"👥 **Live Destinations Reach:**\n"
        f"  • Supergroups & Groups: `{groups_count}` ({'ENABLED' if eg else 'DISABLED'})\n"
        f"  • Channels: `{channels_count}` ({'ENABLED' if ec else 'DISABLED'})\n"
        f"  • DMs / Private Users: `{dms_count}` ({'ENABLED' if ed else 'DISABLED'})\n"
        f"  • **Current Target Reach:** `{len(all_dests)}` chats\n\n"
        f"📝 **Active Broadcast Payload:**\n"
        f"{preview_content}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Use the quick toggle switches and emergency buttons below:"
    )

    kb = get_sb_main_keyboard(cfg)
    if isinstance(message_or_query, CallbackQuery):
        try:
            await message_or_query.message.edit_text(text, reply_markup=kb)
        except Exception:
            try:
                user_id = message_or_query.from_user.id
                await client.send_message(user_id, text, reply_markup=kb)
            except Exception:
                pass
    else:
        try:
            await message_or_query.reply_text(text, reply_markup=kb)
        except Exception:
            pass

# ─── Commands & Handlers ───
SB_COMMANDS = ["smartbroadcast", "sbcast", "autobcast", "smartbcast", "sb", "autobroadcast", "abc"]
SB_REGEX_PATTERN = r"^(?:/|!|\.|)(?:smartbroadcast|sbcast|autobcast|smartbcast|sb|autobroadcast|abc)(?:@\w+)?$"

def get_sender_id(message: Message) -> int:
    if not message:
        return 0
    if message.from_user:
        return message.from_user.id
    if message.sender_chat:
        return message.sender_chat.id
    return 0

@app.on_message((filters.command(SB_COMMANDS, prefixes=["/", "!", ".", ""]) | filters.regex(re.compile(SB_REGEX_PATTERN, re.IGNORECASE))), group=-1)
async def smart_broadcast_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        await message.reply_text(f"❌ **Access Denied:** Only the bot owner can access Smart Broadcast. (Your ID: `{user_id}`)")
        return
    await render_smart_broadcast_menu(client, message)

@app.on_message((filters.command(["sbcastnow", "smartbroadcastnow"], prefixes=["/", "!", ".", ""]) | filters.regex(re.compile(r"^(?:/|!|\.|)(?:sbcastnow|smartbroadcastnow)(?:@\w+)?$", re.IGNORECASE))), group=-1)
async def smart_broadcast_now_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        await message.reply_text(f"❌ **Access Denied:** Only the bot owner can access Smart Broadcast. (Your ID: `{user_id}`)")
        return

    status_msg = await message.reply_text("🚀 **Launching High-Speed Smart Broadcast in background...**")
    sent, failed, failed_details, err = await execute_smart_broadcast_round(manual=True, status_msg=status_msg)
    if err:
        await status_msg.edit(f"❌ **Broadcast Failed:** {err}")
    else:
        cfg = await get_sb_config()
        del_s = cfg.get("delete_after_seconds", 0)
        del_str = format_time_duration(del_s)

        fail_summary = "\n".join(failed_details[:10]) if failed_details else "None 🎉"
        if len(failed_details) > 10:
            fail_summary += f"\n... and {len(failed_details) - 10} more."

        report = (
            f"📢 **[SMART BROADCAST MANUAL REPORT]** 📢\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ **Successfully Delivered:** `{sent}` chats\n"
            f"❌ **Failed Deliveries:** `{failed}` chats\n"
            f"🗑️ **Scheduled Auto-Delete Timer:** `{del_str}`\n\n"
            f"⚠️ **Delivery Failure Breakdown:**\n"
            f"{fail_summary}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await status_msg.edit(report, reply_markup=get_sb_report_keyboard())

# Fast Slash Commands for Setting Custom Values Directly
@app.on_message(filters.command(["setinterval"], prefixes=["/", "!", ".", ""]), group=-1)
async def set_interval_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        return
    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/setinterval <minutes>` (e.g. `/setinterval 45`)")
        return
    try:
        mins = int(message.command[1])
        await update_sb_config({"interval_mins": max(1, mins)})
        await message.reply_text(f"✅ **Broadcast interval updated to {mins} minutes!**")
    except ValueError:
        await message.reply_text("❌ Invalid number!")

@app.on_message(filters.command(["setdeletetimer"], prefixes=["/", "!", ".", ""]), group=-1)
async def set_delete_timer_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        return
    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/setdeletetimer <seconds_or_mins>` (e.g. `/setdeletetimer 45s` or `/setdeletetimer 15`)")
        return
    raw_val = message.command[1].strip().lower()
    try:
        if raw_val.endswith("s"):
            secs = int(raw_val[:-1])
        else:
            secs = int(raw_val) * 60
        await update_sb_config({"delete_after_seconds": max(0, secs)})
        await message.reply_text(f"✅ **Auto-Delete timer set to {format_time_duration(secs)}!**")
    except ValueError:
        await message.reply_text("❌ Invalid format!")

@app.on_message(filters.command(["setmaxrounds"], prefixes=["/", "!", ".", ""]), group=-1)
async def set_max_rounds_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        return
    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/setmaxrounds <count>` (e.g. `/setmaxrounds 5` or `/setmaxrounds 0` for infinite)")
        return
    try:
        rnds = int(message.command[1])
        await update_sb_config({"max_runs": max(0, rnds)})
        await message.reply_text(f"✅ **Max round limit set to {rnds if rnds > 0 else 'Infinite'}!**")
    except ValueError:
        await message.reply_text("❌ Invalid number!")

@app.on_message(filters.command(["syncchats", "sb_sync", "syncbcast"], prefixes=["/", "!", ".", ""]), group=-1)
async def sync_chats_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        return
    st = await message.reply_text("🔄 **Scanning & syncing all active bot channels, groups & users across all sessions...**")
    await sync_all_broadcast_destinations()
    count = await _dest_col.count_documents({})
    g_count = await _dest_col.count_documents({"chat_id": {"$lt": 0}, "chat_type": {"$in": ["group", "supergroup"]}})
    c_count = await _dest_col.count_documents({"chat_id": {"$lt": 0}, "chat_type": "channel"})
    d_count = await _dest_col.count_documents({"chat_id": {"$gt": 0}})
    await st.edit_text(
        f"✅ **Sync Completed!**\n\n"
        f"• **Channels:** `{c_count}` 📢\n"
        f"• **Supergroups & Groups:** `{g_count}` 👥\n"
        f"• **Registered Users (DMs):** `{d_count}` 👤\n"
        f"• **Total Reachable:** `{count}` chats."
    )

# Bulk & Single Channel Adder
@app.on_message(filters.command(["addchannel", "addchan", "addchannels"], prefixes=["/", "!", ".", ""]), group=-1)
async def add_channel_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    raw_targets = []
    if len(message.command) > 1:
        raw_targets.extend(message.command[1:])
    elif message.reply_to_message and message.reply_to_message.text:
        raw_targets.extend(message.reply_to_message.text.replace("\n", " ").replace(",", " ").split())

    if not raw_targets:
        await message.reply_text(
            "❌ **Usage:** `/addchannels <id_or_username> [more_ids...]`\n\n"
            "Examples:\n"
            "• Single: `/addchannel -1001234567890`\n"
            "• Bulk: `/addchannels -1001111111 -1002222222 @mychannel1 @mychannel2`\n"
            "• Or reply `/addchannels` to a list of IDs/usernames!"
        )
        return

    added = 0
    failed = []
    from toxic.core.mongo.db import add_joined_chat

    for target_input in raw_targets:
        target_input = target_input.strip()
        if not target_input:
            continue
        cid = None
        title = None
        try:
            chat = await client.get_chat(target_input)
            cid = chat.id
            title = chat.title or chat.username or f"Channel {cid}"
        except Exception:
            try:
                cid = int(target_input)
                title = f"Channel {cid}"
            except ValueError:
                failed.append(target_input)
                continue

        if cid:
            await add_sb_destination(cid, title, "channel")
            await add_joined_chat(cid, title, chat_type="channel")
            added += 1

    resp = f"✅ **Successfully added `{added}` channels to Smart Broadcast!**"
    if failed:
        resp += f"\n⚠️ **Failed to parse/resolve:** `{', '.join(failed[:10])}`"
    await message.reply_text(resp)

# Bulk & Single Group Adder
@app.on_message(filters.command(["addgroup", "addsupergroup", "addgroups"], prefixes=["/", "!", ".", ""]), group=-1)
async def add_group_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        await message.reply_text("❌ **Access Denied:** Only the bot owner can use this command.")
        return

    raw_targets = []
    if len(message.command) > 1:
        raw_targets.extend(message.command[1:])
    elif message.reply_to_message and message.reply_to_message.text:
        raw_targets.extend(message.reply_to_message.text.replace("\n", " ").replace(",", " ").split())

    if not raw_targets:
        await message.reply_text(
            "❌ **Usage:** `/addgroups <id_or_username> [more_ids...]`\n\n"
            "Examples:\n"
            "• Single: `/addgroup -1001234567890`\n"
            "• Bulk: `/addgroups -1001111111 -1002222222 @mygroup1 @mygroup2`\n"
            "• Or reply `/addgroups` to a list of IDs/usernames!"
        )
        return

    added = 0
    failed = []
    from toxic.core.mongo.db import add_joined_chat

    for target_input in raw_targets:
        target_input = target_input.strip()
        if not target_input:
            continue
        cid = None
        title = None
        try:
            chat = await client.get_chat(target_input)
            cid = chat.id
            title = chat.title or chat.username or f"Group {cid}"
        except Exception:
            try:
                cid = int(target_input)
                title = f"Group {cid}"
            except ValueError:
                failed.append(target_input)
                continue

        if cid:
            await add_sb_destination(cid, title, "supergroup")
            await add_joined_chat(cid, title, chat_type="supergroup")
            added += 1

    resp = f"✅ **Successfully added `{added}` groups to Smart Broadcast!**"
    if failed:
        resp += f"\n⚠️ **Failed to parse/resolve:** `{', '.join(failed[:10])}`"
    await message.reply_text(resp)

@app.on_message(filters.command(["delchannel", "delgroup", "delchat", "removesb"], prefixes=["/", "!", ".", ""]), group=-1)
async def remove_sb_chat_cmd(client: Client, message: Message):
    user_id = get_sender_id(message)
    if not is_owner(user_id):
        return
    if len(message.command) < 2:
        await message.reply_text("❌ **Usage:** `/delchannel <chat_id>` (e.g. `/delchannel -1001234567890`)")
        return
    try:
        cid = int(message.command[1].strip())
        await remove_sb_destination(cid)
        from toxic.core.mongo.db import remove_joined_chat
        await remove_joined_chat(cid)
        await message.reply_text(f"✅ **Chat `{cid}` removed from Smart Broadcast destinations!**")
    except ValueError:
        await message.reply_text("❌ Invalid chat ID! Must be a negative integer (e.g. `-100...`).")

# ─── Interactive Callback Handler ───
@app.on_callback_query(filters.regex(r"^sb_"))
async def smart_broadcast_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_owner(user_id):
        await callback_query.answer("❌ Access Denied!", show_alert=True)
        return

    data = callback_query.data
    cfg = await get_sb_config()

    if data == "sb_close":
        await callback_query.message.delete()
        return

    elif data == "sb_back":
        await render_smart_broadcast_menu(client, callback_query)
        return

    elif data == "sb_toggle_status":
        new_status = not cfg.get("is_active", False)
        await update_sb_config({"is_active": new_status})
        if not new_status:
            deleted, _ = await delete_all_active_sb_messages()
            await callback_query.answer(f"Deactivated! Deleted {deleted} active broadcast messages.", show_alert=True)
        else:
            await callback_query.answer("Smart Auto-Broadcast Activated! ✅", show_alert=True)
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_stop_next":
        await update_sb_config({"is_active": False})
        await callback_query.answer("🛑 Next Broadcast Stopped & Scheduler Deactivated!", show_alert=True)
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_delete_last":
        await callback_query.answer("🗑️ Deleting Last Broadcast Messages Now...")
        last_round = cfg.get("last_broadcast_round", 0)
        query = {"round_num": last_round} if last_round > 0 else {}
        deleted_ok, failed_list = await delete_all_active_sb_messages(query)

        fail_str = "\n".join(failed_list[:10]) if failed_list else "None 🎉 (All deleted cleanly!)"
        if len(failed_list) > 10:
            fail_str += f"\n... and {len(failed_list) - 10} more."

        report = (
            f"🗑️ **[DELETE LAST BROADCAST REPORT]** 🗑️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ **Successfully Deleted Messages:** `{deleted_ok}` chats\n"
            f"⚠️ **Could Not Delete / Failed:** `{len(failed_list)}` chats\n\n"
            f"📌 **Failed Deletion Details:**\n"
            f"{fail_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await callback_query.message.edit_text(report, reply_markup=get_sb_report_keyboard())

    elif data == "sb_force_delete_all":
        await callback_query.answer("🧹 Starting Emergency 1-Click Force Deletion...")
        deleted_ok, failed_list = await delete_all_active_sb_messages()

        fail_str = "\n".join(failed_list[:10]) if failed_list else "None 🎉 (All deleted cleanly!)"
        if len(failed_list) > 10:
            fail_str += f"\n... and {len(failed_list) - 10} more."

        report = (
            f"🎉 **[1-CLICK FORCE DELETION COMPLETE]** 🎉\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ **Successfully Deleted Messages:** `{deleted_ok}` chats\n"
            f"⚠️ **Could Not Delete / Failed:** `{len(failed_list)}` chats\n\n"
            f"📌 **Failed Deletion Details:**\n"
            f"{fail_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await callback_query.message.edit_text(report, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="sb_back")]]))

    elif data == "sb_toggle_preview":
        new_preview = not cfg.get("disable_web_page_preview", True)
        await update_sb_config({"disable_web_page_preview": new_preview})
        await callback_query.answer(f"Link Preview set to: {'OFF ❌' if new_preview else 'ON 🌐'}", show_alert=True)
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_toggle_mode":
        new_mode = not cfg.get("fast_forward_mode", True)
        await update_sb_config({"fast_forward_mode": new_mode})
        await callback_query.answer(f"Mode set to: {'Fast Copy (No Tag)' if new_mode else 'Forward Tag'}", show_alert=True)
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_toggle_target_groups":
        new_val = not cfg.get("enable_groups", True)
        await update_sb_config({"enable_groups": new_val})
        await callback_query.answer(f"Groups Broadcast: {'ENABLED ✅' if new_val else 'DISABLED ❌'}")
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_toggle_target_channels":
        new_val = not cfg.get("enable_channels", True)
        await update_sb_config({"enable_channels": new_val})
        await callback_query.answer(f"Channels Broadcast: {'ENABLED ✅' if new_val else 'DISABLED ❌'}")
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_toggle_target_dms":
        new_val = not cfg.get("enable_dms", True)
        await update_sb_config({"enable_dms": new_val})
        await callback_query.answer(f"DMs Broadcast: {'ENABLED ✅' if new_val else 'DISABLED ❌'}")
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_set_interval":
        await callback_query.message.edit_text(
            "⏱️ **Select Broadcast Interval Frequency:**\n\nChoose how often the broadcast should repeat:",
            reply_markup=get_sb_interval_keyboard()
        )

    elif data.startswith("sb_int_"):
        val = data.split("_")[-1]
        if val == "custom":
            await callback_query.message.delete()
            ask = await client.ask(user_id, "⏱️ **Enter custom interval frequency in minutes (e.g. 10, 45, 180):**\n\n> Send /cancel to abort.")
            if ask.text and ask.text != "/cancel":
                try:
                    mins = int(ask.text.strip())
                    await update_sb_config({"interval_mins": max(1, mins)})
                    await ask.reply(f"✅ **Interval updated to {mins} minutes!**")
                except ValueError:
                    await ask.reply("❌ Invalid number!")
            await render_smart_broadcast_menu(client, ask if 'ask' in locals() else callback_query)
            return
        else:
            mins = int(val)
            await update_sb_config({"interval_mins": mins})
            await callback_query.answer(f"Interval set to {mins} minutes")
            await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_set_delete_timer":
        await callback_query.message.edit_text(
            "🗑️ **Select Auto-Delete Duration:**\n\nChoose how long messages should stay before being automatically deleted:",
            reply_markup=get_sb_delete_timer_keyboard()
        )

    elif data.startswith("sb_del_"):
        val = data.split("_")[-1]
        if val == "custom":
            await callback_query.message.delete()
            ask = await client.ask(user_id, "🗑️ **Enter custom auto-delete timer in minutes or seconds:**\n\n• For seconds add `s` (e.g. `45s`)\n• For minutes enter number (e.g. `15`)\n\n> Send /cancel to abort.")
            if ask.text and ask.text != "/cancel":
                raw_txt = ask.text.strip().lower()
                try:
                    if raw_txt.endswith("s"):
                        secs = int(raw_txt[:-1])
                    else:
                        secs = int(raw_txt) * 60
                    await update_sb_config({"delete_after_seconds": max(0, secs)})
                    await ask.reply(f"✅ **Auto-Delete timer set to {format_time_duration(secs)}!**")
                except ValueError:
                    await ask.reply("❌ Invalid format!")
            await render_smart_broadcast_menu(client, ask if 'ask' in locals() else callback_query)
            return
        else:
            secs = int(val)
            await update_sb_config({"delete_after_seconds": secs})
            await callback_query.answer(f"Auto-delete set to {format_time_duration(secs)}")
            await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_set_max_runs":
        await callback_query.message.edit_text(
            "🔢 **Select Maximum Round Limits:**\n\nChoose how many rounds the broadcast should run before stopping:",
            reply_markup=get_sb_rounds_keyboard()
        )

    elif data.startswith("sb_rnd_"):
        val = data.split("_")[-1]
        if val == "custom":
            await callback_query.message.delete()
            ask = await client.ask(user_id, "🔢 **Enter custom number of rounds (e.g. 3, 5, 10, 50):**\n\n> Send /cancel to abort.")
            if ask.text and ask.text != "/cancel":
                try:
                    rnds = int(ask.text.strip())
                    await update_sb_config({"max_runs": max(0, rnds)})
                    await ask.reply(f"✅ **Round limit set to {rnds} rounds!**")
                except ValueError:
                    await ask.reply("❌ Invalid number!")
            await render_smart_broadcast_menu(client, ask if 'ask' in locals() else callback_query)
            return
        else:
            rnds = int(val)
            await update_sb_config({"max_runs": rnds})
            await callback_query.answer(f"Round limit set to {rnds if rnds > 0 else 'Infinite'}")
            await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_reset_count":
        await update_sb_config({"run_count": 0, "last_broadcast_round": 0})
        await callback_query.answer("Run count reset to 0!")
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_clear_posts":
        deleted, _ = await delete_all_active_sb_messages()
        await callback_query.answer(f"Cleared {deleted} active broadcast messages from all chats!", show_alert=True)
        await render_smart_broadcast_menu(client, callback_query)

    elif data == "sb_set_message":
        await callback_query.message.delete()
        ask = await client.ask(
            user_id,
            "📝 **Send or Reply to your broadcast message now!**\n\n"
            "✨ Supports:\n"
            "• Plain/Formatted Text (Bold, Italic, Code, `> Blockquote`, Links)\n"
            "• Photos, Videos, GIFs/Animations, Documents, Audio, Voice\n"
            "• Direct reply to any existing message!\n\n"
            "> Send /cancel to abort."
        )
        if ask.text == "/cancel":
            await ask.reply("Cancelled.")
        else:
            if ask.reply_to_message:
                target_msg = ask.reply_to_message
                await update_sb_config({
                    "source_chat_id": target_msg.chat.id,
                    "source_msg_id": target_msg.id,
                    "content_type": "reply_msg",
                    "message_text": target_msg.caption or target_msg.text or "Replied Message Content"
                })
                await ask.reply("✅ **Replied message saved as broadcast payload!**")
            else:
                raw_text = ask.text.markdown if hasattr(ask.text, 'markdown') else ask.text
                await update_sb_config({
                    "source_chat_id": ask.chat.id,
                    "source_msg_id": ask.id,
                    "content_type": "text",
                    "message_text": raw_text
                })
                await ask.reply("✅ **Broadcast message saved successfully!**")
        await render_smart_broadcast_menu(client, ask)

    elif data == "sb_preview_msg":
        src_chat_id = cfg.get("source_chat_id")
        src_msg_id = cfg.get("source_msg_id")
        msg_text = cfg.get("message_text")

        if not src_msg_id and (not msg_text or msg_text == "None"):
            await callback_query.answer("❌ No broadcast payload saved yet! Set a message payload first.", show_alert=True)
            return

        await callback_query.answer("👁️ Sending broadcast preview to your DM...")

        header_text = (
            "👁️ <b>[SMART BROADCAST MESSAGE PREVIEW]</b>\n"
            "<i>This is how your broadcast message will look when delivered to groups, channels & DMs:</i>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await client.send_message(user_id, header_text, parse_mode=ParseMode.HTML)
        except Exception:
            pass

        sent_preview = None
        if src_chat_id and src_msg_id:
            try:
                if cfg.get("fast_forward_mode", True):
                    sent_preview = await client.copy_message(user_id, src_chat_id, src_msg_id)
                else:
                    sent_preview = await client.forward_messages(user_id, src_chat_id, src_msg_id)
            except Exception:
                try:
                    from toxic.modules.topic_mirror import get_client
                    ub = get_client()
                    if ub:
                        sent_preview = await ub.copy_message(user_id, src_chat_id, src_msg_id)
                except Exception as e:
                    print(f"[SmartBroadcast Preview Error]: {e}")

        if not sent_preview and msg_text and msg_text != "None":
            try:
                from toxic.core.func import format_caption_to_html
                html_txt = format_caption_to_html(msg_text)
                sent_preview = await client.send_message(
                    user_id,
                    html_txt if html_txt else msg_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=cfg.get("disable_web_page_preview", True)
                )
            except Exception as txt_err:
                print(f"[SmartBroadcast Preview Text Error]: {txt_err}")

        del_s = cfg.get("delete_after_seconds", 0)
        footer = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n✅ <b>Preview Sent!</b>"
        if del_s > 0:
            footer += f"\n<i>⏱ Auto-delete timer is active: <b>{format_time_duration(del_s)}</b> after delivery.</i>"

        try:
            await client.send_message(user_id, footer, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    elif data == "sb_launch_now":
        await callback_query.message.edit_text("🚀 **Launching High-Speed Smart Broadcast to enabled destinations in background...**")
        sent, failed, failed_details, err = await execute_smart_broadcast_round(manual=True, status_msg=callback_query.message)
        if err:
            await callback_query.message.reply_text(f"❌ **Broadcast Failed:** {err}")
        else:
            del_s = cfg.get("delete_after_seconds", 0)
            del_str = format_time_duration(del_s)

            fail_summary = "\n".join(failed_details[:10]) if failed_details else "None 🎉"
            if len(failed_details) > 10:
                fail_summary += f"\n... and {len(failed_details) - 10} more."

            report = (
                f"📢 **[SMART BROADCAST MANUAL REPORT]** 📢\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ **Successfully Delivered:** `{sent}` chats\n"
                f"❌ **Failed Deliveries:** `{failed}` chats\n"
                f"🗑️ **Scheduled Auto-Delete Timer:** `{del_str}`\n\n"
                f"⚠️ **Delivery Failure Breakdown:**\n"
                f"{fail_summary}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await callback_query.message.edit_text(report, reply_markup=get_sb_report_keyboard())

    elif data == "sb_view_stats":
        all_stored = []
        try:
            async for doc in _dest_col.find({}):
                all_stored.append(doc)
        except Exception:
            pass

        text = f"📊 **Smart Broadcast Destinations Breakdown ({len(all_stored)} Total):**\n"
        text += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for i, dest in enumerate(all_stored[:30], 1):
            text += f"{i}. **{dest['title']}** (`{dest['chat_type'].upper()}`)\n   • ID: `{dest['chat_id']}`\n"
        if len(all_stored) > 30:
            text += f"\n... and {len(all_stored) - 30} more destinations."
        await callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="sb_back")]]))

    elif data == "sb_sync_chats":
        await callback_query.answer("🔄 Scanning & syncing all active bot channels, groups & users across all sessions...")
        await sync_all_broadcast_destinations()
        count = await _dest_col.count_documents({})
        g_count = await _dest_col.count_documents({"chat_id": {"$lt": 0}, "chat_type": {"$in": ["group", "supergroup"]}})
        c_count = await _dest_col.count_documents({"chat_id": {"$lt": 0}, "chat_type": "channel"})
        await callback_query.answer(f"✅ Synced! Found {c_count} channels, {g_count} groups ({count} total).", show_alert=True)
        await render_smart_broadcast_menu(client, callback_query)

# ─── Autonomous Presence Tracking Handlers ───
@app.on_message(filters.group | filters.channel, group=-2)
async def smart_broadcast_auto_tracker(client: Client, message: Message):
    try:
        chat = message.chat
        c_type = "channel" if chat.type == ChatType.CHANNEL else "supergroup"
        title = chat.title or chat.first_name or chat.username or f"Chat {chat.id}"
        await add_sb_destination(chat.id, title, c_type)
        from toxic.core.mongo.db import add_joined_chat
        await add_joined_chat(chat.id, title, chat_type=c_type)
    except Exception:
        pass

@app.on_chat_member_updated()
async def smart_broadcast_member_tracker(client: Client, chat_member_updated: ChatMemberUpdated):
    try:
        me = await client.get_me()
        new_member = chat_member_updated.new_chat_member
        if new_member and new_member.user.id == me.id:
            chat = chat_member_updated.chat
            status = new_member.status
            c_type = "channel" if chat.type == ChatType.CHANNEL else "supergroup"
            if status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                title = chat.title or chat.username or f"Chat {chat.id}"
                await add_sb_destination(chat.id, title, c_type)
                from toxic.core.mongo.db import add_joined_chat
                await add_joined_chat(chat.id, title, chat_type=c_type)
                print(f"[SmartBroadcast AutoTracker] Added bot destination: {title} ({chat.id}) [{c_type}]")
            elif status in [ChatMemberStatus.LEFT, ChatMemberStatus.BANNED]:
                await remove_sb_destination(chat.id)
                from toxic.core.mongo.db import remove_joined_chat
                await remove_joined_chat(chat.id)
                print(f"[SmartBroadcast AutoTracker] Removed bot destination: {chat.title} ({chat.id})")
    except Exception as e:
        print(f"[SmartBroadcast AutoTracker] Error: {e}")

# ─── Autonomous Background Broadcast Scheduler Loop ───
async def smart_broadcast_background_scheduler():
    while True:
        try:
            cfg = await get_sb_config()
            if cfg and cfg.get("is_active"):
                interval_m = cfg.get("interval_mins", 30)
                max_r = cfg.get("max_runs", 0)
                run_c = cfg.get("run_count", 0)
                last_run = cfg.get("last_run")

                if max_r > 0 and run_c >= max_r:
                    await update_sb_config({"is_active": False})
                    print(f"[SmartBroadcast Scheduler] Max round limit ({max_r}) reached. Deactivating.")
                    continue

                now = datetime.datetime.now()
                should_run = False
                if not last_run:
                    should_run = True
                else:
                    elapsed = (now - last_run).total_seconds() / 60.0
                    if elapsed >= interval_m:
                        should_run = True

                if should_run:
                    new_run_c = run_c + 1
                    await update_sb_config({
                        "last_run": now,
                        "run_count": new_run_c
                    })

                    if max_r > 0 and new_run_c >= max_r:
                        await update_sb_config({"is_active": False})

                    sent, failed, failed_details, err = await execute_smart_broadcast_round()
                    print(f"[SmartBroadcast Scheduler] Executed round #{new_run_c}. Delivered: {sent}, Failed: {failed}")

                    # Notify owner(s) with live report
                    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
                    del_s = cfg.get("delete_after_seconds", 0)
                    del_str = format_time_duration(del_s)
                    max_r_str = f"{max_r} Rounds" if max_r > 0 else "Infinite ♾️"
                    next_time = now + datetime.timedelta(minutes=interval_m)

                    fail_summary = "\n".join(failed_details[:10]) if failed_details else "None 🎉"
                    if len(failed_details) > 10:
                        fail_summary += f"\n... and {len(failed_details) - 10} more."

                    report = (
                        f"📢 **[SMART AUTO-BROADCAST ROUND #{new_run_c} EXECUTED]** 📢\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"📊 **Rounds Progress:** `{new_run_c}` / `{max_r_str}`\n"
                        f"📤 **Successfully Delivered:** `{sent}` chats\n"
                        f"⚠️ **Failed / Skipped:** `{failed}` chats\n"
                        f"🗑️ **Auto-Delete Timer:** `{del_str}`\n\n"
                        f"📌 **Delivery Failures (if any):**\n"
                        f"{fail_summary}\n\n"
                        f"⏱️ **Next Scheduled Round:**\n"
                        f"📅 `{next_time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                    for oid in owner_list:
                        try:
                            await app.send_message(int(oid), report, reply_markup=get_sb_report_keyboard())
                        except Exception:
                            pass
        except Exception as scheduler_err:
            print(f"[SmartBroadcast Scheduler] Loop notice: {scheduler_err}")

        await asyncio.sleep(5)

# Launch background scheduler task & dedicated real-time deletion worker on import
asyncio.create_task(smart_broadcast_background_scheduler())
asyncio.create_task(smart_broadcast_dedicated_deletion_worker())
