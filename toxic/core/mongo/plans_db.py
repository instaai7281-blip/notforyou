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

async def check_and_remove_expired_mirror_users():
    current_time = datetime.datetime.utcnow()
    async for data in mirror_db.find():
        expire_date = data.get("expire_date")
        if expire_date and expire_date < current_time:
            await remove_mirror_premium(data["_id"])
            print(f"Removed mirror user {data['_id']} due to expired plan.")
 