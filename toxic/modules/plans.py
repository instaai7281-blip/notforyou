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
import datetime, time, math
from toxic import app
import asyncio
from config import OWNER_ID
from toxic.core.func import get_seconds
from toxic.core.mongo import plans_db  
from toxic.core.mongo.db import (
    admin_filter,
    owner_filter,
    add_admin_db,
    remove_admin_db,
    get_all_admins_db,
    is_owner,
    is_admin_or_owner
)
from pyrogram import filters, Client, enums
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery


# -*- coding: utf-8 -*-

@app.on_message(filters.command("rem") & admin_filter)
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

        # Check active tokens database
        from motor.motor_asyncio import AsyncIOMotorClient
        from config import MONGO_DB
        tclient = AsyncIOMotorClient(MONGO_DB)
        tdb = tclient["telegram_bot"]
        tokens_col = tdb["tokens"]

        u_variants = [user_id]
        try:
            u_variants.append(int(user_id))
        except Exception:
            pass
        try:
            u_variants.append(str(user_id))
        except Exception:
            pass

        data = await plans_db.check_premium(user_id)
        mirror_data = await plans_db.check_mirror_premium(user_id)
        token_data = await tokens_col.find_one({"user_id": {"$in": u_variants}})

        is_premium = bool(data or mirror_data)
        is_token_verified = token_data is not None

        # Execute thorough removal across all subscription tables
        await plans_db.remove_premium(user_id)
        await plans_db.remove_mirror_premium(user_id)
        await tokens_col.delete_many({"user_id": {"$in": u_variants}})
        plans_db.invalidate_plans_cache()

        await message.reply_text(
            f"⚙️ ⚡ **XTRACTOR BOT PRO** ⚡ ⚙️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🗑️ **PREMIUM & MIRROR ACCESS REVOKED**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User:** {user_mention}\n"
            f"🆔 **ID:** `{user_id}`\n"
            f"❌ **Status:** Premium, Topic Mirror, & active token sessions terminated.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await client.send_message(
                chat_id=user_id,
                text=(
                    f"⚠️ **NOTICE: ACCESS TERMINATED** ⚠️\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Hello, your subscription for \n"
                    f"⚡ **Xtractor Bot Pro** ⚡ has been removed or expired.\n\n"
                    f"💬 If you wish to purchase/renew, please contact @CrazyxDeveloper_Bot.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
            )
        except Exception:
            pass
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
        f"✨ ⚡ **XTRACTOR BOT PRO** ⚡ ✨",
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
        status_lines.append(f"🎛️ **Topic Mirror Plan:** ✅ Active")
        status_lines.append(f"⏳ **Mirror Expiry:** `{m_expiry_str}` IST ({m_days}d {m_hours}h {m_minutes}m left)\n")
    else:
        status_lines.append(f"🎛️ **Topic Mirror Plan:** ❌ Inactive\n")
        
    status_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    if has_any:
        status_lines.append("🚀 _Thank you for being a valued subscriber!_")
    else:
        status_lines.append("Subscribe via `/plans` to unlock premium features & topic cloning! 🚀")
        
    await message.reply_text("\n".join(status_lines))


@app.on_message(filters.command("addmirror") & admin_filter)
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
                f"✨ ⚡ **XTRACTOR BOT PRO** ⚡ ✨\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎛️ **TOPIC MIRROR PLAN ACTIVATED** 🎛️\n"
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
                        f"Your account has been upgraded to **Topic Mirror Plan**! 🎛️\n\n"
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


# ─── 1-Hour Topic Mirror Demo Command (Hidden Admin/Owner Command) ───
@app.on_message(filters.command(["mirrordemo", "demomirror", "adddemo"]) & admin_filter)
async def give_mirror_demo_cmd_handler(client, message):
    """
    Hidden Owner/Admin command to provide 1-hour Topic Mirror trial demo to potential buyers.
    Automatically expires and revokes access exactly after 1 hour.
    Usage: /mirrordemo <user_id>  (or /demomirror <user_id> / /adddemo <user_id>)
    """
    if len(message.command) >= 2:
        try:
            target_user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid user ID.** Please provide a numeric user ID.\n\nUsage: `/mirrordemo <user_id>`")
            return

        user_mention = f"User (`{target_user_id}`)"
        user_name = "User"
        try:
            user = await client.get_users(target_user_id)
            if user:
                user_mention = user.mention
                user_name = user.first_name or "User"
        except Exception:
            pass

        # Calculate exact 1 hour expiry
        demo_seconds = 3600
        expiry_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=demo_seconds)
        
        await plans_db.add_mirror_premium(target_user_id, expiry_time)
        
        ist_now = datetime.datetime.now(pytz.timezone("Asia/Kolkata")).strftime("%I:%M:%S %p")
        expiry_ist = expiry_time.replace(tzinfo=pytz.utc).astimezone(pytz.timezone("Asia/Kolkata")).strftime("%I:%M:%S %p")

        # Admin confirmation
        admin_text = (
            f"🎉 <b>TOPIC MIRROR 1-HOUR DEMO ACTIVATED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {user_mention}\n"
            f"🆔 <b>ID:</b> <code>{target_user_id}</code>\n"
            f"⏳ <b>Duration:</b> <code>1 Hour (Trial Demo)</code>\n"
            f"📅 <b>Started:</b> <code>{ist_now}</code> (IST)\n"
            f"⌛ <b>Auto-Expires At:</b> <code>{expiry_ist}</code> (IST)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Access will be revoked automatically in 1 hour.</i>"
        )
        await message.reply_text(admin_text, parse_mode=ParseMode.HTML)

        # Direct notification to the user
        user_notice = (
            f"🎁 <b>CONGRATULATIONS! 1-HOUR TOPIC MIRROR DEMO UNLOCKED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👋 Hey <b>{user_name}</b>,\n"
            f"You have been granted a <b>1-Hour Free Demo</b> of the <b>Topic Mirroring Plan</b>! 🎛️\n\n"
            f"⚡ <b>Unlocked Demo Features:</b>\n"
            f"• 📁 1-Click Supergroup Topic Cloning (/topicmirror / /mirror)\n"
            f"• 🎯 Topic-to-Topic Direct Thread Syncing\n"
            f"• 🔄 Auto Topic Creation & Mapping\n"
            f"• 🚀 Zero-Bandwidth High Speed Copying\n\n"
            f"⏳ <b>Trial Validity:</b> <code>1 Hour</code> (Expires at: <code>{expiry_ist}</code> IST)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 <i>Send <code>/mirror</code> or <code>/topicmirror</code> in bot PM to test now!</i>"
        )
        try:
            await client.send_message(
                chat_id=target_user_id,
                text=user_notice,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception as notify_err:
            print(f"[MirrorDemo] Notice delivery failed: {notify_err}")
    else:
        await message.reply_text(
            "🎁 **1-Hour Topic Mirror Demo Utility**\n\n"
            "**Usage:** `/mirrordemo <user_id>`\n"
            "**Example:** `/mirrordemo 123456789`\n\n"
            "*(Grants 1 hour full Topic Mirror access and automatically removes access when the hour expires)*"
        )


# ─── Dynamic Bot Admins Management (Owner Only) ───

@app.on_message(filters.command(["addadmin", "promote", "newadmin"]) & owner_filter)
async def add_admin_cmd_handler(client, message):
    """Promotes a user to bot admin with full access to /admin commands. Owner only."""
    if len(message.command) >= 2:
        try:
            target_user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid User ID.** Please provide a numeric Telegram ID.\n\nUsage: `/addadmin <user_id>`")
            return

        user_mention = f"User (`{target_user_id}`)"
        user_name = "User"
        try:
            target_user = await client.get_users(target_user_id)
            if target_user:
                user_mention = target_user.mention
                user_name = target_user.first_name or "User"
        except Exception:
            pass

        await add_admin_db(target_user_id)

        admin_card = (
            f"👑 <b>NEW BOT ADMIN APPOINTED</b> 👑\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Admin:</b> {user_mention}\n"
            f"🆔 <b>User ID:</b> <code>{target_user_id}</code>\n"
            f"📅 <b>Promoted By:</b> {message.from_user.mention if message.from_user else 'Owner'}\n"
            f"⚡ <b>Permissions:</b> Full Access to <code>/admin</code> Commands\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>Dynamic admin stored persistently in database.</i>"
        )
        image_url = "https://freeimage.host/i/n04TxVa"
        try:
            await message.reply_photo(photo=image_url, caption=admin_card, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(admin_card, parse_mode=ParseMode.HTML)

        # Send DM notification to the new admin
        try:
            await client.send_message(
                chat_id=target_user_id,
                text=(
                    f"🎉 <b>CONGRATULATIONS! YOU ARE NOW A BOT ADMIN</b> 👑\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👋 Hey <b>{user_name}</b>,\n"
                    f"You have been granted <b>Admin Privileges</b> by the Bot Owner!\n\n"
                    f"⚡ <b>What you can do:</b>\n"
                    f"• Issue 1-Hour Topic Mirror Demos (/mirrordemo)\n"
                    f"• Add & Manage Topic Mirror Plans (/addmirror, /mirrorusers)\n"
                    f"• Add & Manage Standard Premium Plans (/add, /rem, /check)\n"
                    f"• Broadcast to users & groups (/gcast)\n"
                    f"• Access the Admin Control Panel via <code>/admin</code>\n\n"
                    f"🚀 <i>Send <code>/admin</code> in bot PM to view all available commands.</i>"
                ),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        except Exception:
            pass
    else:
        await message.reply_text(
            "👑 **Add Bot Admin Utility (Owner Only)**\n\n"
            "**Usage:** `/addadmin <user_id>`\n"
            "**Example:** `/addadmin 123456789`\n\n"
            "*(Promotes the specified user to bot admin with full `/admin` access)*"
        )


@app.on_message(filters.command(["remadmin", "demote", "deladmin", "removeadmin"]) & owner_filter)
async def remove_admin_cmd_handler(client, message):
    """Demotes / revokes a bot admin. Owner only."""
    if len(message.command) >= 2:
        try:
            target_user_id = int(message.command[1])
        except ValueError:
            await message.reply_text("❌ **Invalid User ID.** Please provide a numeric Telegram ID.\n\nUsage: `/remadmin <user_id>`")
            return

        user_mention = f"User (`{target_user_id}`)"
        try:
            target_user = await client.get_users(target_user_id)
            if target_user:
                user_mention = target_user.mention
        except Exception:
            pass

        await remove_admin_db(target_user_id)

        demote_card = (
            f"🗑️ <b>BOT ADMIN REMOVED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>User:</b> {user_mention}\n"
            f"🆔 <b>User ID:</b> <code>{target_user_id}</code>\n"
            f"❌ <b>Status:</b> Admin privileges revoked.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        image_url = "https://freeimage.host/i/n04TxVa"
        try:
            await message.reply_photo(photo=image_url, caption=demote_card, parse_mode=ParseMode.HTML)
        except Exception:
            await message.reply_text(demote_card, parse_mode=ParseMode.HTML)

        # Notify user
        try:
            await client.send_message(
                chat_id=target_user_id,
                text="⚠️ <b>Notice:</b> Your Bot Admin privileges have been revoked by the Owner.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    else:
        await message.reply_text(
            "🗑️ **Remove Bot Admin Utility (Owner Only)**\n\n"
            "**Usage:** `/remadmin <user_id>`\n"
            "**Example:** `/remadmin 123456789`"
        )


@app.on_message(filters.command(["admins", "adminlist", "listadmins"]) & admin_filter)
async def list_admins_cmd_handler(client, message):
    """Lists all owners and dynamic admins."""
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    dyn_admins = await get_all_admins_db()

    text_lines = [
        "👑 <b>BOT AUTHORIZED PERSONNEL LIST</b> 👑",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
        "⚡ <b>Primary Bot Owners (Config):</b>"
    ]
    for oid in owner_list:
        try:
            u = await client.get_users(oid)
            mention = u.mention if u else f"Owner (`{oid}`)"
        except Exception:
            mention = f"Owner (`{oid}`)"
        text_lines.append(f"• 👑 {mention} — <code>{oid}</code>")

    text_lines.append("\n🛡️ <b>Promoted Bot Admins (Database):</b>")
    if dyn_admins:
        for aid in dyn_admins:
            try:
                u = await client.get_users(aid)
                mention = u.mention if u else f"Admin (`{aid}`)"
            except Exception:
                mention = f"Admin (`{aid}`)"
            text_lines.append(f"• 🛡️ {mention} — <code>{aid}</code>")
    else:
        text_lines.append("<i>No dynamic admins added yet. Use <code>/addadmin &lt;user_id&gt;</code> to promote admins.</i>")

    text_lines.append(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    text_lines.append(f"📊 <b>Total Owners:</b> <code>{len(owner_list)}</code> | <b>Total Admins:</b> <code>{len(dyn_admins)}</code>")

    image_url = "https://freeimage.host/i/n04TxVa"
    full_text = "\n".join(text_lines)
    try:
        await message.reply_photo(photo=image_url, caption=full_text, parse_mode=ParseMode.HTML)
    except Exception:
        await message.reply_text(full_text, parse_mode=ParseMode.HTML)


# ─── Admin Help & Control Panel Command (Guarded: Owner/Admin Only) ───
@app.on_message(filters.command(["admin", "adminhelp", "panel", "owner"]))
async def admin_panel_cmd_handler(client, message):
    """
    Admin control panel command that displays all secret & admin commands.
    Restricted to Owner and Promoted Admins.
    """
    user = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    user_id = user.id if user else 0
    if not is_admin_or_owner(user_id):
        await message.reply_text(
            f"🔒 <b>Access Denied:</b> Admin Control Panel is restricted to Bot Owners and Admins.\n\n"
            f"👤 <b>Your ID:</b> <code>{user_id}</code>\n"
            f"<i>If you are the bot owner, make sure your ID is set in <code>OWNER_ID</code>.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    admin_text = (
        f"<blockquote>👑 <b>XTRACTOR PRO — ADMIN CONTROL PANEL</b> 👑</blockquote>\n\n"
        f"👋 <b>Welcome Admin / Owner!</b>\n"
        f"Here is your secret list of admin commands and their usages:\n\n"
        f"<blockquote>👑 <b>OWNER EXCLUSIVE COMMANDS</b>\n"
        f"• <code>/addadmin &lt;user_id&gt;</code> — Promote user to Bot Admin\n"
        f"• <code>/remadmin &lt;user_id&gt;</code> — Demote / revoke Bot Admin\n"
        f"• <code>/admins</code> — List all active bot owners & admins</blockquote>\n\n"
        f"<blockquote>🎁 <b>GLOBAL FREE ACCESS (FREE TRIAL FOR ALL USERS)</b>\n"
        f"• <code>/freeaccess</code> — Interactive dashboard to toggle Free Mirror & Batch for all bot users\n"
        f"• <code>/freeaccess on 1 day</code> — Give 1 Day Free Mirror & Batch to everyone\n"
        f"• <code>/freeaccess off</code> — Turn OFF all free access immediately</blockquote>\n\n"
        f"<blockquote>🎁 <b>1-HOUR TRIAL DEMO (HIDDEN)</b>\n"
        f"• <code>/mirrordemo &lt;user_id&gt;</code> — Give 1-hour Topic Mirror trial demo (auto-expires in 60m)\n"
        f"• <i>Aliases:</i> <code>/demomirror</code>, <code>/adddemo</code></blockquote>\n\n"
        f"<blockquote>🎛️ <b>TOPIC MIRROR MANAGEMENT</b>\n"
        f"• <code>/addmirror &lt;user_id&gt; &lt;duration&gt;</code> — Add Topic Mirror access\n"
        f"  <i>Example:</i> <code>/addmirror 123456789 1 month</code> or <code>30 days</code>\n"
        f"• <code>/remmirror &lt;user_id&gt;</code> — Revoke Topic Mirror access\n"
        f"• <code>/checkmirror &lt;user_id&gt;</code> — Check Topic Mirror plan details\n"
        f"• <code>/mirrorusers</code> — Interactive dashboard for all mirror subscribers</blockquote>\n\n"
        f"<blockquote>💎 <b>STANDARD PREMIUM MANAGEMENT</b>\n"
        f"• <code>/add &lt;user_id&gt; &lt;duration&gt;</code> — Add Standard Premium access\n"
        f"  <i>Example:</i> <code>/add 123456789 1 month</code>\n"
        f"• <code>/rem &lt;user_id&gt;</code> — Remove Standard Premium\n"
        f"• <code>/check &lt;user_id&gt;</code> — Check standard premium status\n"
        f"• <code>/transfer &lt;to_user_id&gt;</code> — Transfer premium subscription\n"
        f"• <code>/stats</code> — Bot statistics & server specs\n"
        f"• <code>/getusers</code> — Interactive premium user manager</blockquote>\n\n"
        f"<blockquote>📢 <b>BROADCAST & CONFIGURATION</b>\n"
        f"• <code>/gcast &lt;msg/reply&gt;</code> — Broadcast to all users & groups\n"
        f"• <code>/autobroadcast</code> — Smart Auto-Broadcast setup\n"
        f"• <code>/setmainchannel &lt;link/id&gt;</code> — Update main channel / force sub\n"
        f"• <code>/set</code> — Register public bot commands in Telegram menu\n"
        f"• <code>/restart</code> — Restart bot process</blockquote>\n\n"
        f"<i>⚠️ Keep these commands private. Only authorized admins can run them.</i>"
    )

    image_url = "https://freeimage.host/i/n04TxVa"
    try:
        await message.reply_photo(
            photo=image_url,
            caption=admin_text,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        print(f"[AdminPanel] Error sending photo: {e}")
        await message.reply_text(admin_text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command("remmirror") & admin_filter)
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


@app.on_message(filters.command("checkmirror") & admin_filter)
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
                f"User `{user_id}` does not have an active Topic Mirror Plan."
            )
    else:
        await message.reply_text("Usage: `/checkmirror user_id`")


# -------------------------------------------------------------
# INTERACTIVE OWNER MIRROR USERS MANAGER (/mirrorusers, /musers)
# -------------------------------------------------------------

async def build_mirror_users_panel(client, page: int = 1):
    all_users = await plans_db.get_all_mirror_users_data()
    current_time_ist = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
    
    if not all_users:
        text = (
            "🎛️ **Topic Mirror Users Manager**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "ℹ️ **No active Topic Mirror users found in database.**\n\n"
            "Use `/addmirror <user_id> <time>` to add a new mirror user."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="muser_list_1")]
        ])
        return text, kb

    total_users = len(all_users)
    items_per_page = 5
    max_pages = math.ceil(total_users / items_per_page)
    page = max(1, min(page, max_pages))
    
    start_idx = (page - 1) * items_per_page
    page_users = all_users[start_idx:start_idx + items_per_page]

    text = (
        f"🎛️ **Topic Mirror Users Manager** (Total: `{total_users}`)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Click on any user below to **increase/decrease time** or **remove access**:\n\n"
    )

    buttons = []
    for u in page_users:
        u_id = u["_id"]
        exp_utc = u.get("expire_date")
        time_left_str = "Expired ❌"
        if exp_utc:
            try:
                exp_ist = exp_utc.astimezone(pytz.timezone("Asia/Kolkata"))
                if exp_ist > current_time_ist:
                    diff = exp_ist - current_time_ist
                    days = diff.days
                    hours = diff.seconds // 3600
                    time_left_str = f"{days}d {hours}h left ✅"
            except Exception:
                pass
        
        buttons.append([
            InlineKeyboardButton(f"👤 User {u_id} • {time_left_str}", callback_data=f"muser_view_{u_id}_{page}")
        ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"muser_list_{page-1}"))
    nav_row.append(InlineKeyboardButton(f"📄 Page {page}/{max_pages}", callback_data="muser_nop"))
    if page < max_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"muser_list_{page+1}"))
    
    if nav_row:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton("🔄 Refresh List", callback_data=f"muser_list_{page}"),
        InlineKeyboardButton("❌ Close", callback_data="muser_close")
    ])
    
    return text, InlineKeyboardMarkup(buttons)


