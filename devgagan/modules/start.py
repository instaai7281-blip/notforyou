# ---------------------------------------------------
# File Name: start.py
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

from pyrogram import filters
from devgagan import app
from config import OWNER_ID
from devgagan.core.func import subscribe
import asyncio
from devgagan.core.func import *
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, BotCommand
from pyrogram.raw.functions.bots import SetBotInfo
from pyrogram.raw.types import InputUserSelf

from pyrogram.enums import ChatType

@app.on_message(filters.private, group=-1)
async def restrict_unauthorized_users(client, message: Message):
    # Authorization checks disabled - all commands and features unlocked for all users!
    return


@app.on_message(filters.command("set"))
async def set(_, message):
    if message.from_user.id not in OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return
     
    await app.set_bot_commands([
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("batch", "🫠 Extract in bulk"),
        BotCommand("login", "🔑 Get into the bot"),
        BotCommand("logout", "🚪 Get out of the bot"),
        BotCommand("token", "🎲 Get 3 hours free access"),
        BotCommand("adl", "👻 Download audio from 30+ sites"),
        BotCommand("dl", "💀 Download videos from 30+ sites"),
        BotCommand("freez", "🧊 Remove all expired user"),
        BotCommand("pay", "₹ Pay now to get subscription"),
        BotCommand("status", "⟳ Refresh Payment status"),
        BotCommand("transfer", "💘 Gift premium to others"),
        BotCommand("myplan", "⌛ Get your plan details"),
        BotCommand("add", "➕ Add user to premium"),
        BotCommand("rem", "➖ Remove from premium"),
        BotCommand("session", "🧵 Generate Pyrogramv2 session"),
        BotCommand("settings", "⚙️ Personalize things"),
        BotCommand("stats", "📊 Get stats of the bot"),
        BotCommand("plan", "🗓️ Check our premium plans"),
        BotCommand("terms", "🥺 Terms and conditions"),
        BotCommand("speedtest", "🚅 Speed of server"),
        BotCommand("lock", "🔒 Protect channel from extraction"),
        BotCommand("gcast", "⚡ Broadcast message to bot users"),
        BotCommand("help", "❓ If you're a noob, still!"),
        BotCommand("cancel", "🚫 Cancel batch process")
    ])
 
    await message.reply("✅ Commands configured successfully!")
 
 
 
 
help_pages = [
    (
        "📝 **Bot Commands Overview (1/2)**:\n\n"
        "💠 **/id To Get id**\n"
        "> Use This Command To Get Your id & Add Me in you Channel/Groups To Get That Chat id \n\n"
        "1. **/add userID**\n"
        "> Add user to premium (Owner only)\n\n"
        "2. **/rem userID**\n"
        "> Remove user from premium (Owner only)\n\n"
        "3. **/transfer userID**\n"
        "> Transfer premium to your beloved major purpose for resellers (Premium members only)\n\n"
        "4. **/get**\n"
        "> Get all user IDs (Owner only)\n\n"
        "5. **/lock**\n"
        "> Lock channel from extraction (Owner only)\n\n"
        "6. **/dl link**\n"
        "> Download videos (Not available in v3 if you are using)\n\n"
        "7. **/adl link**\n"
        "> Download audio (Not available in v3 if you are using)\n\n"
        "8. **/login**\n"
        "> Log into the bot for private channel access\n\n"
        "9. **/batch**\n"
        "> Bulk extraction for posts (After login)\n\n"
    ),
    (
        "📝 **Bot Commands Overview (2/2)**:\n\n"
        "10. **/logout**\n"
        "> Logout from the bot\n\n"
        "11. **/stats**\n"
        "> Get bot stats\n\n"
        "12. **/plan**\n"
        "> Check premium plans\n\n"
        "13. **/speedtest**\n"
        "> Test the server speed (not available in v3)\n\n"
        "14. **/terms**\n"
        "> Terms and conditions\n\n"
        "15. **/cancel**\n"
        "> Cancel ongoing batch process\n\n"
        "16. **/myplan**\n"
        "> Get details about your plans\n\n"
        "17. **/session**\n"
        "> Generate Pyrogram V2 session\n\n"
        "18. **/settings**\n"
        "> 1. SETCHATID : To directly upload in channel or group or user's dm use it with -100[chatID]\n"
        "> 2. SETRENAME : To add custom rename tag or username of your channels\n"
        "> 3. CAPTION : To add custom caption\n"
        "> 4. REPLACEWORDS : Can be used for words in deleted set via REMOVE WORDS\n"
        "> 5. RESET : To set the things back to default\n\n"
        "> You can set CUSTOM THUMBNAIL, PDF WATERMARK, VIDEO WATERMARK, SESSION-based login, etc. from settings\n\n"
        "**__Powered by CHOSEN ONE ⚝__**"
    )
]
 
 
async def send_or_edit_help_page(_, message, page_number):
    if page_number < 0 or page_number >= len(help_pages):
        return
 
     
    prev_button = InlineKeyboardButton("◀️ Previous", callback_data=f"help_prev_{page_number}")
    next_button = InlineKeyboardButton("Next ▶️", callback_data=f"help_next_{page_number}")
 
     
    buttons = []
    if page_number > 0:
        buttons.append(prev_button)
    if page_number < len(help_pages) - 1:
        buttons.append(next_button)
 
     
    keyboard = InlineKeyboardMarkup([buttons])
 
     
    await message.delete()
 
     
    await message.reply(
        help_pages[page_number],
        reply_markup=keyboard
    )
 
 
