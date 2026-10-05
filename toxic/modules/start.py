# ---------------------------------------------------
# File Name: start.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

from pyrogram import filters
from toxic import app
from config import OWNER_ID
from toxic.core.func import subscribe
import asyncio
from toxic.core.func import *
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message, BotCommand
from pyrogram.raw.functions.bots import SetBotInfo
from pyrogram.raw.types import InputUserSelf

from pyrogram.enums import ChatType

@app.on_message(filters.private, group=-1)
async def restrict_unauthorized_users(client, message: Message):
    # Authorization checks disabled - all commands and features unlocked for all users!
    return


@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message: Message):
    join = await subscribe(client, message)
    if join == 1:
        return

    bot_username = get_bot_username()
    user_name = message.from_user.first_name if message.from_user else "User"

    start_text = (
        f"<blockquote><b>🚀 Welcome to Xtractor Bot Pro, {user_name}! 🖤</b></blockquote>\n\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\n\n"
        f"<blockquote><b>✨ WHAT I CAN DO FOR YOU:</b>\n"
        f"• <b>Ultra Fast Xtractor Pro:</b> Extract & sync content from private channels & groups!\n"
        f"• <b>Bulk Extraction (/batch):</b> Extract up to 5000 files in one single command!\n"
        f"• <b>Topic Mirror Forum Sync (/topicmirror):</b> Clone entire forum groups with auto-topic creation & 1-click update sync!\n"
        f"• <b>Direct Topic Link Mirror (/topiclink):</b> Mirror from 1 topic link directly into another!\n"
        f"• <b>Custom Watermarking & Metadata:</b> PDF watermarks, video thumbnails, custom captions!</blockquote>\n\n"
        f"<i>Just send any post link or tap a button below to get started! ☕🚀</i>"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Topic Mirror Hub", callback_data="tm_hub"), InlineKeyboardButton("🔗 Link Mirror", callback_data="tm_topiclink")],
        [InlineKeyboardButton("📘 User Guide", callback_data="guide_page_1"), InlineKeyboardButton("⚙️ Settings", callback_data="back_to_main")],
        [InlineKeyboardButton("💎 View Plans", callback_data="see_plan"), InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])

    image_url = "https://freeimage.host/i/n7cbXDX"
    try:
        await message.reply_photo(
            photo=image_url,
            caption=start_text,
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )
    except Exception as err:
        print(f"⚠️ Failed to send start photo: {err}")
        await message.reply_text(start_text, reply_markup=buttons, parse_mode=ParseMode.HTML)



@app.on_message(filters.command("set"))
async def set(_, message):
    if message.from_user.id not in OWNER_ID:
        await message.reply("You are not authorized to use this command.")
        return
     
    await app.set_bot_commands([
        BotCommand("start", "🚀 𝗦𝘁𝗮𝗿𝘁 𝘁𝗵𝗲 𝗯𝗼𝘁"),
        BotCommand("guide", "📘 𝗜𝗻𝘁𝗲𝗿𝗮𝗰𝘁𝗶𝘃𝗲 𝘂𝘀𝗲𝗿 𝗴𝘂𝗶𝗱𝗲 & 𝗵𝗲𝗹𝗽"),
        BotCommand("plans", "💎 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 & 𝘁𝗼𝗽𝗶𝗰 𝗺𝗶𝗿𝗿𝗼𝗿 𝗽𝗹𝗮𝗻𝘀"),
        BotCommand("myplan", "⌛ 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻 𝗱𝗲𝘁𝗮𝗶𝗹𝘀"),
        BotCommand("topicmirror", "📁 𝗧𝗼𝗽𝗶𝗰 𝗠𝗶𝗿𝗿𝗼𝗿 𝗙𝗼𝗿𝘂𝗺 𝗦𝘆𝗻𝗰"),
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
        BotCommand("mirrorusers", "🎛️ 𝗠𝗮𝗻𝗮𝗴𝗲 𝗺𝗶𝗿𝗿𝗼𝗿 𝘂𝘀𝗲𝗿𝘀 (𝗢𝘄𝗻𝗲𝗿)"),
        BotCommand("addmirror", "👑 𝗔𝗱𝗱 𝗺𝗶𝗿𝗿𝗼𝗿 𝗮𝗰𝗰𝗲𝘀𝘀 (𝗔𝗱𝗺𝗶𝗻)"),
        BotCommand("remmirror", "👑 𝗥𝗲𝗺𝗼𝘃𝗲 𝗺𝗶𝗿𝗿𝗼𝗿 𝗮𝗰𝗰𝗲𝘀𝘀 (𝗔𝗱𝗺𝗶𝗻)"),
        BotCommand("checkmirror", "👑 𝗖𝗵𝗲𝗰𝗸 𝗺𝗶𝗿𝗿𝗼𝗿 𝗮𝗰𝗰𝗲𝘀𝘀 (𝗔𝗱𝗺𝗶𝗻)"),
        BotCommand("add", "➕ 𝗔𝗱𝗱 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿"),
        BotCommand("rem", "➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝘂𝘀𝗲𝗿"),
        BotCommand("transfer", "💞 𝗚𝗶𝗳𝘁 𝗽𝗿𝗲𝗺𝗶𝘂𝗺"),
        BotCommand("stats", "📊 𝗕𝗼𝘁 𝘀𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀"),
        BotCommand("gcast", "📢 𝗚𝗿𝗼𝘂𝗽 𝗯𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁"),
        BotCommand("autobroadcast", "⚡ 𝗔𝘂𝘁𝗼 𝗯𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝘀𝗲𝘁𝘁𝗶𝗻𝗴𝘀")
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
        "⚝__**"
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
            [InlineKeyboardButton("💬 Contact Now", url="https://t.me/CrazyxDeveloper_Bot")],
        ]
    )
    await message.reply_text(terms_text, reply_markup=buttons)
 
 