async def build_single_mirror_user_panel(client, user_id: int, page: int = 1):
    u_data = await plans_db.check_mirror_premium(user_id)
    if not u_data:
        text = f"❌ **User `{user_id}` is not in the Topic Mirror list.**"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to List", callback_data=f"muser_list_{page}")]])
        return text, kb

    user_mention = f"User (`{user_id}`)"
    try:
        u_obj = await client.get_users(user_id)
        if u_obj:
            user_mention = f"{u_obj.mention} (`{user_id}`)"
    except Exception:
        pass

    exp_utc = u_data.get("expire_date")
    current_time_ist = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
    
    exp_str = "N/A"
    time_left_str = "Expired ❌"
    if exp_utc:
        try:
            exp_ist = exp_utc.astimezone(pytz.timezone("Asia/Kolkata"))
            exp_str = exp_ist.strftime("%d-%m-%Y %I:%M:%S %p")
            if exp_ist > current_time_ist:
                diff = exp_ist - current_time_ist
                days = diff.days
                hours, rem = divmod(diff.seconds, 3600)
                mins, _ = divmod(rem, 60)
                time_left_str = f"`{days} days, {hours} hours, {mins} mins remaining`"
            else:
                time_left_str = "❌ **Plan Expired**"
        except Exception:
            pass

    text = (
        f"🎛️ **Manage Topic Mirror User**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 **User:** {user_mention}\n"
        f"🆔 **User ID:** `{user_id}`\n"
        f"⌛ **Expiry Date:** `{exp_str}` (IST)\n"
        f"⏳ **Status:** {time_left_str}\n\n"
        f"Use the buttons below to **increase time**, **decrease time**, or **revoke access**:"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ +7 Days", callback_data=f"muser_adddays_{user_id}_7_{page}"),
            InlineKeyboardButton("➕ +30 Days", callback_data=f"muser_adddays_{user_id}_30_{page}"),
            InlineKeyboardButton("➕ +1 Day", callback_data=f"muser_adddays_{user_id}_1_{page}")
        ],
        [
            InlineKeyboardButton("➖ -7 Days", callback_data=f"muser_subdays_{user_id}_7_{page}"),
            InlineKeyboardButton("➖ -1 Day", callback_data=f"muser_subdays_{user_id}_1_{page}")
        ],
        [
            InlineKeyboardButton("❌ Revoke Mirror Access", callback_data=f"muser_revoke_{user_id}_{page}")
        ],
        [
            InlineKeyboardButton("🔙 Back to List", callback_data=f"muser_list_{page}"),
            InlineKeyboardButton("🔄 Refresh", callback_data=f"muser_view_{user_id}_{page}")
        ]
    ])
    return text, kb


