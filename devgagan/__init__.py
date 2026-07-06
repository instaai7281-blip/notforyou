# ---------------------------------------------------
# File Name: __init__.py
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

print("DEBUG: devgagan/__init__.py started")
import asyncio
import logging
from pyrogram import Client
from pyrogram.enums import ParseMode 
from pyrogram.types import BotCommand
from motor.motor_asyncio import AsyncIOMotorClient
import time
from config import API_ID, API_HASH, BOT_TOKEN, STRING, STRINGS, MONGO_DB, MAX_CONCURRENT_TASKS, OWNER_ID, LOG_GROUP

# DNS fix for MongoDB SRV resolution on Railway
try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ['8.8.8.8', '1.1.1.1']
except Exception as e:
    print(f"DNS Resolver fix failed: {e}")

print("--- RestrictBot: Optimized Build v2.5 Loading ---")

loop = asyncio.get_event_loop()

logging.basicConfig(
    format="[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s",
    level=logging.INFO,
)

botStartTime = time.time()

app = Client(
    "RestrictBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=300,
    parse_mode=ParseMode.MARKDOWN,
    sleep_threshold=60,
    max_concurrent_transmissions=128
)

# Multi-client pool for balancing
pro_clients = []
if STRINGS:
    for i, session in enumerate(STRINGS):
        # Setting no_updates=True prevents the client from crashing on unknown Story updates
        pro_clients.append(Client(f"pro_client_{i}", api_id=API_ID, api_hash=API_HASH, session_string=session, workers=150, sleep_threshold=60, no_updates=True, max_concurrent_transmissions=128))
    pro = pro_clients[0] # Backward compatibility
else:
    pro = None

# Global Semaphore for concurrency control
task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

import os
# Stale session cleanup to prevent DC migration hang
for suffix in ["", "-journal"]:
    path = f"sexrepo.session{suffix}"
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"Removed stale session file: {path}")
        except Exception as e:
            print(f"Failed to remove stale session file {path}: {e}")

from telethon import TelegramClient
from telethon.network import ConnectionTcpObfuscated
sex = TelegramClient(
    'sexrepo', 
    API_ID, 
    API_HASH,
    connection=ConnectionTcpObfuscated,
    connection_retries=15,
    retry_delay=5
)


# MongoDB setup
tclient = AsyncIOMotorClient(MONGO_DB)
tdb = tclient["telegram_bot"]  # Your database
token = tdb["tokens"]  # Your tokens collection

async def create_ttl_index():
    """Ensure the TTL index exists for the `tokens` collection."""
    await token.create_index("expires_at", expireAfterSeconds=0)

# Run the TTL index creation when the bot starts
async def setup_database():
    await create_ttl_index()
    print("MongoDB TTL index created.")

# You can call this in your main bot file before starting the bot

