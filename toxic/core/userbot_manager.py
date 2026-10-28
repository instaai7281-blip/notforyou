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
                    return existing
                else:
                    await existing.start()
                    logger.info(f"[UserbotManager] Reconnected existing client for user {user_id} on @{bot_name}")
                    return existing
            except errors.AuthKeyDuplicated:
                logger.warning(f"[UserbotManager] AUTH_KEY_DUPLICATED on reconnect for {user_id} on @{bot_name}. Evicting cached instance.")
                await handle_burned_session(user_id, bot_name)
                return None
            except Exception as re_err:
                logger.warning(f"[UserbotManager] Reconnecting cached client for {user_id} failed: {re_err}. Rebuilding...")
                _active_userbots.pop(user_id, None)
                try:
                    await existing.stop()
                except Exception:
                    pass

        # 2. Retrieve session string if not provided (per-bot partition first)
        if not session_string:
            try:
                session_string = await db.get_user_session(user_id, bot_name=bot_name)
            except Exception as db_err:
                logger.error(f"[UserbotManager] Failed to fetch session from MongoDB for {user_id}: {db_err}")
                return None

        if not session_string:
            return None

        # 3. Check if this session is already running in pro_clients to avoid duplicating
        try:
            from toxic import pro_clients
            if pro_clients:
                for pc in pro_clients:
                    if getattr(pc, "is_connected", False):
                        if getattr(pc, "session_string", None) == session_string:
                            logger.info(f"[UserbotManager] Reusing pro_client for user {user_id}")
                            _active_userbots[user_id] = pc
                            return pc
        except Exception:
            pass

        # 4. Create single unified Client instance for THIS bot
        # Using no_updates=True allows multiple bots to share the exact same userbot session
        # concurrently for cloning/mirroring without triggering Telegram's AUTH_KEY_DUPLICATED!
        try:
            ub = Client(
                f"ub_{bot_name}_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True,
                no_updates=True,
                workers=8,
                max_concurrent_transmissions=4,
                sleep_threshold=60
            )
            await ub.start()

            _active_userbots[user_id] = ub
            logger.info(f"[UserbotManager] ✅ Unified client started successfully for user {user_id} on @{bot_name}")
            return ub

        except errors.AuthKeyDuplicated:
            logger.warning(f"[UserbotManager] AUTH_KEY_DUPLICATED for {user_id} on @{bot_name}. Releasing in-memory client without deleting DB session.")
            _active_userbots.pop(user_id, None)
            return None
        except Exception as e:
            logger.error(f"[UserbotManager] ❌ Failed to start unified client for {user_id} on @{bot_name}: {e}")
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
