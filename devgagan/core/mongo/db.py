# ---------------------------------------------------
# File Name: db.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan
# GitHub: https://github.com/devgaganin/
# Telegram: https://t.me/team_spy_pro
# YouTube: https://youtube.com/@dev_gagan
# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

from config import MONGO_DB
from motor.motor_asyncio import AsyncIOMotorClient as MongoCli
mongo = MongoCli(MONGO_DB)
db = mongo.user_data
db = db.users_data_db
async def get_data(user_id):
    x = await db.find_one({"_id": user_id})
    return x
async def set_thumbnail(user_id, thumb):
    data = await get_data(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": {"thumb": thumb}})
    else:
        await db.insert_one({"_id": user_id, "thumb": thumb})
async def set_caption(user_id, caption):
    data = await get_data(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": {"caption": caption}})
    else:
        await db.insert_one({"_id": user_id, "caption": caption})
async def replace_caption(user_id, replace_txt, to_replace):
    data = await get_data(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": {"replace_txt": replace_txt, "to_replace": to_replace}})
    else:
        await db.insert_one({"_id": user_id, "replace_txt": replace_txt, "to_replace": to_replace})
async def set_session(user_id, session):
    data = await get_data(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": {"session": session}})
    else:
        await db.insert_one({"_id": user_id, "session": session})
async def clean_words(user_id, new_clean_words):
    data = await get_data(user_id)
    if data and data.get("_id"):
        existing_words = data.get("clean_words", [])
         
        if existing_words is None:
            existing_words = []
        updated_words = list(set(existing_words + new_clean_words))
        await db.update_one({"_id": user_id}, {"$set": {"clean_words": updated_words}})
    else:
        await db.insert_one({"_id": user_id, "clean_words": new_clean_words})
async def remove_clean_words(user_id, words_to_remove):
    data = await get_data(user_id)
    if data and data.get("_id"):
        existing_words = data.get("clean_words", [])
        updated_words = [word for word in existing_words if word not in words_to_remove]
        await db.update_one({"_id": user_id}, {"$set": {"clean_words": updated_words}})
    else:
        await db.insert_one({"_id": user_id, "clean_words": []})
async def set_channel(user_id, chat_id):
    data = await get_data(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": {"chat_id": chat_id, "target_chat_id": chat_id}})
    else:
        await db.insert_one({"_id": user_id, "chat_id": chat_id, "target_chat_id": chat_id})
async def all_words_remove(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"clean_words": None}})
async def remove_thumbnail(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"thumb": None}})
async def remove_caption(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"caption": None}})
async def remove_replace(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"replace_txt": None, "to_replace": None}})
 
async def remove_session(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"session": None}})
async def remove_channel(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"chat_id": None, "target_chat_id": None}})
async def set_filter(user_id, media_type, status):
    data = await get_data(user_id)
    if data and data.get("_id"):
         
        filters = data.get("filters", {})
        filters[media_type] = status
        await db.update_one({"_id": user_id}, {"$set": {"filters": filters}})
    else:
        await db.insert_one({"_id": user_id, "filters": {media_type: status}})

async def delete_session(user_id):
    """Delete the session associated with the given user_id from the database."""
    await db.update_one({"_id": user_id}, {"$unset": {"session": ""}})

async def update_data(user_id, update_dict):
    data = await get_data(user_id)
    if data and data.get("_id"):
        await db.update_one({"_id": user_id}, {"$set": update_dict})
    else:
        update_dict["_id"] = user_id
        await db.insert_one(update_dict)

mappings_db = mongo.user_data.forward_mappings

async def add_forward_mapping(user_id, target_chat_id):
    await mappings_db.update_one(
        {"_id": user_id},
        {"$set": {"target_chat_id": target_chat_id}},
        upsert=True
    )

async def remove_forward_mapping(user_id):
    await mappings_db.delete_one({"_id": user_id})

async def get_forward_mapping(user_id):
    doc = await mappings_db.find_one({"_id": user_id})
    return doc.get("target_chat_id") if doc else None

async def get_all_forward_mappings():
    cursor = mappings_db.find({})
    results = []
    async for doc in cursor:
        results.append((doc["_id"], doc["target_chat_id"]))
    return results

async def load_all_thumbnails(thumbnail_dir):
    try:
        import os
        cursor = db.find({"thumb": {"$ne": None}})
        count = 0
        async for user_data in cursor:
            user_id = user_data.get("_id")
            thumb_data = user_data.get("thumb")
            if user_id and isinstance(thumb_data, (bytes, bytearray)):
                path = os.path.join(thumbnail_dir, f"{user_id}.jpg")
                with open(path, "wb") as f:
                    f.write(thumb_data)
                count += 1
        print(f"[INFO] Restored {count} custom thumbnails from MongoDB.")
    except Exception as e:
        print(f"[ERROR] Failed to restore custom thumbnails: {e}")

# Collection for global configuration settings
config_db = mongo.user_data.global_config

async def get_broadcast_config():
    doc = await config_db.find_one({"_id": "scheduled_broadcast"})
    if not doc:
        default = {
            "_id": "scheduled_broadcast",
            "message": "Hello! This is a scheduled broadcast message.",
            "interval_mins": 60,
            "is_active": False,
            "last_run": None
        }
        await config_db.insert_one(default)
        return default
    return doc

async def update_broadcast_config(update_dict):
    await config_db.update_one(
        {"_id": "scheduled_broadcast"},
        {"$set": update_dict},
        upsert=True
    )

# Collection for tracking auto-deletion of sent broadcast messages
deletions_db = mongo.user_data.scheduled_broadcast_deletions

async def add_broadcast_deletion(chat_id, message_id, delete_at):
    await deletions_db.insert_one({
        "chat_id": chat_id,
        "message_id": message_id,
        "delete_at": delete_at
    })

async def get_pending_deletions():
    cursor = deletions_db.find({})
    deletions = []
    async for doc in cursor:
        deletions.append(doc)
    return deletions

async def remove_broadcast_deletion(doc_id):
    await deletions_db.delete_one({"_id": doc_id})

# Collection for tracking chats (groups/channels) where the bot is active
joined_chats_db = mongo.user_data.joined_chats

async def add_joined_chat(chat_id, title):
    import datetime
    await joined_chats_db.update_one(
        {"_id": chat_id},
        {"$set": {"title": title, "updated_at": datetime.datetime.now()}},
        upsert=True
    )

async def get_all_joined_chats():
    cursor = joined_chats_db.find({})
    chats = []
    async for doc in cursor:
        chats.append({"chat_id": doc["_id"], "title": doc.get("title", "Unknown")})
    return chats

async def remove_joined_chat(chat_id):
    await joined_chats_db.delete_one({"_id": chat_id})