def get_bot_username():
    if hasattr(app, "me") and app.me and app.me.username:
        return f"@{app.me.username}"
    return "@bot"


@app.on_message(filters.command(["plan", "plans"]))
async def plan(client, message):
    bot_username = get_bot_username()
    plan_text = (
        "<blockquote><b>💎 XTRACTOR BOT PRO — SUBSCRIPTION PLANS 💎</b></blockquote>\n\n"
        "<b>🔥 Unlock Unlimited High-Speed Extraction & Topic Syncing:</b>\n\n"
        "<blockquote><b>✨ STANDARD PREMIUM PLANS:</b>\n"
        "• <b>🥉 7 Days Plan:</b> ₹49  |  $0.70 USDT\n"
        "• <b>🥈 15 Days Plan:</b> ₹89  |  $1.20 USDT\n"
        "• <b>🥇 30 Days Plan:</b> ₹149  |  $1.90 USDT 🚀 <i>(Best Value)</i>\n"
        "• <b>💎 3 Months Plan:</b> ₹399  |  $5.00 USDT\n"
        "<i>Includes: High-Speed Batch extraction (/batch up to 5000 files), 0s Cooldown, Custom Thumbs & Watermarks!</i></blockquote>\n\n"
        "<blockquote><b>👑 SPECIAL TOPIC MIRROR PLAN (SEPARATE ACCESS):</b>\n"
        "• <b>📁 Topic Mirroring & Auto-Folder Plan:</b> Active via Admin\n"
        "<i>Includes: Forum Topic Cloning (/topicmirror), Auto Topic Creation & Mapping, Live Topic Scan & Compare (/scan_mirror), 1-Click Sync & Update Missing Content (/sync_mirror), Auto Group Bio & Disclaimer Tagging!</i>\n\n"
        "⚠️ <b>Important Note:</b> Topic Mirroring feature requires dedicated mirror access. Standard premium access does NOT include Topic Mirroring. Admin adds mirror access separately via <code>/addmirror</code>.</blockquote>\n\n"
        "<blockquote><b>💳 ACCEPTED PAYMENT METHODS:</b>\n"
        "• UPI (GPay / PhonePe / Paytm / BHIM)\n"
        "• Crypto (USDT BEP20 / TRC20 / TON)\n"
        "• Amazon Gift Cards</blockquote>\n\n"
        "📲 <b>To Buy Access:</b> Click <b>Contact Admin</b> below!"
    )
   
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Buy Plan / Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")],
            [InlineKeyboardButton("📘 User Guide", callback_data="guide_page_1"), InlineKeyboardButton("📜 Terms", callback_data="see_terms")],
        ]
    )
    await message.reply_text(plan_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("see_plan"))
