# ---------------------------------------------------
# File Name: users_db.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

from config import MONGO_DB
from motor.motor_asyncio import AsyncIOMotorClient as MongoCli


mongo = MongoCli(MONGO_DB)
db = mongo.users
db = db.users_db


async def get_users():
  user_list = []
  try:
    async for user in db.find({"user": {"$gt": 0}}):
      user_list.append(user['user'])
  except Exception as e:
    print(f"Error getting users from db: {e}")
  return user_list


async def get_user(user):
  users = await get_users()
  if user in users:
    return True
  else:
    return False

async def add_user(user):
  users = await get_users()
  if user in users:
    return
  else:
    try:
      await db.insert_one({"user": user})
    except Exception as e:
      print(f"Error adding user to db: {e}")


async def del_user(user):
  users = await get_users()
  if not user in users:
    return
  else:
    try:
      await db.delete_one({"user": user})
    except Exception as e:
      print(f"Error deleting user from db: {e}")
      
async def get_all_registered_users():
  users = await get_users()
  try:
    from toxic.core.mongo.db import db as settings_db
    async for doc in settings_db.find({}):
      if "_id" in doc:
        try:
          users.append(int(doc["_id"]))
        except ValueError:
          pass
  except Exception as e:
    print(f"Error getting users from settings db: {e}")
  return list(set(users))
    


