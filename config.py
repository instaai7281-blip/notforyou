# Note if you are trying to deploy on vps then directly fill values in (".env") or set them as environment variables

from os import getenv
from dotenv import load_dotenv

load_dotenv()

# VPS --- FILL COOKIES 🍪 in """ ... """ 

INST_COOKIES = """
# write up here insta cookies
"""
YTUB_COOKIES = """
# Netscape HTTP Cookie File
"""

API_ID = int(getenv("API_ID", "0"))
API_HASH = getenv("API_HASH", "")
BOT_TOKEN = getenv("BOT_TOKEN", "")
OWNER_ID = list(map(int, getenv("OWNER_ID", "").split()))
MONGO_DB = getenv("MONGO_DB", "")
LOG_GROUP = getenv("LOG_GROUP", "")
CHANNEL_ID = int(getenv("CHANNEL_ID", "0"))
FREEMIUM_LIMIT = int(getenv("FREEMIUM_LIMIT", "3"))
PREMIUM_LIMIT = int(getenv("PREMIUM_LIMIT", "5000"))
WEBSITE_URL = getenv("WEBSITE_URL", "upshrink.com")
AD_API = getenv("AD_API", "")
STRING = getenv("STRING", None)
STRINGS = getenv("STRINGS", "").split()
# If legacy STRING is present, add it to STRINGS list
if STRING and STRING not in STRINGS:
    STRINGS.append(STRING)

YT_COOKIES = getenv("YT_COOKIES", YTUB_COOKIES)
INSTA_COOKIES = getenv("INSTA_COOKIES", INST_COOKIES)
# Optimization: Number of concurrent tasks
MAX_CONCURRENT_TASKS = int(getenv("MAX_CONCURRENT_TASKS", "10"))

import os
THUMBNAIL_DIR = os.path.abspath("./thumbnails")
if not os.path.exists(THUMBNAIL_DIR):
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
