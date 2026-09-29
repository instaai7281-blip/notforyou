# ---------------------------------------------------
# File Name: db.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

import datetime
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

# Settings database helpers for global configs (e.g. auth channel)
settings_db = mongo.user_data.settings

async def get_auth_channels():
    doc = await settings_db.find_one({"_id": "auth_channels_list"})
    if doc:
        return doc.get("chat_ids", [])
    old = await settings_db.find_one({"_id": "auth_channel"})
    if old and old.get("chat_id"):
        return [old.get("chat_id")]
    return []

async def add_auth_channel(chat_id):
    channels = await get_auth_channels()
    if chat_id not in channels:
        channels.append(chat_id)
        await settings_db.update_one(
            {"_id": "auth_channels_list"},
            {"$set": {"chat_ids": channels}},
            upsert=True
        )

async def remove_auth_channel(chat_id):
    channels = await get_auth_channels()
    if chat_id in channels:
        channels.remove(chat_id)
        await settings_db.update_one(
            {"_id": "auth_channels_list"},
            {"$set": {"chat_ids": channels}},
            upsert=True
        )

async def clear_auth_channels():
    await settings_db.update_one(
        {"_id": "auth_channels_list"},
        {"$set": {"chat_ids": []}},
        upsert=True
    )
    await settings_db.delete_one({"_id": "auth_channel"})

async def set_bio_channel(chat_id):
    await settings_db.update_one(
        {"_id": "bio_channel"},
        {"$set": {"chat_id": chat_id}},
        upsert=True
    )

async def get_bio_channel():
    doc = await settings_db.find_one({"_id": "bio_channel"})
    return doc.get("chat_id") if doc else None

async def set_log_channel(chat_id):
    await settings_db.update_one(
        {"_id": "log_channel"},
        {"$set": {"chat_id": chat_id}},
        upsert=True
    )

async def get_log_channel():
    doc = await settings_db.find_one({"_id": "log_channel"})
    return doc.get("chat_id") if doc else None

# Ban / Unban helpers
async def ban_user(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"banned": True}}, upsert=True)

async def unban_user(user_id):
    await db.update_one({"_id": user_id}, {"$set": {"banned": False}}, upsert=True)

async def is_user_banned(user_id):
    x = await db.find_one({"_id": user_id})
    return x.get("banned", False) if x else False

# Collection for global broadcast configuration settings
config_db = mongo.user_data.global_config