async def see_plan(client, callback_query):
    bot_username = get_bot_username()
    plan_text = (
        "<blockquote><b>💎 XTRACTOR BOT PRO — SUBSCRIPTION PLANS 💎</b></blockquote>\n\n"
        "<b>🔥 Unlock Unlimited High-Speed Extraction & Topic Syncing:</b>\n\n"
        "<blockquote><b>✨ STANDARD PREMIUM PLANS:</b>\n"
        "• <b>🥉 7 Days Plan:</b> ₹49  |  $0.70 USDT\n"
        "• <b>🥈 15 Days Plan:</b> ₹89  |  $1.20 USDT\n"
        "• <b>🥇 30 Days Plan:</b> ₹149  |  $1.90 USDT 🚀 <i>(Best Value)</i>\n"
        "• <b>💎 3 Months Plan:</b> ₹399  |  $5.00 USDT\n"
        "<i>Includes: High-Speed Batch extraction (/batch up to 5000 files), 0s Cooldown, Custom Thumbs & Watermarks!</i></blockquote>\n\n"
        "<blockquote><b>👑 SPECIAL TOPIC MIRROR PLAN (SEPARATE ACCESS):</b>\n"
        "• <b>📁 Topic Mirroring & Auto-Folder Plan:</b> Active via Admin\n"
        "<i>Includes: Forum Topic Cloning (/topicmirror), Auto Topic Creation & Mapping, Live Topic Scan & Compare (/scan_mirror), 1-Click Sync & Update Missing Content (/sync_mirror), Auto Group Bio & Disclaimer Tagging!</i>\n\n"
        "⚠️ <b>Important Note:</b> Topic Mirroring feature requires dedicated mirror access. Standard premium access does NOT include Topic Mirroring. Admin adds mirror access separately via <code>/addmirror</code>.</blockquote>\n\n"
        "<blockquote><b>💳 ACCEPTED PAYMENT METHODS:</b>\n"
        "• UPI (GPay / PhonePe / Paytm / BHIM)\n"
        "• Crypto (USDT BEP20 / TRC20 / TON)\n"
        "• Amazon Gift Cards</blockquote>\n\n"
        "📲 <b>To Buy Access:</b> Click <b>Contact Admin</b> below!"
    )
     
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💬 Buy Plan / Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")],
            [InlineKeyboardButton("📘 User Guide", callback_data="guide_page_1"), InlineKeyboardButton("📜 Terms", callback_data="see_terms")],
        ]
    )
    await callback_query.message.edit_text(plan_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("see_terms"))
async def see_terms(client, callback_query):
    terms_text = (
        "<blockquote><b>📜 TERMS AND CONDITIONS</b></blockquote>\n\n"
        "<blockquote>• <b>Personal Use Only:</b> The bot services are intended strictly for personal utility and backup purposes.\n"
        "• <b>Fair Usage:</b> Spamming or abusing system resources may result in authorization suspension.\n"
        "• <b>No Refund Policy:</b> Payments are final once digital premium access is activated.\n"
        "• <b>Compliance:</b> Users are responsible for ensuring compliance with Telegram's Terms of Service.</blockquote>"
    )
     
    buttons = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💎 View Premium Plans", callback_data="see_plan")],
            [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")],
        ]
    )
    await callback_query.message.edit_text(terms_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("check_subscription"))
async def check_subscription_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    from config import CHANNEL_ID
    if CHANNEL_ID:
        try:
            user = await client.get_chat_member(CHANNEL_ID, user_id)
            if str(getattr(user, "status", "")).lower() in ["member", "administrator", "creator"]:
                await callback_query.answer("✅ Thank you for joining! Access granted.", show_alert=True)
                try:
                    await callback_query.message.delete()
                except Exception:
                    pass
                await callback_query.message.reply_text("🎉 **Welcome! Access granted. Send /start or any link to proceed!**")
                return
            elif str(getattr(user, "status", "")).lower() in ["kicked", "banned"]:
                await callback_query.answer("❌ You are banned from using this bot.", show_alert=True)
                return
        except UserNotParticipant:
            await callback_query.answer("❌ You have not joined the channel yet! Please join first.", show_alert=True)
            return
        except Exception as e:
            print(f"Sub check err: {e}")
    await callback_query.answer("✅ Access verified! Send /start to proceed.", show_alert=True)


