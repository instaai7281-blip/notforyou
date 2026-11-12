# ---------------------------------------------------
# File Name: userbot_manager.py
# Description: Multi-Bot Aware Singleton Userbot Client Manager
#              Guarantees clean session isolation across multiple deployed bots
#              sharing the same MongoDB database. Completely prevents [406 AUTH_KEY_DUPLICATED]
# Author: Antigravity
# ---------------------------------------------------

import asyncio
import logging
from typing import Optional, Dict
from pyrogram import Client, errors
from config import API_ID, API_HASH
from toxic.core.mongo import db

logger = logging.getLogger(__name__)

# Master dictionary for THIS bot process: user_id -> Client instance
_active_userbots: Dict[int, Client] = {}
# Concurrency locks per user to prevent simultaneous instantiation race conditions
_locks: Dict[int, asyncio.Lock] = {}
_master_lock = asyncio.Lock()


def get_current_bot_username() -> str:
    """Returns the current bot's username or identifier."""
    try:
        from toxic import app
        if getattr(app, "me", None) and app.me.username:
            return app.me.username
    except Exception:
        pass
    return "default_bot"


async def get_user_lock(user_id: int) -> asyncio.Lock:
    """Returns a dedicated lock for the specified user_id."""
    async with _master_lock:
        if user_id not in _locks:
            _locks[user_id] = asyncio.Lock()
        return _locks[user_id]