@app.on_message(filters.command(["mirrorusers", "musers", "manage_mirror"]) & admin_filter)
async def mirror_users_manager_cmd(client, message):
    text, kb = await build_mirror_users_panel(client, page=1)
    await message.reply_text(text, reply_markup=kb)


@app.on_callback_query(filters.regex(r"^muser_"))
async def mirror_users_callback_handler(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    if not is_admin_or_owner(user_id):
        await query.answer("❌ Access Denied!", show_alert=True)
        return

    data = query.data
    if data == "muser_close":
        await query.message.delete()
        return
    elif data == "muser_nop":
        await query.answer()
        return

    parts = data.split("_")
    action = parts[1]

    if action == "list":
        page = int(parts[2]) if len(parts) > 2 else 1
        text, kb = await build_mirror_users_panel(client, page=page)
        await query.message.edit_text(text, reply_markup=kb)

    elif action == "view":
        target_uid = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 1
        text, kb = await build_single_mirror_user_panel(client, target_uid, page=page)
        await query.message.edit_text(text, reply_markup=kb)

    elif action == "adddays":
        target_uid = int(parts[2])
        days_to_add = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 1

        u_data = await plans_db.check_mirror_premium(target_uid)
        curr_utc = datetime.datetime.utcnow()
        if u_data and u_data.get("expire_date"):
            old_exp = u_data["expire_date"]
            start_exp = old_exp if old_exp > curr_utc else curr_utc
        else:
            start_exp = curr_utc

        new_exp = start_exp + datetime.timedelta(days=days_to_add)
        await plans_db.update_mirror_premium_expiry(target_uid, new_exp)

        exp_ist_str = new_exp.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%d-%m-%Y %I:%M:%S %p")
        await query.answer(f"✅ Added +{days_to_add} days for user {target_uid}!", show_alert=True)

        try:
            await client.send_message(
                target_uid,
                f"🎉 **TOPIC MIRROR PLAN EXTENDED!**\n\n"
                f"Your Topic Mirror Plan has been extended by **+{days_to_add} days** by Admin.\n"
                f"⏳ **New Expiry Date:** `{exp_ist_str}` (IST)"
            )
        except Exception:
            pass

        text, kb = await build_single_mirror_user_panel(client, target_uid, page=page)
        await query.message.edit_text(text, reply_markup=kb)

    elif action == "subdays":
        target_uid = int(parts[2])
        days_to_sub = int(parts[3])
        page = int(parts[4]) if len(parts) > 4 else 1

        u_data = await plans_db.check_mirror_premium(target_uid)
        if u_data and u_data.get("expire_date"):
            old_exp = u_data["expire_date"]
            new_exp = old_exp - datetime.timedelta(days=days_to_sub)
            await plans_db.update_mirror_premium_expiry(target_uid, new_exp)
            await query.answer(f"➖ Reduced {days_to_sub} days from user {target_uid}.", show_alert=True)
        else:
            await query.answer("User has no active mirror plan!", show_alert=True)

        text, kb = await build_single_mirror_user_panel(client, target_uid, page=page)
        await query.message.edit_text(text, reply_markup=kb)

    elif action == "revoke":
        target_uid = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else 1

        await plans_db.remove_mirror_premium(target_uid)
        await query.answer(f"🗑️ Mirror access revoked for user {target_uid}!", show_alert=True)

        try:
            await client.send_message(
                target_uid,
                f"⚠️ **TOPIC MIRROR PLAN REVOKED**\n\n"
                f"Your Topic Mirror Plan access has been removed by Admin."
            )
        except Exception:
            pass

        text, kb = await build_mirror_users_panel(client, page=page)
        await query.message.edit_text(text, reply_markup=kb)
        


@app.on_message(filters.command("check") & admin_filter)
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
                f"🔍 ⚡ **XTRACTOR BOT PRO** ⚡ 🔍\n"
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


@app.on_message(filters.command("add") & admin_filter)
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
                f"✨ ⚡ **XTRACTOR BOT PRO** ⚡ ✨\n"
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
                        f"Thank you for supporting ⚡ **Xtractor Bot Pro** ⚡!\n"
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
                f"🔄 ⚡ **XTRACTOR BOT PRO** ⚡ 🔄\n"
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
                                f"Your subscription for ⚡ **Xtractor Bot Pro** ⚡ has expired.\n\n"
                                f"Thank you for being with us! If you wish to renew, please contact @CrazyxDeveloper_Bot.\n"
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


@app.on_message(filters.command("freez") & admin_filter)
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

@app.on_message(filters.command("clearpremium") & admin_filter)
async def clear_all_premium_cmd(client, message):
    try:
        await plans_db.db.delete_many({})
        await message.reply_text("✅ **All premium users have been successfully removed from the database.**")
    except Exception as e:
        await message.reply_text(f"❌ **Failed to clear premium users:** `{e}`")

@app.on_message(filters.command("ban") & admin_filter)
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

@app.on_message(filters.command("unban") & admin_filter)
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
    # Exclude OWNER_ID and Admins from ban checks
    if is_admin_or_owner(user_id):
        return
    if await is_user_banned(user_id):
        await message.reply_text("❌ **You are banned from using this bot.**\n\n💬 Please contact the admin to unban.")
        message.stop_propagation()

# Intercept all incoming callback queries from banned users at group -1 priority
@app.on_callback_query(group=-1)
async def check_banned_user_callback(client, query):
    user_id = query.from_user.id
    if is_admin_or_owner(user_id):
        return
    if await is_user_banned(user_id):
        await query.answer("❌ You are banned from using this bot. Contact admin to unban.", show_alert=True)
        query.stop_propagation()


# ────── TOXIC_ID Security Management Commands (Owner Only) ──────
@app.on_message(filters.command("addtoxic") & owner_filter)
async def add_toxic_cmd(client, message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ **Usage:** `/addtoxic <KEY_NAME>`\n\nExample: `/addtoxic TOXIC-PRO-998877`")
        return
    key = message.command[1].strip()
    await plans_db.add_toxic_id(key)
    await message.reply_text(f"✅ **TOXIC_ID Authorized Successfully!**\n\n🔑 **Key:** `{key}`\n\nAny bot container with `TOXIC_ID={key}` can now run!")

@app.on_message(filters.command("remtoxic") & owner_filter)
async def rem_toxic_cmd(client, message):
    if len(message.command) < 2:
        await message.reply_text("⚠️ **Usage:** `/remtoxic <KEY_NAME>`")
        return
    key = message.command[1].strip()
    await plans_db.remove_toxic_id(key)
    await message.reply_text(f"❌ **TOXIC_ID Revoked Successfully!**\n\n🔑 **Key:** `{key}`\n\nContainers running with this key will fail security check!")

@app.on_message(filters.command("checktoxic") & owner_filter)
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


# ─────────────────────────────────────────────────────────────────────────────
# ────── Global Free Access Management (Mirror & Batch Free Trial) ───────────
# ─────────────────────────────────────────────────────────────────────────────

async def build_free_access_panel() -> tuple:
    from toxic.core.mongo.plans_db import (
        get_global_free_access,
        format_time_remaining
    )
    import datetime
    data = await get_global_free_access()
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    # Mirror status
    mirror_on = data.get("mirror_free", False)
    mirror_exp = data.get("mirror_expires_at")
    mirror_rem_sec = None
    if mirror_on and mirror_exp:
        mirror_rem_sec = max(0, int((mirror_exp - now_utc).total_seconds()))
        if mirror_rem_sec == 0:
            mirror_on = False

    # Batch status
    batch_on = data.get("batch_free", False)
    batch_exp = data.get("batch_expires_at")
    batch_rem_sec = None
    if batch_on and batch_exp:
        batch_rem_sec = max(0, int((batch_exp - now_utc).total_seconds()))
        if batch_rem_sec == 0:
            batch_on = False

    mirror_badge = "🟢 <b>ACTIVE (FREE)</b>" if mirror_on else "🔴 <b>DISABLED (PAID ONLY)</b>"
    batch_badge = "🟢 <b>ACTIVE (FREE)</b>" if batch_on else "🔴 <b>DISABLED (PAID ONLY)</b>"

    mirror_time_str = format_time_remaining(mirror_rem_sec) if (mirror_on and mirror_exp) else ("Permanent (Until OFF)" if mirror_on else "N/A")
    batch_time_str = format_time_remaining(batch_rem_sec) if (batch_on and batch_exp) else ("Permanent (Until OFF)" if batch_on else "N/A")

    text = (
        "<blockquote>👑 <b>GLOBAL FREE ACCESS CONTROL PANEL</b> 👑</blockquote>\n\n"
        "⚡ <b>Control Free Access for ALL Bot Users Worldwide</b>\n"
        "<i>Jab yeh active hoga, sabhi users bina kisi plan ke Topic Mirror aur Batch use kar payenge!</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 <b>Topic Mirror Free Access:</b> {mirror_badge}\n"
        f"⏳ <b>Mirror Remaining:</b> <code>{mirror_time_str}</code>\n"
        f"📅 <b>Mirror Expiry:</b> <code>{mirror_exp.strftime('%Y-%m-%d %H:%M UTC') if (mirror_on and mirror_exp) else 'None'}</code>\n\n"
        f"📦 <b>Batch / Extract Free Access:</b> {batch_badge}\n"
        f"⏳ <b>Batch Remaining:</b> <code>{batch_time_str}</code>\n"
        f"📅 <b>Batch Expiry:</b> <code>{batch_exp.strftime('%Y-%m-%d %H:%M UTC') if (batch_on and batch_exp) else 'None'}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>Control Buttons se ON/OFF aur Duration set karein:</b>"
    )

    mirror_btn_text = "📁 Mirror: [🔴 Turn OFF]" if mirror_on else "📁 Mirror: [🟢 Turn ON (1 Day)]"
    batch_btn_text = "📦 Batch: [🔴 Turn OFF]" if batch_on else "📦 Batch: [🟢 Turn ON (1 Day)]"

    buttons = [
        [
            InlineKeyboardButton(mirror_btn_text, callback_data="fa_toggle_mirror"),
            InlineKeyboardButton(batch_btn_text, callback_data="fa_toggle_batch"),
        ],
        [
            InlineKeyboardButton("🎁 1-Click FREE BOTH (1 Day / 24h) 🚀", callback_data="fa_both_1d")
        ],
        [
            InlineKeyboardButton("⏱️ 1 Hour", callback_data="fa_dur_3600"),
            InlineKeyboardButton("⏱️ 3 Hours", callback_data="fa_dur_10800"),
            InlineKeyboardButton("⏱️ 6 Hours", callback_data="fa_dur_21600"),
        ],
        [
            InlineKeyboardButton("⏱️ 12 Hours", callback_data="fa_dur_43200"),
            InlineKeyboardButton("⏱️ 1 Day (24h)", callback_data="fa_dur_86400"),
            InlineKeyboardButton("⏱️ 2 Days", callback_data="fa_dur_172800"),
        ],
        [
            InlineKeyboardButton("⏱️ 3 Days", callback_data="fa_dur_259200"),
            InlineKeyboardButton("⏱️ 7 Days", callback_data="fa_dur_604800"),
            InlineKeyboardButton("♾️ Permanent", callback_data="fa_dur_inf"),
        ],
        [
            InlineKeyboardButton("🛑 Turn OFF ALL Free Access", callback_data="fa_off_all")
        ],
        [
            InlineKeyboardButton("📢 Announce Promo to All", callback_data="fa_announce"),
            InlineKeyboardButton("🔄 Refresh Status", callback_data="fa_refresh")
        ]
    ]

    return text, InlineKeyboardMarkup(buttons)


@app.on_message(filters.command([
    "freeaccess", "free_access", "freemirror", "free_mirror",
    "freebatch", "free_batch", "free", "globalfree", "freetrial",
    "freeplan", "freemode", "freeaccessmode"
]))
async def free_access_cmd_handler(client, message):
    from toxic.core.mongo.plans_db import (
        set_global_free_access,
        parse_duration_to_seconds,
        format_time_remaining
    )
    user = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    user_id = user.id if user else 0
    if not is_admin_or_owner(user_id):
        await message.reply_text(
            f"🔒 <b>Access Denied:</b> This command is restricted to Bot Owners and Admins.\n\n"
            f"👤 <b>Your Telegram ID:</b> <code>{user_id}</code>\n"
            f"<i>If you are the bot owner, make sure your ID is added to <code>OWNER_ID</code> in bot configuration or promote via <code>/addadmin</code>.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    cmd_parts = message.command
    if len(cmd_parts) == 1:
        text, kb = await build_free_access_panel()
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    arg1 = cmd_parts[1].lower()

    if arg1 in ("off", "disable", "stop", "close"):
        target = "both"
        if len(cmd_parts) >= 3 and cmd_parts[2].lower() in ("mirror", "batch"):
            target = cmd_parts[2].lower()
        await set_global_free_access(feature=target, enabled=False, admin_id=message.from_user.id)
        await message.reply_text(
            f"🛑 <b>Global Free Access for <code>{target.upper()}</code> has been TURNED OFF!</b>",
            parse_mode=ParseMode.HTML
        )
        return

    if arg1 in ("status", "check", "info"):
        text, kb = await build_free_access_panel()
        await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    target = "both"
    duration_str = "1 day"

    if arg1 == "on":
        if len(cmd_parts) >= 3 and cmd_parts[2].lower() in ("mirror", "batch", "both", "all"):
            target = cmd_parts[2].lower()
            if len(cmd_parts) >= 4:
                duration_str = " ".join(cmd_parts[3:])
        elif len(cmd_parts) >= 3:
            duration_str = " ".join(cmd_parts[2:])
    elif arg1 in ("mirror", "batch"):
        target = arg1
        if len(cmd_parts) >= 3:
            duration_str = " ".join(cmd_parts[2:])
    else:
        duration_str = " ".join(cmd_parts[1:])

    seconds = parse_duration_to_seconds(duration_str)
    await set_global_free_access(feature=target, enabled=True, duration_seconds=seconds, admin_id=message.from_user.id)
    time_str = format_time_remaining(seconds)
    await message.reply_text(
        f"🎉 <b>Global Free Access ENABLED!</b> 🚀\n\n"
        f"• <b>Feature:</b> <code>{target.upper()}</code>\n"
        f"• <b>Duration:</b> <code>{time_str}</code> ({seconds}s)\n\n"
        f"✅ <i>All users can now use {target.title()} completely FREE!</i>",
        parse_mode=ParseMode.HTML
    )


async def _send_promo_broadcast(client, users, text, kb):
    sent = 0
    for u in users:
        try:
            uid = u.get("user") if isinstance(u, dict) else u
            if uid:
                await client.send_message(chat_id=int(uid), text=text, parse_mode=ParseMode.HTML, reply_markup=kb)
                sent += 1
                await asyncio.sleep(0.05)
        except Exception:
            pass
    print(f"[PromoBroadcast] Announcement sent to {sent} users.")


@app.on_callback_query(filters.regex(r"^fa_"))
async def free_access_callback_handler(client, query: CallbackQuery):
    from toxic.core.mongo.plans_db import (
        get_global_free_access,
        set_global_free_access,
        format_time_remaining
    )
    user_id = query.from_user.id if query.from_user else 0
    if not is_admin_or_owner(user_id):
        await query.answer("🔒 Access Denied: Only Bot Owners & Admins can change Free Access settings.", show_alert=True)
        return
    action = query.data

    if action == "fa_refresh":
        text, kb = await build_free_access_panel()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer("🔄 Status Refreshed!", show_alert=False)
        return

    if action == "fa_toggle_mirror":
        data = await get_global_free_access()
        cur = data.get("mirror_free", False)
        await set_global_free_access("mirror", enabled=not cur, duration_seconds=86400 if not cur else None, admin_id=query.from_user.id)
        text, kb = await build_free_access_panel()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer(f"📁 Mirror Free: {'OFF' if cur else 'ON (1 Day)'}", show_alert=True)
        return

    if action == "fa_toggle_batch":
        data = await get_global_free_access()
        cur = data.get("batch_free", False)
        await set_global_free_access("batch", enabled=not cur, duration_seconds=86400 if not cur else None, admin_id=query.from_user.id)
        text, kb = await build_free_access_panel()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer(f"📦 Batch Free: {'OFF' if cur else 'ON (1 Day)'}", show_alert=True)
        return

    if action == "fa_both_1d":
        await set_global_free_access("both", enabled=True, duration_seconds=86400, admin_id=query.from_user.id)
        text, kb = await build_free_access_panel()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer("🎁 Free Access ENABLED for BOTH (1 Day)!", show_alert=True)
        return

    if action.startswith("fa_dur_"):
        dur_val = action.split("_")[2]
        if dur_val == "inf":
            await set_global_free_access("both", enabled=True, duration_seconds=None, admin_id=query.from_user.id)
            ans = "♾️ Permanent Free Access Enabled (No Limit)!"
        else:
            sec = int(dur_val)
            await set_global_free_access("both", enabled=True, duration_seconds=sec, admin_id=query.from_user.id)
            ans = f"⏱️ Duration set to {format_time_remaining(sec)} for Both!"
        text, kb = await build_free_access_panel()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer(ans, show_alert=True)
        return

    if action == "fa_off_all":
        await set_global_free_access("both", enabled=False, admin_id=query.from_user.id)
        text, kb = await build_free_access_panel()
        try:
            await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception:
            pass
        await query.answer("🛑 ALL Free Access Disabled!", show_alert=True)
        return

    if action == "fa_announce":
        from toxic.core.mongo.users_db import get_users
        users = await get_users()
        promo_msg = (
            "🎉 <b>SPECIAL PROMOTION: FREE ACCESS UNLOCKED!</b> 🚀\n\n"
            "<blockquote>🎁 <b>Topic Mirroring & Bulk Batch are now 100% FREE!</b>\n\n"
            "All users have been granted complimentary access. You can now clone full topic groups and batch process files without any plan restrictions!</blockquote>\n\n"
            "<b>🚀 Quick Start:</b>\n"
            "• <code>/topicmirror</code> — Clone entire supergroups with topics\n"
            "• <code>/batch</code> — Bulk extract and upload restricted files\n\n"
            "<i>Enjoy your free access! 🖤</i>"
        )
        promo_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📁 Start Topic Mirror", callback_data="tm_new")],
            [InlineKeyboardButton("📘 User Guide", callback_data="guide_page_1")]
        ])
        asyncio.create_task(_send_promo_broadcast(client, users, promo_msg, promo_kb))
        await query.answer(f"📢 Announcing promo to {len(users)} users in background!", show_alert=True)
        return
    


# ─────────────────────────────────────────────────────────────
# 💎 PREMIUM CENTER (EXACT STYLING AS REQUESTED BY LO)
# ─────────────────────────────────────────────────────────────

def get_premium_center_markup():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Save restrict Bot", callback_data="prem_saver_bot"),
            InlineKeyboardButton("Topic Mirror Bot", callback_data="prem_mirror_bot")
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="prem_help_steps")
        ]
    ])