async def get_broadcast_config():
    doc = await config_db.find_one({"_id": "scheduled_broadcast"})
    if not doc:
        default = {
            "_id": "scheduled_broadcast",
            "message": "Hello! This is a scheduled broadcast message.",
            "interval_mins": 60,
            "is_active": False,
            "last_run": None,
            "delete_after_mins": 0,
            "max_runs": 0,
            "run_count": 0
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

# Collection for persistent topic mirror mappings & checkpoints
mirror_db = mongo.user_data.topic_mirror_sessions

async def get_mirror_session(src_chat_id, tgt_chat_id):
    """Retrieves saved topic mappings and progress for a source-target pair."""
    doc = await mirror_db.find_one({"_id": f"{src_chat_id}_{tgt_chat_id}"})
    return doc if doc else {}

async def save_mirror_topic_mapping(src_chat_id, tgt_chat_id, src_topic_id, tgt_topic_id, title):
    """Saves or updates a topic mapping between source and target."""
    key = f"topics.{str(src_topic_id)}"
    await mirror_db.update_one(
        {"_id": f"{src_chat_id}_{tgt_chat_id}"},
        {
            "$set": {
                f"{key}.tgt_topic_id": tgt_topic_id,
                f"{key}.title": title,
                "updated_at": datetime.datetime.now()
            }
        },
        upsert=True
    )

async def update_mirror_topic_checkpoint(src_chat_id, tgt_chat_id, src_topic_id, last_msg_id):
    """Updates the highest message ID copied for a topic."""
    key = f"topics.{str(src_topic_id)}.last_msg_id"
    await mirror_db.update_one(
        {"_id": f"{src_chat_id}_{tgt_chat_id}"},
        {"$set": {key: last_msg_id, "updated_at": datetime.datetime.now()}},
        upsert=True
    )

async def reset_mirror_session(src_chat_id, tgt_chat_id):
    """Resets progress checkpoints for a source-target mirror session."""
    await mirror_db.delete_one({"_id": f"{src_chat_id}_{tgt_chat_id}"})

async def save_mirror_session_info(user_id, src_chat_id, tgt_chat_id, src_title, tgt_title):
    """Saves session metadata for quick resume buttons."""
    await mirror_db.update_one(
        {"_id": f"{src_chat_id}_{tgt_chat_id}"},
        {
            "$set": {
                "user_id": user_id,
                "src_chat_id": src_chat_id,
                "tgt_chat_id": tgt_chat_id,
                "src_title": src_title,
                "tgt_title": tgt_title,
                "updated_at": datetime.datetime.now()
            }
        },
        upsert=True
    )

async def get_user_mirror_sessions(user_id, limit=8):
    """Retrieves all saved mirror sessions for a user, sorted by last updated."""
    cursor = mirror_db.find(
        {"$or": [{"user_id": user_id}, {"user_id": {"$exists": False}}]}
    ).sort("updated_at", -1).limit(limit)
    sessions = []
    async for doc in cursor:
        sessions.append(doc)
    return sessions

async def delete_mirror_session(src_chat_id, tgt_chat_id):
    """Deletes a saved mirror session."""
    await mirror_db.delete_one({"_id": f"{src_chat_id}_{tgt_chat_id}"})

async def get_mirror_sessions_by_chat(chat_id):
    """Retrieves all saved mirror sessions associated with a target or source group ID."""
    try:
        c_id = int(chat_id)
        cursor = mirror_db.find({"$or": [{"tgt_chat_id": c_id}, {"src_chat_id": c_id}]})
        sessions = []
        async for doc in cursor:
            sessions.append(doc)
        return sessions
    except Exception as e:
        print(f"[MongoDB] get_mirror_sessions_by_chat error: {e}")
        return []



async def update_mirror_session_target(src_chat_id, old_tgt_chat_id, new_tgt_chat_id, new_tgt_title=""):
    """Updates the target chat ID and title for a saved mirror session."""
    old_doc = await mirror_db.find_one({"_id": f"{src_chat_id}_{old_tgt_chat_id}"})
    if old_doc:
        old_doc["_id"] = f"{src_chat_id}_{new_tgt_chat_id}"
        old_doc["tgt_chat_id"] = int(new_tgt_chat_id)
        if new_tgt_title:
            old_doc["tgt_title"] = new_tgt_title
        old_doc["updated_at"] = datetime.datetime.now()
        await mirror_db.delete_one({"_id": f"{src_chat_id}_{old_tgt_chat_id}"})
        await mirror_db.insert_one(old_doc)
        return True
    return False


DEFAULT_GROUP_BIO = (
    "Don't DM to anyone ⚠️\n\n"
    "https://telegra.ph/Disclaimer-cum-DMCA-09-13-2\n\n"
    "Contact: @CHOSEN_ONEx_bot"
)

async def get_custom_group_bio() -> str:
    """Retrieves configured global group bio/description from MongoDB, or default."""
    doc = await db.find_one({"_id": "global_group_bio"})
    if doc and doc.get("bio"):
        return doc["bio"]
    return DEFAULT_GROUP_BIO

async def set_custom_group_bio(bio: str):
    """Sets custom global group bio/description in MongoDB."""
    await db.update_one({"_id": "global_group_bio"}, {"$set": {"bio": bio}}, upsert=True)

async def reset_custom_group_bio():
    """Resets global group bio to default."""
    await db.delete_one({"_id": "global_group_bio"})