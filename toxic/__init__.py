# ---------------------------------------------------
# File Name: __init__.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

print("DEBUG: toxic/__init__.py started")
import asyncio
import logging
import re
import os
import random
import time
from pyrogram import Client
from pyrogram.enums import ParseMode 
from pyrogram.types import BotCommand
from pyrogram.errors import FloodWait as PyroFloodWait
from motor.motor_asyncio import AsyncIOMotorClient
import telethon.errors as tele_errors
from telethon import TelegramClient
from telethon.network import ConnectionTcpObfuscated
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
    sleep_threshold=120,
    max_concurrent_transmissions=128
)

# Multi-client pool for balancing
pro_clients = []
if STRINGS:
    for i, session in enumerate(STRINGS):
        # Setting no_updates=True prevents the client from crashing on unknown Story updates
        pro_clients.append(Client(f"pro_client_{i}", api_id=API_ID, api_hash=API_HASH, session_string=session, workers=150, sleep_threshold=120, no_updates=True, max_concurrent_transmissions=128))
    pro = pro_clients[0] # Backward compatibility
else:
    pro = None

# Global Semaphore for concurrency control
task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

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


async def start_telethon_client(client, bot_token, name="Telethon Client (sex)"):
    """Starts Telethon client with automated FloodWait handling."""
    max_retries = 10
    retry_count = 0
    while retry_count < max_retries:
        try:
            print(f"Starting {name}...")
            await client.start(bot_token=bot_token)
            print(f"✅ {name} started successfully!")
            return True
        except tele_errors.FloodWaitError as fw:
            wait_time = int(getattr(fw, "seconds", 60)) + 5
            print(f"⚠️ [{name}] FloodWait detected! Sleeping {wait_time}s before retrying...")
            await asyncio.sleep(wait_time)
            retry_count += 1
        except Exception as e:
            err_str = str(e)
            if "FloodWait" in err_str or "FLOOD_WAIT" in err_str or "wait of" in err_str:
                wait_match = re.search(r'(\d+)\s*seconds?', err_str)
                wait_time = int(wait_match.group(1)) + 5 if wait_match else 60
                print(f"⚠️ [{name}] FloodWait in error: sleeping {wait_time}s before retrying...")
                await asyncio.sleep(wait_time)
                retry_count += 1
            else:
                print(f"❌ {name} start failed: {e}")
                return False
    return False