def format_stylized_name(name: str) -> str:
    """Format user name with stylish unicode glyphs matching LO's screenshot"""
    if not name:
        return "Tⱺxic"
    # subtle aesthetic touch: replace standard 'o' with 'ⱺ'
    styled = name.replace("o", "ⱺ").replace("O", "ⱺ")
    return f"{styled} ✯"

@app.on_message(filters.command(["premium", "premiumcenter", "store", "buy"]))
async def premium_center_cmd(client: Client, message):
    user = message.from_user
    raw_name = user.first_name if user and user.first_name else "Tⱺxic"
    styled_name = format_stylized_name(raw_name)

    text = (
        "💎 <b>PREMIUM CENTER</b>\n\n"
        f"👋 <b>WELCOME,</b> 🖤 <b>{styled_name}</b>\n\n"
        "⚡ <b>PURCHASE PREMIUM FOR ANY SUPPORTED BOT.</b>\n\n"
        "💎 <b>AUTOMATIC ACTIVATION • 🚫 NO SCREENSHOT</b>\n\n"
        "❓ <b>TAP HELP FOR PAYMENT STEPS.</b>"
    )

    await message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_premium_center_markup(),
        disable_web_page_preview=True
    )


@app.on_callback_query(filters.regex(r"^prem_main_menu$"))
async def prem_main_menu_cb(client: Client, query: CallbackQuery):
    user = query.from_user
    raw_name = user.first_name if user and user.first_name else "Tⱺxic"
    styled_name = format_stylized_name(raw_name)

    text = (
        "💎 <b>PREMIUM CENTER</b>\n\n"
        f"👋 <b>WELCOME,</b> 🖤 <b>{styled_name}</b>\n\n"
        "⚡ <b>PURCHASE PREMIUM FOR ANY SUPPORTED BOT.</b>\n\n"
        "💎 <b>AUTOMATIC ACTIVATION • 🚫 NO SCREENSHOT</b>\n\n"
        "❓ <b>TAP HELP FOR PAYMENT STEPS.</b>"
    )
    try:
        await query.message.edit_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_premium_center_markup(),
            disable_web_page_preview=True
        )
    except Exception:
        await query.message.reply_text(
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_premium_center_markup(),
            disable_web_page_preview=True
        )
    await query.answer()


