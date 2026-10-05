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
 