@app.on_message(filters.command("help"))
async def help(client, message):
    join = await subscribe(client, message)
    if join == 1:
        return
 
     
    await send_or_edit_help_page(client, message, 0)
 
 
@app.on_callback_query(filters.regex(r"help_(prev|next)_(\d+)"))
async def on_help_navigation(client, callback_query):
    action, page_number = callback_query.data.split("_")[1], int(callback_query.data.split("_")[2])
 
    if action == "prev":
        page_number -= 1
    elif action == "next":
        page_number += 1
 
     
    await send_or_edit_help_page(client, callback_query.message, page_number)
 
     
    await callback_query.answer()
 
 
@app.on_message(filters.command("terms") & filters.private)
async def terms(client, message):
    terms_text = (
        "> 📜 **Terms and Conditions** 📜\n\n"
        "✨ We are not responsible for user deeds, and we do not promote copyrighted content. If any user engages in such activities, it is solely their responsibility.\n"
        "✨ Upon purchase, we do not guarantee the uptime, downtime, or the validity of the plan. __Authorization and banning of users are at our discretion; we reserve the right to ban or authorize users at any time.__\n"
        "✨ Payment to us **__does not guarantee__** authorization for the /batch command. All decisions regarding authorization are made at our discretion and mood.\n"
    )
     
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/CHOSEN_ONEx_bot")],
        ]
    )
    await message.reply_text(terms_text, reply_markup=buttons)
 
 
@app.on_message(filters.command("plans") & filters.private)
async def plan(client, message):
    plan_text = (
        "⚡ **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦 𝗣𝗥𝗘𝗠𝗜𝗨𝗠** ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🚀 **PREMIUM BENEFITS:**\n"
        "✦ **No Verification:** No captcha or ads ⏳\n"
        "✦ **Bulk Uploads:** Queue up to **5000 files** at once 📂\n"
        "✦ **No Waiting Time:** Instant extraction (0s cooldown) ⏱️\n"
        "✦ **Unlimited Extraction:** From public/private chats 🎥\n"
        "✦ **Custom Thumbnails:** Save personalized thumbnails 📸\n"
        "✦ **Parallel Processing:** Max speed multi-chunk uploads ⚡\n\n"
        "👑 **AVAILABLE PLANS:**\n"
        "• **7-Day Plan:** ₹30 | $0.50 USDT\n"
        "• **15-Day Plan:** ₹60 | $0.90 USDT\n"
        "• **30-Day Plan:** ₹90 | $1.20 USDT (Max Speed 🚀)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📲 **To Upgrade:** Contact @CHOSEN_ONEx_bot\n"
        "💳 **Payments:** UPI, Amazon Gift Card, or USDT (Crypto)"
    )
   
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/CHOSEN_ONEx_bot")],
        ]
    )
    await message.reply_text(plan_text, reply_markup=buttons)
 
 
@app.on_callback_query(filters.regex("see_plan"))
async def see_plan(client, callback_query):
    plan_text = (
        "⚡ **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦 𝗣𝗥𝗘𝗠𝗜𝗨𝗠** ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💰 **Pricing & Upgrade Details:**\n"
        "• **7 Days:** ₹30 | $0.50 USDT\n"
        "• **15 Days:** ₹60 | $0.90 USDT\n"
        "• **30 Days:** ₹90 | $1.20 USDT\n\n"
        "🚀 **Key Features:**\n"
        "• Queue up to **5000 files** in a single batch!\n"
        "• Instant extraction (no cooldowns/captcha)\n"
        "• Premium fast multi-threaded engine ⚡\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📲 **To Upgrade:** Contact @CHOSEN_ONEx_bot"
    )
     
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 See Terms", callback_data="see_terms")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/CHOSEN_ONEx_bot")],
        ]
    )
    await callback_query.message.edit_text(plan_text, reply_markup=buttons)
 
 