@app.on_callback_query(filters.regex(r"^prem_saver_bot$"))
async def prem_saver_bot_cb(client: Client, query: CallbackQuery):
    text = (
        "📥 <b>SAVE RESTRICT CONTENT (SRC) BOT PLAN</b>\n\n"
        "<blockquote>⚡ <b>FEATURES INCLUDED:</b>\n"
        "• Download & Forward Restricted Private Channel Media\n"
        "• Server-Side Zero Bandwidth Copy Mode (Ultra-Fast 50ms)\n"
        "• Bulk Batch Processing (Up to 5,000 files in 1 command)\n"
        "• Custom Thumbnails, PDF Watermarks & Clean Captions\n"
        "• Bypass Telegram Copy Protection & Forward Lock</blockquote>\n\n"
        "<b>💰 PRICING:</b>\n"
        "• <b>1 Month:</b> <code>₹149</code> / <code>$2.00 USD</code>\n"
        "• <b>3 Months:</b> <code>₹299</code> / <code>$4.00 USD</code>\n\n"
        "<i>Instant automatic activation upon payment confirmation! 🚀</i>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💳 Buy 1 Month (₹149)", url="https://t.me/CrazyxDeveloper_Bot"),
            InlineKeyboardButton("💎 Buy 3 Months (₹299)", url="https://t.me/CrazyxDeveloper_Bot")
        ],
        [
            InlineKeyboardButton("🔙 Back to Premium Center", callback_data="prem_main_menu")
        ]
    ])
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    await query.answer()


