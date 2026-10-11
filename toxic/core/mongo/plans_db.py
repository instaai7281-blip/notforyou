# ---------------------------------------------------
# File Name: plans_db.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

import datetime
from motor.motor_asyncio import AsyncIOMotorClient as MongoCli
from config import MONGO_DB
 
mongo = MongoCli(MONGO_DB)
db = mongo.premium
db = db.premium_db
 
async def add_premium(user_id, expire_date):
    data = await check_premium(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": {"expire_date": expire_date}})
    else:
        await db.insert_one({"_id": user_id, "expire_date": expire_date})
 
async def remove_premium(user_id):
    await db.delete_one({"_id": user_id})
 
async def check_premium(user_id):
    return await db.find_one({"_id": user_id})
 
async def premium_users():
    id_list = []
    async for data in db.find():
        id_list.append(data["_id"])
    return id_list
 
async def check_and_remove_expired_users():
    current_time = datetime.datetime.utcnow()
    async for data in db.find():
        expire_date = data.get("expire_date")
        if expire_date and expire_date < current_time:
            await remove_premium(data["_id"])
            print(f"Removed user {data['_id']} due to expired plan.")

# ────── Topic Mirroring Special Plan Collection ──────
mirror_db = mongo.premium.mirror_premium_db

async def add_mirror_premium(user_id, expire_date):
    data = await check_mirror_premium(user_id)
    if data and data.get("_id"):
        await mirror_db.update_one({"_id": user_id}, {"$set": {"expire_date": expire_date}})
    else:
        await mirror_db.insert_one({"_id": user_id, "expire_date": expire_date})

async def remove_mirror_premium(user_id):
    await mirror_db.delete_one({"_id": user_id})

async def check_mirror_premium(user_id):
    return await mirror_db.find_one({"_id": user_id})

async def mirror_premium_users():
    id_list = []
    async for data in mirror_db.find():
        id_list.append(data["_id"])
    return id_list

async def get_all_mirror_users_data():
    users = []
    async for data in mirror_db.find():
        users.append(data)
    return users

async def update_mirror_premium_expiry(user_id: int, expire_date: datetime.datetime):
    await mirror_db.update_one({"_id": user_id}, {"$set": {"expire_date": expire_date}}, upsert=True)

async def check_and_remove_expired_mirror_users():
    current_time = datetime.datetime.utcnow()
    async for data in mirror_db.find():
        expire_date = data.get("expire_date")
        if expire_date and expire_date < current_time:
            user_id = data["_id"]
            await remove_mirror_premium(user_id)
            print(f"Removed mirror user {user_id} due to expired plan / trial.")
            try:
                from toxic import app
                await app.send_message(
                    chat_id=user_id,
                    text=(
                        "⚠️ <b>TOPIC MIRROR ACCESS EXPIRED</b> ⚠️\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        "Your Topic Mirror / Demo Access has expired.\n\n"
                        "💬 <b>To purchase a full plan, contact:</b> @CrazyxDeveloper_Bot\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    ),
                    disable_web_page_preview=True
                )
            except Exception:
                pass

# ────── TOXIC_ID Security Keys Collection ──────
toxic_id_db = mongo.premium.toxic_id_db

async def add_toxic_id(toxic_code: str):
    await toxic_id_db.update_one({"_id": toxic_code.strip()}, {"$set": {"active": True}}, upsert=True)

async def remove_toxic_id(toxic_code: str):
    await toxic_id_db.delete_one({"_id": toxic_code.strip()})

async def is_valid_toxic_id(toxic_code: str):
    if not toxic_code:
        return False
    from config import MASTER_TOXIC_ID
    code_clean = str(toxic_code).strip()
    if MASTER_TOXIC_ID and code_clean == str(MASTER_TOXIC_ID).strip():
        return True
    data = await toxic_id_db.find_one({"_id": code_clean})
    return bool(data)

async def get_all_toxic_ids():
    codes = []
    async for data in toxic_id_db.find():
        codes.append(data["_id"])
    return codes


# ────── Global Free Access Management (Mirror & Batch) ──────
import re

free_access_db = mongo.premium.free_access_db

def parse_duration_to_seconds(text: str) -> int:
    """Parses duration strings like '1d', '24h', '1 day', '2 days', '6 hours', '30m' into seconds."""
    if not text:
        return 86400  # Default 1 day
    text = str(text).strip().lower()
    if text.isdigit():
        return int(text)
    match = re.match(r"^(\d+)\s*([a-zA-Z]+)$", text)
    if not match:
        return 86400
    val = int(match.group(1))
    unit = match.group(2)
    if unit in ('s', 'sec', 'secs', 'second', 'seconds'):
        return val
    elif unit in ('m', 'min', 'mins', 'minute', 'minutes'):
        return val * 60
    elif unit in ('h', 'hr', 'hrs', 'hour', 'hours'):
        return val * 3600
    elif unit in ('d', 'day', 'days'):
        return val * 86400
    elif unit in ('w', 'week', 'weeks'):
        return val * 86400 * 7
    elif unit in ('mo', 'mon', 'month', 'months'):
        return val * 86400 * 30
    return val * 86400

def format_time_remaining(seconds: int) -> str:
    """Formats seconds into human readable duration string."""
    if seconds is None:
        return "Permanent (No Expiry)"
    if seconds <= 0:
        return "Expired"
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or not parts:
        parts.append(f"{minutes}m")
    return " ".join(parts)

async def get_global_free_access() -> dict:
    """Retrieves current global free access state from MongoDB."""
    data = await free_access_db.find_one({"_id": "global_free_access"})
    if not data:
        data = {
            "_id": "global_free_access",
            "mirror_free": False,
            "mirror_expires_at": None,
            "batch_free": False,
            "batch_expires_at": None,
            "updated_at": None,
            "updated_by": None
        }
        await free_access_db.insert_one(data)
    return data

async def is_global_mirror_free() -> bool:
    """Returns True if global free mirror access is currently active."""
    data = await get_global_free_access()
    if not data.get("mirror_free"):
        return False
    expires_at = data.get("mirror_expires_at")
    if expires_at:
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if now_utc >= expires_at:
            # Auto-expire
            await free_access_db.update_one(
                {"_id": "global_free_access"},
                {"$set": {"mirror_free": False, "mirror_expires_at": None}}
            )
            return False
    return True

async def is_global_batch_free() -> bool:
    """Returns True if global free batch access is currently active."""
    data = await get_global_free_access()
    if not data.get("batch_free"):
        return False
    expires_at = data.get("batch_expires_at")
    if expires_at:
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        if now_utc >= expires_at:
            # Auto-expire
            await free_access_db.update_one(
                {"_id": "global_free_access"},
                {"$set": {"batch_free": False, "batch_expires_at": None}}
            )
            return False
    return True

async def set_global_free_access(feature: str, enabled: bool, duration_seconds: int = None, admin_id: int = None) -> dict:
    """
    Toggles global free access for 'mirror', 'batch', or 'both'/'all'.
    Duration in seconds. If duration_seconds is None and enabled=True, it stays active permanently until manually toggled OFF.
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    expires_at = (now_utc + datetime.timedelta(seconds=duration_seconds)) if (enabled and duration_seconds) else None

    updates = {"updated_at": now_utc, "updated_by": admin_id}
    if feature in ("mirror", "both", "all"):
        updates["mirror_free"] = bool(enabled)
        updates["mirror_expires_at"] = expires_at if enabled else None
    if feature in ("batch", "both", "all"):
        updates["batch_free"] = bool(enabled)
        updates["batch_expires_at"] = expires_at if enabled else None

    await free_access_db.update_one(
        {"_id": "global_free_access"},
        {"$set": updates},
        upsert=True
    )
    return await get_global_free_access()

 