@app.on_message(filters.command("guide"))
async def guide_command(_, message: Message):
    bot_username = get_bot_username()
    guide_p1_text = (
        f"<blockquote><b>📘 USER GUIDE — XTRACTOR BOT PRO (1/3)</b></blockquote>\n\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\n\n"
        "<blockquote><b>✨ 1. PUBLIC CHANNEL / GROUP POSTS:</b>\n"
        f"Send any public Telegram post link directly to <code>{bot_username}</code>.\n"
        "<i>Example:</i> <code>https://t.me/public_channel/1234</code></blockquote>\n\n"
        "<blockquote><b>🔒 2. PRIVATE CHANNEL / GROUP POSTS (XTRACTOR PRO):</b>\n"
        f"1️⃣ Send <code>/login</code> to <code>{bot_username}</code>.\n"
        "2️⃣ Enter your phone number with country code: <code>+91XXXXXXXXXX</code>\n"
        "3️⃣ Check Telegram official chat for your OTP code.\n"
        "4️⃣ Enter OTP with <b>spaces between digits</b> (e.g., for OTP <code>54321</code> ➡️ enter <code>5 4 3 2 1</code>).\n"
        "5️⃣ Once logged in, send private links <code>https://t.me/c/123456789/55</code> or use <code>/batch</code> for bulk extraction!</blockquote>\n\n"
        "<blockquote><b>🇮🇳 हिंदी गाइड:</b>\n"
        f"1️⃣ <code>{bot_username}</code> को <code>/login</code> भेजें।\n"
        "2️⃣ अपना नंबर <code>+91XXXXXXXXXX</code> टाइप करें।\n"
        "3️⃣ Telegram ऐप पर आया हुआ OTP <b>स्पेस देकर</b> लिखें (जैसे: <code>5 4 3 2 1</code>)।\n"
        "4️⃣ लॉगिन के बाद लिंक भेजें या <code>/batch</code> का उपयोग करें।</blockquote>"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Topic Mirror Guide ➡️", callback_data="guide_page_2")],
        [InlineKeyboardButton("⚡ Extra Features", callback_data="guide_page_3"), InlineKeyboardButton("💎 View Plans", callback_data="see_plan")],
        [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])
    image_url = "https://freeimage.host/i/n7cbXDX"
    try:
        await message.reply_photo(
            photo=image_url,
            caption=guide_p1_text,
            reply_markup=buttons,
            parse_mode=ParseMode.HTML
        )
    except Exception as err:
        print(f"⚠️ Failed to send guide photo: {err}")
        await message.reply_text(guide_p1_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("^guide_page_1$"))