async def get_or_create_userbot(user_id: int, session_string: Optional[str] = None) -> Optional[Client]:
    """
    Returns the dedicated active Pyrogram Client instance for a given user on THIS bot.
    Isolates sessions per-bot so multiple bots deployed on the same MongoDB can run
    simultaneously from the same Telegram user account without [406 AUTH_KEY_DUPLICATED].
    """
    if not user_id:
        return None

    bot_name = get_current_bot_username()
    lock = await get_user_lock(user_id)
    async with lock:
        # 1. Check existing cached client in this bot process
        existing = _active_userbots.get(user_id)
        if existing:
            try:
                if getattr(existing, "is_connected", False):
                    try:
                        from toxic.modules.view_once import attach_view_once_to_client
                        attach_view_once_to_client(existing, user_id)
                    except Exception:
                        pass
                    return existing
                else:
                    await asyncio.wait_for(existing.start(), timeout=12.0)
                    try:
                        from toxic.modules.view_once import attach_view_once_to_client
                        attach_view_once_to_client(existing, user_id)
                    except Exception:
                        pass
                    logger.info(f"[UserbotManager] Reconnected existing client for user {user_id} on @{bot_name}")
                    return existing
            except errors.AuthKeyDuplicated:
                logger.warning(f"[UserbotManager] AUTH_KEY_DUPLICATED on reconnect for {user_id} on @{bot_name}. Evicting cached instance.")
                await handle_burned_session(user_id, bot_name)
                return None
            except Exception as re_err:
                logger.warning(f"[UserbotManager] Reconnecting cached client for {user_id} failed: {re_err}. Rebuilding...")
                try:
                    await existing.stop()
                except Exception:
                    pass

        # 2. Retrieve session string if not provided (per-bot partition strictly prioritized)
        is_dedicated_bot_session = False
        if not session_string:
            try:
                # Check if user specifically logged into THIS bot
                dedicated_sess = await db.get_user_session(user_id, bot_name=bot_name, allow_fallback=False)
                if dedicated_sess:
                    session_string = dedicated_sess
                    is_dedicated_bot_session = True
                else:
                    # Fallback to shared session only when needed for operations (use no_updates=True!)
                    session_string = await db.get_user_session(user_id, bot_name=bot_name, allow_fallback=True)
            except Exception as db_err:
                logger.error(f"[UserbotManager] Failed to fetch session from MongoDB for {user_id}: {db_err}")
                return None

        if not session_string:
            return None

        # Check assigned_bot in DB so ONLY the primary logged-in bot subscribes to live updates
        if not is_dedicated_bot_session:
            try:
                u_doc = await db.get_data(user_id)
                if u_doc and u_doc.get("assigned_bot") == bot_name:
                    is_dedicated_bot_session = True
            except Exception:
                pass

        # 3. Check if this session is already running in pro_clients to avoid duplicating
        try:
            from toxic import pro_clients
            if pro_clients:
                for pc in pro_clients:
                    if getattr(pc, "is_connected", False):
                        if getattr(pc, "session_string", None) == session_string:
                            logger.info(f"[UserbotManager] Reusing pro_client for user {user_id}")
                            _active_userbots[user_id] = pc
                            try:
                                from toxic.modules.view_once import attach_view_once_to_client
                                attach_view_once_to_client(pc, user_id)
                            except Exception:
                                pass
                            return pc
        except Exception:
            pass

        # 4. Create single unified Client instance for THIS bot
        # Only subscribe to updates (no_updates=False) on the bot where user actually logged in!
        # If AuthKeyDuplicated happens (e.g. rolling restart or concurrent client), cleanly fallback to no_updates=True.
        last_err = None
        for try_no_updates in ([False, True] if is_dedicated_bot_session else [True]):
            try:
                ub = Client(
                    f"ub_{bot_name}_{user_id}_{'upd' if not try_no_updates else 'noupd'}",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    session_string=session_string,
                    in_memory=True,
                    no_updates=try_no_updates,
                    workers=12,
                    max_concurrent_transmissions=6,
                    sleep_threshold=180
                )
                await asyncio.wait_for(ub.start(), timeout=15.0)

                _active_userbots[user_id] = ub
                if not try_no_updates:
                    try:
                        from toxic.modules.view_once import attach_view_once_to_client
                        attach_view_once_to_client(ub, user_id)
                    except Exception as vo_err:
                        logger.warning(f"[UserbotManager] Notice attaching view-once handler: {vo_err}")
                logger.info(f"[UserbotManager] ✅ Unified client started for {user_id} on @{bot_name} (no_updates={try_no_updates})")
                return ub

            except errors.AuthKeyDuplicated as akd_err:
                last_err = akd_err
                logger.warning(f"[UserbotManager] AUTH_KEY_DUPLICATED (no_updates={try_no_updates}) for {user_id} on @{bot_name}. Retrying safe isolation mode...")
                _active_userbots.pop(user_id, None)
                try:
                    await ub.stop()
                except Exception:
                    pass
                await asyncio.sleep(1.0)
                continue
            except (errors.AuthKeyUnregistered, errors.SessionRevoked, errors.UserDeactivated, errors.UserDeactivatedBan) as auth_err:
                logger.info(f"[UserbotManager] Session expired/revoked ({type(auth_err).__name__}) for {user_id} on @{bot_name}. Purged dead session from DB.")
                _active_userbots.pop(user_id, None)
                try:
                    await db.remove_user_session(user_id, bot_name=bot_name)
                except Exception:
                    pass
                return None
            except Exception as e:
                last_err = e
                logger.error(f"[UserbotManager] ❌ Failed to start unified client for {user_id} on @{bot_name}: {e}")
                return None

        return None


async def handle_burned_session(user_id: int, bot_name: str = None):
    """Safely cleans up an active client instance without aggressively deleting valid Mongo sessions."""
    if not bot_name:
        bot_name = get_current_bot_username()
    client = _active_userbots.pop(user_id, None)
    if client:
        try:
            if getattr(client, "is_connected", False):
                await client.stop()
        except Exception:
            pass
    logger.info(f"[UserbotManager] Evicted in-memory client for user {user_id} on @{bot_name}")


async def close_userbot(user_id: int):
    """Gracefully disconnects and unregisters a user's client."""
    bot_name = get_current_bot_username()
    lock = await get_user_lock(user_id)
    async with lock:
        client = _active_userbots.pop(user_id, None)
        if client:
            try:
                if getattr(client, "is_connected", False):
                    await client.stop()
                logger.info(f"[UserbotManager] Client for user {user_id} stopped cleanly on @{bot_name}.")
            except Exception as e:
                logger.warning(f"[UserbotManager] Client stop notice for user {user_id}: {e}")


def get_active_userbot_sync(user_id: int) -> Optional[Client]:
    """Synchronous lookup for an active, already-connected client instance in this bot process."""
    client = _active_userbots.get(user_id)
    if client and getattr(client, "is_connected", False):
        return client
    return None