async def start_pyrogram_client(client, name="Pyrogram Client"):
    """Starts Pyrogram client with automated FloodWait handling."""
    while True:
        try:
            print(f"Starting {name}...")
            await client.start()
            print(f"✅ {name} started successfully!")
            break
        except PyroFloodWait as fw:
            wait_time = int(getattr(fw, "value", getattr(fw, "x", 60))) + 5
            print(f"⚠️ [{name}] FloodWait detected! Waiting {wait_time}s before retrying...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            err_str = str(e)
            if "FLOOD_WAIT" in err_str or "FloodWait" in err_str:
                wait_match = re.search(r'(\d+)\s*seconds?', err_str)
                wait_time = int(wait_match.group(1)) + 5 if wait_match else 60
                print(f"⚠️ [{name}] FloodWait in error string: waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"❌ [{name}] Startup Error: {e}")
                raise e


async def restrict_bot():
    global BOT_ID, BOT_NAME, BOT_USERNAME
    try:
        await setup_database()
    except Exception as e:
        print(f"❌ Database Setup Error: {e}")
        print("Continuing without TTL index optimization...")
    
    # Start Telethon client with FloodWait resilience
    await start_telethon_client(sex, BOT_TOKEN)

    # Start Main Pyrogram Bot client with FloodWait resilience
    await start_pyrogram_client(app, "Main Bot (app)")

    getme = await app.get_me()
    BOT_ID = getme.id
    BOT_USERNAME = getme.username

    # 🔒 TOXIC_ID Security Lock Check
    from config import TOXIC_ID
    from toxic.core.mongo.plans_db import is_valid_toxic_id
    import sys

    print("\n🔍 Verifying TOXIC_ID Security Authorization Key...")
    if not await is_valid_toxic_id(TOXIC_ID):
        print("\n" + "=" * 65)
        print("❌ [SECURITY LOCK ALERT] INVALID OR MISSING TOXIC_ID!")
        print(f"   Provided TOXIC_ID: '{TOXIC_ID}'")
        print("🛡️ This bot repository is protected. You need a valid TOXIC_ID key")
        print("   provided by the Bot Owner to deploy or run this codebase.")
        print("💬 Contact Admin @CHOSEN_ONEx_bot to request authorization.")
        print("=" * 65 + "\n")
        sys.exit(1)
    else:
        print("✅ [SECURITY PASSED] TOXIC_ID Key Verified Successfully! Access Granted.\n")

    # Set Bot Commands
    try:
        await app.set_bot_commands([
            BotCommand("start", "🚀 𝗦𝘁𝗮𝗿𝘁 𝘁𝗵𝗲 𝗯𝗼𝘁"),
            BotCommand("guide", "📘 𝗜𝗻𝘁𝗲𝗿𝗮𝗰𝘁𝗶𝘃𝗲 𝘂𝘀𝗲𝗿 𝗴𝘂𝗶𝗱𝗲 & 𝗵𝗲𝗹𝗽"),
            BotCommand("plans", "💎 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 & 𝘁𝗼𝗽𝗶𝗰 𝗺𝗶𝗿𝗿𝗼𝗿 𝗽𝗹𝗮𝗻𝘀"),
            BotCommand("myplan", "⌛ 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗱𝗲𝘁𝗮𝗶𝗹𝘀"),
            BotCommand("topicmirror", "📁 𝗧𝗼𝗽𝗶𝗰 𝗠𝗶𝗿𝗿𝗼𝗿 𝗙𝗼𝗿𝘂𝗺 (₹𝟮𝟵𝟵 𝗣𝗹𝗮𝗻)"),
            BotCommand("topiclink", "🔗 𝗠𝗶𝗿𝗿𝗼𝗿 𝘀𝗽𝗲𝗰𝗶𝗳𝗶𝗰 𝘁𝗼𝗽𝗶𝗰-𝘁𝗼-𝘁𝗼𝗽𝗶𝗰"),

            BotCommand("scan_mirror", "🔎 𝗦𝗰𝗮𝗻 & 𝗰𝗼𝗺𝗽𝗮𝗿𝗲 𝘁𝗼𝗽𝗶𝗰 𝗰𝗼𝗻𝘁𝗲𝗻𝘁"),
            BotCommand("sync_mirror", "🔄 𝟭-𝗖𝗹𝗶𝗰𝗸 𝘀𝘆𝗻𝗰 𝗺𝗶𝘀𝘀𝗶𝗻𝗴 𝘁𝗼𝗽𝗶𝗰 𝗳𝗶𝗹𝗲𝘀"),
            BotCommand("cancel_mirror", "🛑 𝗖𝗮𝗻𝗰𝗲𝗹 𝗮𝗰𝘁𝗶𝘃𝗲 𝗺𝗶𝗿𝗿𝗼𝗿"),
            BotCommand("batch", "🪄 𝗕𝘂𝗹𝗸 𝗲𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗼𝗻"),
            BotCommand("cancel", "🚫 𝗖𝗮𝗻𝗰𝗲𝗹 𝗯𝗮𝘁𝗰𝗵"),
            BotCommand("login", "🔑 𝗔𝗰𝗰𝗲𝘀𝘀 𝘆𝗼𝘂𝗿 𝗮𝗰𝗰𝗼𝘂𝗻𝘁"),
            BotCommand("logout", "🚪 𝗦𝗲𝗰𝘂𝗿𝗲 𝗲𝘅𝗶𝘁"),
            BotCommand("settings", "⚙️ 𝗖𝘂𝘀𝘁𝗼𝗺𝗶𝘇𝗲 𝘀𝗲𝘁𝘁𝗶𝗻𝗴𝘀"),
            BotCommand("speedtest", "🚅 𝗦𝗽𝗲𝗲𝗱 𝘁𝗲𝘀𝘁"),
            BotCommand("terms", "📜 𝗧𝗲𝗿𝗺𝘀 & 𝗰𝗼𝗻𝗱𝗶𝘁𝗶𝗼𝗻𝘀"),
            BotCommand("addmirror", "👑 𝗔𝗱𝗱 𝗺𝗶𝗿𝗿𝗼𝗿 𝗮𝗰𝗰𝗲𝘀𝘀 (𝗔𝗱𝗺𝗶𝗻)"),
            BotCommand("remmirror", "👑 𝗥𝗲𝗺𝗼𝘃𝗲 𝗺𝗶𝗿𝗿𝗼𝗿 𝗮𝗰𝗰𝗲𝘀𝘀 (𝗔𝗱𝗺𝗶𝗻)"),
            BotCommand("checkmirror", "👑 𝗖𝗵𝗲𝗰𝗸 𝗺𝗶𝗿𝗿𝗼𝗿 𝗮𝗰𝗰𝗲𝘀𝘀 (𝗔𝗱𝗺𝗶𝗻)"),
            BotCommand("add", "➕ 𝗔𝗱𝗱 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿"),
            BotCommand("rem", "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿"),
            BotCommand("transfer", "💞 𝗚𝗶𝗳𝘁 𝗽𝗿𝗲𝗺𝗶𝘂𝗺"),
            BotCommand("stats", "📊 𝗕𝗼𝘁 𝘀𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀"),
            BotCommand("gcast", "⚡ 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗺𝗲𝘀𝘀𝗮𝗴𝗲")
        ])
    except Exception as cmd_err:
        print(f"⚠️ Failed to set bot commands: {cmd_err}")

    if getme.last_name:
        BOT_NAME = getme.first_name + " " + getme.last_name
    else:
        BOT_NAME = getme.first_name

    if STRINGS:
        for idx, client in enumerate(pro_clients):
            try:
                await start_pyrogram_client(client, f"Pro Client #{idx+1}")
            except Exception as pc_err:
                print(f"⚠️ Pro client #{idx+1} failed to start: {pc_err}")
    
    # Send clean startup notification on boot/restart
    try:
        owner_id = OWNER_ID[0] if isinstance(OWNER_ID, list) and OWNER_ID else OWNER_ID
        startup_msg = (
            "<blockquote><b>🚀 TOXIC BOT PRO ONLINE!</b></blockquote>\n\n"
            "<b>✅ Status:</b> Bot & Telethon Clients Started Successfully\n"
            "<b>🛡️ Active Features:</b>\n"
            "• PDF & Video Watermarking\n"
            "• High-Speed Save-Restricted Bypass\n"
            "• Topic Mirror & Auto Forum Sync (v2.5)\n"
            "• Real Speed Test & Dynamic UI\n\n"
            "⚡ <i>Ready to process extraction & mirroring requests!</i>"
        )
        if owner_id:
            await app.send_message(int(owner_id), startup_msg, parse_mode=enums.ParseMode.HTML)
            print("[INFO] Startup message sent to owner.")
        if LOG_GROUP:
            await app.send_message(int(LOG_GROUP), startup_msg, parse_mode=enums.ParseMode.HTML)
            print("[INFO] Startup message sent to log group.")
    except Exception as e:
        print(f"⚠️ Failed to send startup message: {e}")


def get_client():
    return random.choice(pro_clients) if pro_clients else None

loop.run_until_complete(restrict_bot())