@app.on_callback_query(filters.regex("see_terms"))
async def see_terms(client, callback_query):
    terms_text = (
        "> 📜 **Terms and Conditions** 📜\n\n"
        "✨ We are not responsible for user deeds, and we do not promote copyrighted content. If any user engages in such activities, it is solely their responsibility.\n"
        "✨ Upon purchase, we do not guarantee the uptime, downtime, or the validity of the plan. __Authorization and banning of users are at our discretion; we reserve the right to ban or authorize users at any time.__\n"
        "✨ Payment to us **__does not guarantee__** authorization for the /batch command. All decisions regarding authorization are made at our discretion and mood.\n"
    )
     
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 See Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/CHOSEN_ONEx_bot")],
        ]
    )
    await callback_query.message.edit_text(terms_text, reply_markup=buttons)

@app.on_message(filters.command("guide"))
async def guide_command(_, message: Message):
    image_url = "https://i.postimg.cc/BXkchVpY/image.jpg"  # Direct image URL from PostImage
    await message.reply_photo(
        photo=image_url,
        caption=(
            "📘 **How to Use Save Restricted Bot**\n\n"
            "If you want to Download Posts From Public Channels/Groups Just Send me **Post Link**\n"        
            "🔓 I'll unlock content from restricted channels or groups.\n\n"
            "Use /settings for Settings 🌝\n\n"
            "Use Next Button For Private Channels/Groups Guide 👇"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➡️ Next", callback_data="guide_page_1")]
        ]),
        quote=True
    )

# Second page callback handler
@app.on_callback_query(filters.regex("^guide_page_2$"))  # ^ and $ ensure exact match
async def guide_page_2(_, query: CallbackQuery):
    await query.message.edit_text(
        "🛠️ **More Features 😎**\n\n"
        "✅ Supported post formats:\n\n"
        "Public Link:\n `https://t.me/public_channel/1234`\n\n"
        "Private Link:\n `https://t.me/c/123456789/55`\n\n"
        "💡 Use /login only for private source.\n"
        "Use /id to get user or chat ID.\n\n"
        "Use /batch to download multiple posts at once 💀\n\n"
        "Powered by CHOSEN ONE ⚝",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="guide_page_1")]
        ])
    )

# Back to first page
@app.on_callback_query(filters.regex("^guide_page_1$"))  # ^ and $ ensure exact match
async def guide_page_1(_, query: CallbackQuery):
    await query.message.edit_text(
        "**📘 How to Use @SRC_PRO_BOT Guide 👇**\n\n"
        "💡 **For Private Channels/Groups**\n\n"
        "**How to download or forward posts from Private Channel/Groups Where Save is Restricted 💀**\n"
        "────────────────────\n"
        "➡️ Send /start\n"
        "➡️ Send /login\n"
        "────────────────────\n"
        "**Now 📲 Enter your mobile number\n like:**\n"
        "`+91XXXXXXXXXX`\n\n"
        "📨 You’ll get an OTP from Telegram official chat.\n"
        "────────────────────\n"
        "**🔢 Enter the OTP with spaces between digits.**\n"
        "Example: If OTP is `54321`,\n enter: `5 4 3 2 1`\n\n"
        "✅ You’ll be logged in successfully!\n"
        "────────────────────\n"
        "⚡ Now use /batch to download multiple posts.\n"
        "▭▭▭▭▭▭▭▭▭▭▭▭▭▭▭\n\n"
        "**हिंदी में 👇**\n\n"
        "**@SRC_PRO_BOT** का कैसे उपयोग करें\n"
        "/start कमांड भेजें फिर\n"
        "/login कमांड भेजें\n"
        "────────────────────\n"
        "📲 अब अपना मोबाइल नंबर दर्ज करें:\n"
        "`+91XXXXXXXXXX`\n\n"
        "────────────────────\n"
        "📨 Telegram की official चैट से OTP आएगा\n"     
        "🔢 OTP को स्पेस के साथ दर्ज करें\n"
        "उदाहरण: 5 4 3 2 1\n\n"
        "✅ अब आप सफलतापूर्वक बॉट में लॉग इन हो जाएंगे\n"
        "────────────────────\n"
        "⚡ एक बार में कई पोस्ट डाउनलोड करने के लिए /batch का उपयोग करें।"
        "▭▭▭▭▭▭▭▭▭▭▭▭▭▭▭\n\n",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("More Features 😎", callback_data="guide_page_2")]
        ])
)