async def guide_page_1(_, query: CallbackQuery):
    bot_username = get_bot_username()
    guide_p1_text = (
        f"<blockquote><b>📘 USER GUIDE — XTRACTOR BOT PRO (1/3)</b></blockquote>\n\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\n\n"
        "<blockquote><b>✨ 1. PUBLIC CHANNEL / GROUP POSTS:</b>\n"
        f"Send any public Telegram post link directly to <code>{bot_username}</code>.\n"
        "<i>Example:</i> <code>https://t.me/public_channel/1234</code></blockquote>\n\n"
        "<blockquote><b>🔒 2. PRIVATE CHANNEL / GROUP POSTS (XTRACTOR PRO):</b>\n"
        f"1️⃣ Send <code>/login</code> to <code>{bot_username}</code>.\n"
        "2️⃣ Enter your phone number with country code: <code>+91XXXXXXXXXX</code>\n"
        "3️⃣ Check Telegram official chat for your OTP code.\n"
        "4️⃣ Enter OTP with <b>spaces between digits</b> (e.g., for OTP <code>54321</code> ➡️ enter <code>5 4 3 2 1</code>).\n"
        "5️⃣ Once logged in, send private links <code>https://t.me/c/123456789/55</code> or use <code>/batch</code> for bulk extraction!</blockquote>\n\n"
        "<blockquote><b>🇮🇳 हिंदी गाइड:</b>\n"
        f"1️⃣ <code>{bot_username}</code> को <code>/login</code> भेजें।\n"
        "2️⃣ अपना नंबर <code>+91XXXXXXXXXX</code> टाइप करें।\n"
        "3️⃣ Telegram ऐप पर आया हुआ OTP <b>स्पेस देकर</b> लिखें (जैसे: <code>5 4 3 2 1</code>)।\n"
        "4️⃣ लॉगिन के बाद लिंक भेजें या <code>/batch</code> का उपयोग करें।</blockquote>"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Topic Mirror Guide ➡️", callback_data="guide_page_2")],
        [InlineKeyboardButton("⚡ Extra Features", callback_data="guide_page_3"), InlineKeyboardButton("💎 View Plans", callback_data="see_plan")],
        [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])
    try:
        await query.message.edit_caption(guide_p1_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.edit_text(guide_p1_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("^guide_page_2$"))
async def guide_page_2(_, query: CallbackQuery):
    bot_username = get_bot_username()
    guide_p2_text = (
        f"<blockquote><b>📁 USER GUIDE — TOPIC MIRROR FORUM SYNC (2/3)</b></blockquote>\n\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\n\n"
        "<blockquote><b>👑 EXCLUSIVE TOPIC MIRROR FEATURE:</b>\n"
        "Clones entire Forum Groups with automatic folder/topic creation, target mapping, instant resume checkpoints, and 1-click update sync!</blockquote>\n\n"
        "<blockquote><b>🛠️ STEP-BY-STEP SETUP:</b>\n"
        "1️⃣ Enable <b>Topics</b> in your Target Telegram Group settings.\n"
        f"2️⃣ Add <code>{bot_username}</code> to your Target Group and make it <b>Admin</b> with <i>Manage Topics</i> & <i>Send Messages</i> rights.\n"
        f"3️⃣ Send <code>/topicmirror</code> in <code>{bot_username}</code> private chat.\n"
        "4️⃣ Send Source Channel/Group Link & select Target Forum Group.</blockquote>\n\n"
        "<blockquote><b>🔎 LIVE SCAN & 1-CLICK SYNC (UPDATE MISSING CONTENT):</b>\n"
        "• <b>Scan & Compare (<code>/scan_mirror</code>):</b> Scans source & target groups, showing exact extracted vs remaining missing content per topic.\n"
        "• <b>1-Click Sync (<code>/sync_mirror</code>):</b> Automatically extracts missing posts without duplicating existing content!\n"
        "• <b>Topic Link Mirror (<code>/topiclink</code>):</b> Mirror content from one specific source topic link directly to another target topic link!</blockquote>\n\n"

        "⚠️ <i>Note: Requires active Topic Mirror Plan. Contact Admin via /plans to enable access.</i>"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Restricted Guide", callback_data="guide_page_1"), InlineKeyboardButton("Extra Features ➡️", callback_data="guide_page_3")],
        [InlineKeyboardButton("💎 View Plans", callback_data="see_plan"), InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])
    try:
        await query.message.edit_caption(guide_p2_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.edit_text(guide_p2_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("^guide_page_3$"))
async def guide_page_3(_, query: CallbackQuery):
    bot_username = get_bot_username()
    guide_p3_text = (
        f"<blockquote><b>⚡ USER GUIDE — COMMANDS & ADVANCED UTILITIES (3/3)</b></blockquote>\n\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\n\n"
        "<blockquote><b>🛠️ KEY COMMANDS:</b>\n"
        "• <code>/batch</code> — Extract range of posts (up to 5000 files in one go)\n"
        "• <code>/cancel</code> — Stop active batch download task\n"
        "• <code>/topicmirror</code> — Start Topic Mirror Forum Sync\n"
        "• <code>/cancel_mirror</code> — Stop active Topic Mirroring process\n"
        "• <code>/scan_mirror</code> — Live scan & compare topic content differences\n"
        "• <code>/sync_mirror</code> — 1-Click update missing topic files\n"
        "• <code>/speedtest</code> — Display exact download/upload server speeds\n"
        "• <code>/settings</code> — Customize thumbnail, watermarks, caption & metadata\n"
        "• <code>/myplan</code> — Check subscription validity & plan details\n"
        "• <code>/plans</code> — View premium plans & purchase details\n"
        "• <code>/id</code> — Get Telegram User ID or Chat ID\n"
        "• <code>/login</code> / <code>/logout</code> — Manage active user session</blockquote>"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Topic Mirror Guide", callback_data="guide_page_2")],
        [InlineKeyboardButton("💎 View Plans", callback_data="see_plan"), InlineKeyboardButton("📜 Terms & Conditions", callback_data="see_terms")],
        [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])
    try:
        await query.message.edit_caption(guide_p3_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    except Exception:
        await query.message.edit_text(guide_p3_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
