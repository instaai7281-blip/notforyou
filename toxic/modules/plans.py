# ---------------------------------------------------
# File Name: plans.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

from datetime import timedelta
import pytz
import datetime, time
from toxic import app
import asyncio
from config import OWNER_ID
from toxic.core.func import get_seconds
from toxic.core.mongo import plans_db  
from pyrogram import filters 


# -*- coding: utf-8 -*-

@app.on_message(filters.command("rem") & filters.user(OWNER_ID))
async def remove_premium(client, message):
    if len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        user_mention = f"User (`{user_id}`)"
        try:
            user = await client.get_users(user_id)
            if user:
                user_mention = user.mention
        except Exception:
            pass

        # Check premium database
        data = await plans_db.check_premium(user_id)
        
        # Check active tokens database
        from motor.motor_asyncio import AsyncIOMotorClient
        from config import MONGO_DB
        tclient = AsyncIOMotorClient(MONGO_DB)
        tdb = tclient["telegram_bot"]
        tokens_col = tdb["tokens"]
        token_data = await tokens_col.find_one({"user_id": user_id})

        is_premium = data and data.get("_id")
        is_token_verified = token_data is not None

        if is_premium or is_token_verified:
            if is_premium:
                await plans_db.remove_premium(user_id)
            if is_token_verified:
                await tokens_col.delete_one({"user_id": user_id})

            await message.reply_text(
                f"⚙️ 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 ⚙️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🗑️ **PREMIUM ACCESS REVOKED**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"❌ **Status:** Premium access & active token sessions terminated.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            try:
                await client.send_message(
                    chat_id=user_id,
                    text=(
                        f"⚠️ **NOTICE: PREMIUM EXPIRED/TERMINATED** ⚠️\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Hello, your premium subscription or token session for \n"
                        f"🖤 **Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝** has been terminated or expired.\n\n"
                        f"💬 If you think this is a mistake or wish to renew, please contact the owner.\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )
                )
            except Exception:
                pass
        else:
            # Force cleanup of any records in both databases just in case
            await plans_db.remove_premium(user_id)
            await tokens_col.delete_one({"user_id": user_id})
            await message.reply_text(
                f"⚙️ 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 ⚙️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🧹 **FORCE CLEANED**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"🧹 **Action:** Force-removed from premium and token databases.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
    else:
        await message.reply_text(
            f"💤 **Boring...**\n\n"
            f"Usage: `/rem user_id`\n"
            f"_(Try getting it right next time!)_"
        )


@app.on_message(filters.command("myplan"))
async def myplan(client, message):
    user_id = message.from_user.id
    user = message.from_user.mention
    data = await plans_db.check_premium(user_id)  
    mirror_data = await plans_db.check_mirror_premium(user_id)
    
    current_time = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
    
    status_lines = [
        f"✨ 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 ✨",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"👑 **YOUR SUBSCRIPTION STATUS** 👑",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"👤 **User:** {user}",
        f"🆔 **ID:** `{user_id}`\n"
    ]
    
    has_any = False
    
    if data and data.get("expire_date"):
        has_any = True
        expiry = data.get("expire_date")
        expiry_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata"))
        expiry_str = expiry_ist.strftime("%d-%m-%Y %I:%M:%S %p")
        time_left = expiry_ist - current_time
        days = time_left.days
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        status_lines.append(f"⚡ **Standard Premium:** ✅ Active")
        status_lines.append(f"⏳ **Standard Expiry:** `{expiry_str}` IST ({days}d {hours}h {minutes}m left)\n")
    else:
        status_lines.append(f"⚡ **Standard Premium:** ❌ Inactive\n")
        
    if mirror_data and mirror_data.get("expire_date"):
        has_any = True
        m_expiry = mirror_data.get("expire_date")
        m_expiry_ist = m_expiry.astimezone(pytz.timezone("Asia/Kolkata"))
        m_expiry_str = m_expiry_ist.strftime("%d-%m-%Y %I:%M:%S %p")
        m_time_left = m_expiry_ist - current_time
        m_days = m_time_left.days
        m_hours, m_remainder = divmod(m_time_left.seconds, 3600)
        m_minutes, _ = divmod(m_remainder, 60)
        status_lines.append(f"🎛️ **Topic Mirror Plan (₹299):** ✅ Active")
        status_lines.append(f"⏳ **Mirror Expiry:** `{m_expiry_str}` IST ({m_days}d {m_hours}h {m_minutes}m left)\n")
    else:
        status_lines.append(f"🎛️ **Topic Mirror Plan (₹299):** ❌ Inactive\n")
        
    status_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if has_any:
        status_lines.append("🚀 _Thank you for being a valued subscriber!_")
    else:
        status_lines.append("Subscribe via `/plans` to unlock premium features & topic cloning! 🚀")
        
    await message.reply_text("\n".join(status_lines))


@app.on_message(filters.command("addmirror") & filters.user(OWNER_ID))
async def give_mirror_premium_cmd_handler(client, message):
    if len(message.command) == 4:
        time_zone = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
        current_time = time_zone.strftime("%d-%m-%Y %I:%M:%S %p")
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        user_mention = f"User (`{user_id}`)"
        user_name = "User"
        try:
            user = await client.get_users(user_id)
            if user:
                user_mention = user.mention
                user_name = user.mention
        except Exception:
            pass

        time_val = message.command[2] + " " + message.command[3]
        seconds = await get_seconds(time_val)
        if seconds > 0:
            expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)  
            await plans_db.add_mirror_premium(user_id, expiry_time)  
            data = await plans_db.check_mirror_premium(user_id)
            expiry = data.get("expire_date")   
            expiry_str_in_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%d-%m-%Y %I:%M:%S %p")         
            await message.reply_text(
                f"✨ 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 ✨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎛️ **TOPIC MIRROR PLAN ACTIVATED (₹299)** 🎛️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"⏳ **Duration:** `{time_val}`\n"
                f"📅 **Start:** `{current_time}` (IST)\n"
                f"⌛ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ ⚝_", 
                disable_web_page_preview=True
            )
            try:
                await client.send_message(
                    chat_id=user_id,
                    text=(
                        f"🎉 **CONGRATULATIONS! TOPIC MIRROR PLAN ACTIVATED** 🎉\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👋 Hey {user_name},\n"
                        f"Your account has been upgraded to **Topic Mirror Plan (₹299/month)**! 🎛️\n\n"
                        f"⚡ **UNLOCKED FEATURES:**\n"
                        f"  • Forum Topic Mirroring (/mirror) 📁\n"
                        f"  • Automatic Topic Creation & Mapping 🔄\n"
                        f"  • Auto Group Bio & Disclaimer Tagging 🏷️\n"
                        f"  • High-Speed Resume Checkpoints 🚀\n\n"
                        f"📈 **PLAN DETAILS:**\n"
                        f"  • **Duration:** `{time_val}`\n"
                        f"  • **Expiry Time:** `{expiry_str_in_ist}` (IST)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚀 _Use /mirror to start cloning topics now!_"
                    ), 
                    disable_web_page_preview=True              
                )
            except Exception:
                pass
        else:
            await message.reply_text("Invalid time format. Example: `/addmirror 123456789 1 month` or `30 days`")
    else:
        await message.reply_text("Usage: `/addmirror user_id duration` (e.g. `/addmirror 123456789 1 month` or `30 days`)")


@app.on_message(filters.command("remmirror") & filters.user(OWNER_ID))
async def remove_mirror_premium_cmd(client, message):
    if len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        user_mention = f"User (`{user_id}`)"
        try:
            user = await client.get_users(user_id)
            if user:
                user_mention = user.mention
        except Exception:
            pass

        await plans_db.remove_mirror_premium(user_id)
        await message.reply_text(
            f"🗑️ **TOPIC MIRROR ACCESS REVOKED**\n\n"
            f"👤 **User:** {user_mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"❌ **Status:** Topic Mirror plan access removed."
        )
    else:
        await message.reply_text("Usage: `/remmirror user_id`")


@app.on_message(filters.command("checkmirror") & filters.user(OWNER_ID))
async def check_mirror_premium_cmd(client, message):
    if len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        user_mention = f"User (`{user_id}`)"
        try:
            user = await client.get_users(user_id)
            if user:
                user_mention = user.mention
        except Exception:
            pass

        data = await plans_db.check_mirror_premium(user_id)  
        if data and data.get("expire_date"):
            expiry = data.get("expire_date") 
            expiry_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata"))
            expiry_str_in_ist = expiry_ist.strftime("%d-%m-%Y %I:%M:%S %p")            
            
            current_time = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
            time_left = expiry_ist - current_time
            
            days = time_left.days
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            time_left_str = f"{days} days, {hours} hours, {minutes} minutes"
            await message.reply_text(
                f"🎛️ 🖤 **TOPIC MIRROR PLAN DETAILS** 🖤 🎛️\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"⏰ **Remaining:** `{time_left_str}`\n"
                f"⌛ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            await message.reply_text(
                f"❌ **No Topic Mirror Plan Data Found!**\n\n"
                f"User `{user_id}` does not have an active Topic Mirror Plan (₹299)."
            )
    else:
        await message.reply_text("Usage: `/checkmirror user_id`")
        


@app.on_message(filters.command("check") & filters.user(OWNER_ID))
async def get_premium(client, message):
    if len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        user_mention = f"User (`{user_id}`)"
        try:
            user = await client.get_users(user_id)
            if user:
                user_mention = user.mention
        except Exception:
            pass

        data = await plans_db.check_premium(user_id)  
        if data and data.get("expire_date"):
            expiry = data.get("expire_date") 
            expiry_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata"))
            expiry_str_in_ist = expiry_ist.strftime("%d-%m-%Y %I:%M:%S %p")            
            
            current_time = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
            time_left = expiry_ist - current_time
            
            days = time_left.days
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            time_left_str = f"{days} days, {hours} hours, {minutes} minutes"
            await message.reply_text(
                f"🔍 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 🔍\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👑 **PREMIUM USER DETAILS** 👑\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"⏰ **Remaining:** `{time_left_str}`\n"
                f"⌛ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
        else:
            await message.reply_text(
                f"❌ **No Premium Data Found!**\n\n"
                f"User `{user_id}` is not registered as a premium user in the database."
            )
    else:
        await message.reply_text("Usage: `/check user_id`")


@app.on_message(filters.command("add") & filters.user(OWNER_ID))
async def give_premium_cmd_handler(client, message):
    if len(message.command) == 4:
        time_zone = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
        current_time = time_zone.strftime("%d-%m-%Y %I:%M:%S %p")
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        user_mention = f"User (`{user_id}`)"
        user_name = "User"
        try:
            user = await client.get_users(user_id)
            if user:
                user_mention = user.mention
                user_name = user.mention
        except Exception:
            pass

        time_val = message.command[2]+" "+message.command[3]
        seconds = await get_seconds(time_val)
        if seconds > 0:
            expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)  
            await plans_db.add_premium(user_id, expiry_time)  
            data = await plans_db.check_premium(user_id)
            expiry = data.get("expire_date")   
            expiry_str_in_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%d-%m-%Y %I:%M:%S %p")         
            await message.reply_text(
                f"✨ 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 ✨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌟 **PREMIUM ACCESS ACTIVATED** 🌟\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **User:** {user_mention}\n"
                f"🆔 **ID:** `{user_id}`\n"
                f"⏳ **Duration:** `{time_val}`\n"
                f"📅 **Start:** `{current_time}` (IST)\n"
                f"⌛ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ ⚝_", 
                disable_web_page_preview=True
            )
            try:
                await client.send_message(
                    chat_id=user_id,
                    text=(
                        f"🎉 **CONGRATULATIONS! PREMIUM ACTIVATED** 🎉\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👋 Hey {user_name},\n"
                        f"Thank you for supporting 🖤 **Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝**!\n"
                        f"Your account has been upgraded to Premium status. Enjoy! 👑\n\n"
                        f"⚡ **BENEFITS ACTIVATED:**\n"
                        f"  • Max download & upload speed 🚀\n"
                        f"  • Access to restricted content bypass 🔥\n"
                        f"  • Custom thumbnail support 📸\n"
                        f"  • Parallel transmission chunks ⚡\n\n"
                        f"📈 **YOUR PLAN DETAILS:**\n"
                        f"  • **Duration:** `{time_val}`\n"
                        f"  • **Expiry Time:** `{expiry_str_in_ist}` (IST)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚀 _Enjoy the maximum speed & limit!_"
                    ), 
                    disable_web_page_preview=True              
                )
            except Exception:
                pass
                    
        else:
            await message.reply_text("Invalid time format. Please use '1 day for days', '1 hour for hours', or '1 min for minutes', or '1 month for months' or '1 year for year'")
    else:
        await message.reply_text("Usage : /add user_id time (e.g., '1 day for days', '1 hour for hours', or '1 min for minutes', or '1 month for months' or '1 year for year')")


@app.on_message(filters.command("transfer"))
async def transfer_premium(client, message):
    if len(message.command) == 2:
        try:
            new_user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return

        sender_user_id = message.from_user.id
        
        sender_mention = f"User (`{sender_user_id}`)"
        new_mention = f"User (`{new_user_id}`)"
        
        try:
            sender_user = await client.get_users(sender_user_id)
            if sender_user:
                sender_mention = sender_user.mention
        except Exception:
            pass
            
        try:
            new_user = await client.get_users(new_user_id)
            if new_user:
                new_mention = new_user.mention
        except Exception:
            pass
        
        data = await plans_db.check_premium(sender_user_id)
        
        if data and data.get("_id"):
            expiry = data.get("expire_date")  
            
            await plans_db.remove_premium(sender_user_id)
            await plans_db.add_premium(new_user_id, expiry)
            
            expiry_str_in_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata")).strftime(
                "%d-%m-%Y %I:%M:%S %p"
            )
            time_zone = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
            current_time = time_zone.strftime("%d-%m-%Y %I:%M:%S %p")
            
            await message.reply_text(
                f"🔄 🖤 **𝗦𝗧𝗢𝗟𝗘𝗡 𝗛𝗔𝗣𝗣𝗜𝗡𝗘𝗦𝗦** 🖤 🔄\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔄 **PREMIUM PLAN TRANSFERRED**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 **From:** {sender_mention}\n"
                f"👤 **To:** {new_mention}\n"
                f"📅 **Transferred:** `{current_time}` (IST)\n"
                f"⏳ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ ⚝_"
            )
            
            try:
                await client.send_message(
                    chat_id=new_user_id,
                    text=(
                        f"🎉 **PREMIUM PLAN RECEIVED** 🎉\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"👋 Hey {new_mention},\n"
                        f"A premium subscription has been transferred to you!\n\n"
                        f"🛡️ **From:** {sender_mention}\n"
                        f"📅 **Date:** `{current_time}` (IST)\n"
                        f"⏳ **Expiry:** `{expiry_str_in_ist}` (IST)\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🚀 _Enjoy the unlimited speed and features!_"
                    )
                )
            except Exception:
                pass
        else:
            await message.reply_text("⚠️ **You are not a Premium user!**\n\nOnly Premium users can transfer their plans.")
    else:
        await message.reply_text("⚠️ **Usage:** /transfer user_id\n\nReplace `user_id` with the new user's ID.")


async def premium_remover():
    all_users = await plans_db.premium_users()
    removed_users = []
    not_removed_users = []

    for user_id in all_users:
        try:
            user = await app.get_users(user_id)
            chk_time = await plans_db.check_premium(user_id)

            if chk_time and chk_time.get("expire_date"):
                expiry_date = chk_time["expire_date"]

                if expiry_date <= datetime.datetime.now():
                    name = user.first_name
                    await plans_db.remove_premium(user_id)
                    try:
                        await app.send_message(
                            user_id, 
                            text=(
                                f"⚠️ **NOTICE: PREMIUM EXPIRED** ⚠️\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                f"Hello {name},\n"
                                f"Your subscription for 🖤 **Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝** has expired.\n\n"
                                f"Thank you for being with us! If you wish to renew, please contact the owner.\n"
                                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                            )
                        )
                    except Exception:
                        pass
                    print(f"{name}, your premium subscription has expired.")
                    removed_users.append(f"{name} ({user_id})")
                else:
                    name = user.first_name
                    current_time = datetime.datetime.now()
                    time_left = expiry_date - current_time

                    days = time_left.days
                    hours, remainder = divmod(time_left.seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)

                    if days > 0:
                        remaining_time = f"{days} days, {hours} hours, {minutes} minutes, {seconds} seconds"
                    elif hours > 0:
                        remaining_time = f"{hours} hours, {minutes} minutes, {seconds} seconds"
                    elif minutes > 0:
                        remaining_time = f"{minutes} minutes, {seconds} seconds"
                    else:
                        remaining_time = f"{seconds} seconds"

                    print(f"{name} : Remaining Time : {remaining_time}")
                    not_removed_users.append(f"{name} ({user_id})")
        except:
            await plans_db.remove_premium(user_id)
            print(f"Unknown users captured : {user_id} removed")
            removed_users.append(f"Unknown ({user_id})")

    return removed_users, not_removed_users


@app.on_message(filters.command("freez") & filters.user(OWNER_ID))
async def refresh_users(_, message):
    removed_users, not_removed_users = await premium_remover()
    # Create a summary message
    removed_text = "\n".join(removed_users) if removed_users else "No users removed."
    not_removed_text = "\n".join(not_removed_users) if not_removed_users else "No users remaining with premium."
    summary = (
        f"**Here is Summary...**\n\n"
        f"> **Removed Users:**\n{removed_text}\n\n"
        f"> **Not Removed Users:**\n{not_removed_text}"
    )
    await message.reply(summary)

# Admin Administration: Clear Premium, Ban, and Unban features
from toxic.core.mongo.db import is_user_banned, ban_user, unban_user

@app.on_message(filters.command("clearpremium") & filters.user(OWNER_ID))
async def clear_all_premium_cmd(client, message):
    try:
        await plans_db.db.delete_many({})
        await message.reply_text("✅ **All premium users have been successfully removed from the database.**")
    except Exception as e:
        await message.reply_text(f"❌ **Failed to clear premium users:** `{e}`")

@app.on_message(filters.command("ban") & filters.user(OWNER_ID))
async def ban_user_cmd(client, message):
    if len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return
        
        await ban_user(user_id)
        # Also remove premium and clean token sessions for security
        await plans_db.remove_premium(user_id)
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            from config import MONGO_DB
            tclient = AsyncIOMotorClient(MONGO_DB)
            tdb = tclient["telegram_bot"]
            await tdb["tokens"].delete_one({"user_id": user_id})
        except Exception:
            pass

        await message.reply_text(f"🚫 **User {user_id} has been banned from the bot.**")
    else:
        await message.reply_text("Usage: `/ban user_id`")

@app.on_message(filters.command("unban") & filters.user(OWNER_ID))
async def unban_user_cmd(client, message):
    if len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric ID.")
            return
        
        await unban_user(user_id)
        await message.reply_text(f"✅ **User {user_id} has been unbanned successfully.**")
    else:
        await message.reply_text("Usage: `/unban user_id`")

# Intercept all incoming messages from banned users at group -1 priority
@app.on_message(group=-1)
async def check_banned_user(client, message):
    user_id = message.from_user.id if message.from_user else None
    if not user_id:
        return
    # Exclude OWNER_ID from ban checks
    if user_id in OWNER_ID:
        return
    if await is_user_banned(user_id):
        await message.reply_text("❌ **You are banned from using this bot.**\n\n💬 Please contact the admin to unban.")
        message.stop_propagation()

# Intercept all incoming callback queries from banned users at group -1 priority
@app.on_callback_query(group=-1)
async def check_banned_user_callback(client, query):
    user_id = query.from_user.id
    if user_id in OWNER_ID:
        return
    if await is_user_banned(user_id):
        await query.answer("❌ You are banned from using this bot. Contact admin to unban.", show_alert=True)
        query.stop_propagation()


# ────── TOXIC_ID Security Management Commands (Owner Only) ──────
@app.on_message(filters.command("addtoxic") & filters.user(OWNER_ID))
async def add_toxic_cmd(client, message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ **Usage:** `/addtoxic <KEY_NAME>`\n\nExample: `/addtoxic TOXIC-PRO-998877`")
        return
    key = message.command[1].strip()
    await plans_db.add_toxic_id(key)
    await message.reply_text(f"✅ **TOXIC_ID Authorized Successfully!**\n\n🔑 **Key:** `{key}`\n\nAny bot container with `TOXIC_ID={key}` can now run!")

@app.on_message(filters.command("remtoxic") & filters.user(OWNER_ID))
async def rem_toxic_cmd(client, message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ **Usage:** `/remtoxic <KEY_NAME>`")
        return
    key = message.command[1].strip()
    await plans_db.remove_toxic_id(key)
    await message.reply_text(f"❌ **TOXIC_ID Revoked Successfully!**\n\n🔑 **Key:** `{key}`\n\nContainers running with this key will fail security check!")

@app.on_message(filters.command("checktoxic") & filters.user(OWNER_ID))
async def check_toxic_cmd(client, message):
    from config import MASTER_TOXIC_ID
    from pyrogram.enums import ParseMode
    keys = await plans_db.get_all_toxic_ids()
    master_key = MASTER_TOXIC_ID if MASTER_TOXIC_ID else "Not Set"
    msg = "<blockquote><b>🔐 ACTIVE TOXIC_ID AUTHORIZATION KEYS</b></blockquote>\n\n"
    msg += f"👑 <b>Master Default Key:</b> <code>{master_key}</code>\n\n"
    if keys:
        msg += "<b>📜 Additional Authorized Keys:</b>\n"
        for k in keys:
            msg += f"• <code>{k}</code>\n"
    else:
        msg += "<i>No extra keys in MongoDB database. (Only Master Key active)</i>"
    await message.reply_text(msg, parse_mode=ParseMode.HTML)
    
