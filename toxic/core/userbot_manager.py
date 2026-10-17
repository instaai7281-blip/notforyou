# ---------------------------------------------------
# File Name: userbot_manager.py
# Description: Unified Singleton Userbot Client Manager
#              Guarantees a SINGLE active Client per user session
#              Completely prevents [406 AUTH_KEY_DUPLICATED]
# Author: Antigravity
# ---------------------------------------------------

import asyncio
import logging
from typing import Optional, Dict
from pyrogram import Client
from config import API_ID, API_HASH
from toxic.core.mongo import db

logger = logging.getLogger(__name__)

# Master dictionary: user_id -> Client instance
_active_userbots: Dict[int, Client] = {}
# Concurrency locks per user to prevent simultaneous instantiation race conditions
_locks: Dict[int, asyncio.Lock] = {}
_master_lock = asyncio.Lock()


async def get_user_lock(user_id: int) -> asyncio.Lock:
    """Returns a dedicated lock for the specified user_id."""
    async with _master_lock:
        if user_id not in _locks:
            _locks[user_id] = asyncio.Lock()
        return _locks[user_id]


async def get_or_create_userbot(user_id: int, session_string: Optional[str] = None) -> Optional[Client]:
    """
    Returns the single, shared, active Pyrogram Client instance for a given user.
    Guarantees that an auth key (session string) is NEVER opened in multiple clients simultaneously,
    completely preventing [406 AUTH_KEY_DUPLICATED].
    """
    if not user_id:
        return None

    lock = await get_user_lock(user_id)
    async with lock:
        # 1. Check existing cached client
        existing = _active_userbots.get(user_id)
        if existing:
            try:
                if getattr(existing, "is_connected", False):
                    return existing
                else:
                    await existing.start()
                    logger.info(f"[UserbotManager] Reconnected existing client for user {user_id}")
                    return existing
            except Exception as re_err:
                logger.warning(f"[UserbotManager] Reconnecting cached client for {user_id} failed: {re_err}. Rebuilding...")
                _active_userbots.pop(user_id, None)
                try:
                    await existing.stop()
                except Exception:
                    pass

        # 2. Retrieve session string if not provided
        if not session_string:
            try:
                user_data = await db.get_data(user_id)
                session_string = user_data.get("session") if user_data else None
            except Exception as db_err:
                logger.error(f"[UserbotManager] Failed to fetch session from MongoDB for {user_id}: {db_err}")
                return None

        if not session_string:
            return None

        # 3. Create single unified Client instance
        try:
            ub = Client(
                f"ub_unified_{user_id}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=session_string,
                in_memory=True,
                no_updates=False,  # Allows handling real-time view-once events while serving API requests
                max_concurrent_transmissions=64
            )
            await ub.start()

            # Attach view-once auto-saver handler dynamically to this unified client
            try:
                from toxic.modules.view_once import attach_view_once_to_client
                attach_view_once_to_client(ub, user_id)
            except Exception as vo_err:
                logger.warning(f"[UserbotManager] Failed to attach view_once handler to {user_id}: {vo_err}")

            _active_userbots[user_id] = ub
            logger.info(f"[UserbotManager] ✅ Unified client started successfully for user {user_id}")
            return ub

        except Exception as e:
            logger.error(f"[UserbotManager] ❌ Failed to start unified client for {user_id}: {e}")
            return None


async def close_userbot(user_id: int):
    """Gracefully disconnects and unregisters a user's client (e.g. during logout or relogin)."""
    lock = await get_user_lock(user_id)
    async with lock:
        client = _active_userbots.pop(user_id, None)
        if client:
            try:
                if getattr(client, "is_connected", False):
                    await client.stop()
                logger.info(f"[UserbotManager] Client for user {user_id} stopped cleanly.")
            except Exception as e:
                logger.warning(f"[UserbotManager] Client stop notice for user {user_id}: {e}")


def get_active_userbot_sync(user_id: int) -> Optional[Client]:
    """Synchronous lookup for an active, already-connected client instance."""
    client = _active_userbots.get(user_id)
    if client and getattr(client, "is_connected", False):
        return client
    return None