@app.on_callback_query(filters.regex(r"^prem_mirror_bot$"))
async def prem_mirror_bot_cb(client: Client, query: CallbackQuery):
    text = (
        "👑 <b>TOPIC MIRROR & FORUM CLONE PRO PLAN</b>\n\n"
        "<blockquote>🌟 <b>EXCLUSIVE VIP CAPABILITIES:</b>\n"
        "• 1-Click Complete Supergroup Forum Clone (All Topics & Icons)\n"
        "• Channel-to-Topics (<code>/c2t</code>) Auto Caption Route Engine\n"
        "• 1-Click Live Scan & Sync Missing Content (<code>/sync_mirror</code>)\n"
        "• Daily Scheduled Auto-Update & Real-Time Sync\n"
        "• Includes FULL Save Restrict (SRC) Plan automatically!</blockquote>\n\n"
        "<b>💰 PRICING:</b>\n"
        "• <b>1 Month:</b> <code>₹299</code> / <code>$4.00 USD</code>\n"
        "• <b>3 Months:</b> <code>₹599</code> / <code>$8.00 USD</code>\n\n"
        "<i>Unlock unlimited supergroup cloning at maximum server speed! ⚡</i>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👑 Buy 1 Month (₹299)", url="https://t.me/CrazyxDeveloper_Bot"),
            InlineKeyboardButton("🌟 Buy 3 Months (₹599)", url="https://t.me/CrazyxDeveloper_Bot")
        ],
        [
            InlineKeyboardButton("🔙 Back to Premium Center", callback_data="prem_main_menu")
        ]
    ])
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    await query.answer()