async def restrict_bot():
    global BOT_ID, BOT_NAME, BOT_USERNAME
    try:
        await setup_database()
    except Exception as e:
        print(f"❌ Database Setup Error: {e}")
        print("Continuing without TTL index optimization...")
    
    print("Starting Telethon Client (sex)...")
    try:
        await sex.start(bot_token=BOT_TOKEN)
        print("Telethon Client (sex) started successfully!")
    except Exception as e:
        print(f"❌ Telethon Client start failed: {e}")

    await app.start()
    getme = await app.get_me()
    BOT_ID = getme.id
    BOT_USERNAME = getme.username

    # Set Bot Commands
    await app.set_bot_commands([
        BotCommand("start", "🚀 𝗦𝘁𝗮𝗿𝘁 𝘁𝗵𝗲 𝗯𝗼𝘁"),
        BotCommand("batch", "🪄 𝗕𝘂𝗹𝗸 𝗲𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗼𝗻"),
        BotCommand("cancel", "🚫 𝗖𝗮𝗻𝗰𝗲𝗹 𝗯𝗮𝘁𝗰𝗵"),
        BotCommand("settings", "⚙️ 𝗖𝘂𝘀𝘁𝗼𝗺𝗶𝘇𝗲 𝘀𝗲𝘁𝘁𝗶𝗻𝗴𝘀"),
        BotCommand("help", "❓ 𝗛𝗲𝗹𝗽 𝗴𝘂𝗶𝗱𝗲"),
        BotCommand("login", "🔑 𝗔𝗰𝗰𝗲𝘀𝘀 𝘆𝗼𝘂𝗿 𝗮𝗰𝗰𝗼𝘂𝗻𝘁"),
        BotCommand("logout", "🚪 𝗦𝗲𝗰𝘂𝗿𝗲 𝗲𝘅𝗶𝘁"),
        BotCommand("plans", "💎 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗽𝗹𝗮𝗻𝘀"),
        BotCommand("refer", "💞 𝗥𝗲𝗳𝗲𝗿 𝗬𝗼𝘂𝗿 𝗙𝗿𝗶𝗲𝗻𝗱𝘀"),
        BotCommand("adl", "👻 𝗔𝘂𝗱𝗶𝗼 𝗱𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗲𝗿 (𝟯𝟬+ 𝘀𝗶𝘁𝗲𝘀)"),
        BotCommand("dl", "💀 𝗩𝗶𝗱𝗲𝗼 𝗱𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗲𝗿 (𝟯𝟬+ 𝘀𝗶𝘁𝗲𝘀)"),
        BotCommand("transfer", "💞 𝗚𝗶𝗳𝘁 𝗽𝗿𝗲𝗺𝗶𝘂𝗺"),
        BotCommand("myplan", "⌛ 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗱𝗲𝘁𝗮𝗶𝗹𝘀"),
        BotCommand("add", "➕ 𝗔𝗱𝗱 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿"),
        BotCommand("rem", "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿"),
        BotCommand("session", "🧵 𝗣𝘆𝗿𝗼𝗴𝗿𝗮𝗺 𝘃𝟮 𝗴𝗲𝗻𝗲𝗿𝗮𝘁𝗼𝗿"),
        BotCommand("stats", "📊 𝗕𝗼𝘁 𝘀𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀"),
        BotCommand("terms", "🥺 𝗧𝗲𝗿𝗺𝘀 & 𝗰𝗼𝗻𝗱𝗶𝘁𝗶𝗼𝗻𝘀"),
        BotCommand("speedtest", "🚅 𝗦𝗽𝗲𝗲𝗱 𝘁𝗲𝘀𝘁"),
        BotCommand("get", "🗄️ 𝗘𝘅𝗽𝗼𝗿𝘁 𝘂𝘀𝗲𝗿 𝗱𝗮𝘁𝗮"),
        BotCommand("lock", "🔒 𝗣𝗿𝗼𝘁𝗲𝗰𝘁 𝗰𝗵𝗮𝗻𝗻𝗲𝗹"),
        BotCommand("gcast", "⚡ 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗺𝗲𝘀𝘀𝗮𝗴𝗲")
    ])
    if getme.last_name:
        BOT_NAME = getme.first_name + " " + getme.last_name
    else:
        BOT_NAME = getme.first_name
    if STRINGS:
        for client in pro_clients:
            await client.start()
    
    # Send startup message
    try:
        print(f"Attempting to send startup message to owner: {OWNER_ID[0]}")
        startup_msg = "✅ **Bot Started Successfully!**\n\n🛡️ **Features Active:**\n- PDF Watermark\n- Media Filters\n- Rebranding Tag"
        await app.send_message(OWNER_ID[0], startup_msg)
        print("Startup message sent to owner.")
        if LOG_GROUP:
            print(f"Attempting to send startup message to log group: {LOG_GROUP}")
            await app.send_message(int(LOG_GROUP), startup_msg)
            print("Startup message sent to log group.")
    except Exception as e:
        print(f"Failed to send startup message: {e}")

import random
def get_client():
    return random.choice(pro_clients) if pro_clients else None

loop.run_until_complete(restrict_bot())