@app.on_callback_query(filters.regex(r"^prem_help_steps$"))
async def prem_help_steps_cb(client: Client, query: CallbackQuery):
    text = (
        "❓ <b>PAYMENT & ACTIVATION STEPS</b>\n\n"
        "<blockquote><b>1️⃣ CHOOSE YOUR BOT & DURATION:</b>\n"
        "Select either Save Restrict Bot or Topic Mirror Bot above.\n\n"
        "<b>2️⃣ PAYMENT METHODS SUPPORTED:</b>\n"
        "• 🇮🇳 <b>UPI:</b> PhonePe / GooglePay / Paytm / QR\n"
        "• 🌐 <b>Crypto:</b> USDT (BEP20 / TRC20 / TON)\n"
        "• 🎁 <b>Amazon / Flipkart Gift Cards</b>\n\n"
        "<b>3️⃣ INSTANT ACTIVATION:</b>\n"
        "Send your User ID (<code>/id</code>) to our Admin bot. Your premium access unlocks automatically in under 2 minutes!</blockquote>\n\n"
        "👉 <b>Admin Support:</b> @CrazyxDeveloper_Bot"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 Chat with Admin", url="https://t.me/CrazyxDeveloper_Bot")
        ],
        [
            InlineKeyboardButton("🔙 Back to Premium Center", callback_data="prem_main_menu")
        ]
    ])
    try:
        await query.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb, disable_web_page_preview=True)
    await query.answer()
