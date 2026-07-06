import asyncio
from pyrogram import filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from devgagan import app
from config import OWNER_ID

@app.on_message(filters.command("deleteall"))
async def delete_all_cmd(_, message):
    chat_id = message.chat.id
    
    # 1. Direct check: only works in channels or groups
    if message.chat.type not in [enums.ChatType.CHANNEL, enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply("❌ **Error:** This command can only be used in channels or groups.")
        return

    # 2. Check authorization of the sender (if sent by a user)
    if message.from_user:
        user_id = message.from_user.id
        owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
        is_owner = str(user_id) in [str(o) for o in owner_list]
        if not is_owner:
            # Check if they are admin in this chat
            try:
                member = await app.get_chat_member(chat_id, user_id)
                if member.status not in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                    await message.reply("❌ **Access Denied:** Only administrators can use this command.")
                    return
            except Exception:
                await message.reply("❌ **Access Denied:** You are not authorized here.")
                return

    # 3. Send confirmation message with buttons
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Delete All", callback_data="confirm_delete_all"),
            InlineKeyboardButton("❌ Cancel", callback_data="cancel_delete_all")
        ]
    ])
    
    await message.reply(
        "⚠️ **WARNING:**\n\n"
        "Are you absolutely sure you want to delete **all messages** in this chat?\n"
        "This action is permanent and cannot be undone!",
        reply_markup=buttons
    )

@app.on_callback_query(filters.regex(r"^(confirm_delete_all|cancel_delete_all)$"))
async def delete_all_callback(_, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    # Verify clicker's rights (Must be chat owner, chat administrator, or global bot owner)
    authorized = False
    owner_list = OWNER_ID if isinstance(OWNER_ID, list) else [OWNER_ID]
    is_owner = str(user_id) in [str(o) for o in owner_list]
    if is_owner:
        authorized = True
    else:
        try:
            member = await app.get_chat_member(chat_id, user_id)
            if member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]:
                authorized = True
        except Exception:
            pass

    if not authorized:
        await callback_query.answer("❌ Only administrators of this chat can perform this action!", show_alert=True)
        return

    if callback_query.data == "cancel_delete_all":
        await callback_query.message.edit_text("❌ **Operation cancelled.** No messages were deleted.")
        return

    # Confirm delete all
    await callback_query.message.edit_text("⌛ **Initializing mass deletion...**")
    
    userbot = None
    try:
        # Inline import to avoid circular dependency issues
        from devgagan.modules.main import initialize_userbot
        userbot = await initialize_userbot(user_id)
        
        client_to_use = userbot if userbot else app
        client_name = "Userbot" if userbot else "Bot"
        
        await callback_query.message.edit_text(f"🔍 **Scanning messages using {client_name}...**")
        
        # Collect message IDs
        message_ids = []
        async for msg in client_to_use.get_chat_history(chat_id, limit=10000):
            if msg.id != callback_query.message.id:
                message_ids.append(msg.id)
                
        if not message_ids:
            await callback_query.message.edit_text("📋 **No messages found to delete.**")
            if userbot:
                await userbot.stop()
            return
            
        await callback_query.message.edit_text(f"🗑️ **Deleting {len(message_ids)} messages using {client_name}...**")
        
        deleted_count = 0
        batch_size = 100
        for k in range(0, len(message_ids), batch_size):
            batch = message_ids[k:k+batch_size]
            try:
                await client_to_use.delete_messages(chat_id, batch)
                deleted_count += len(batch)
                await asyncio.sleep(0.5)  # Simple delay to avoid rate limits
            except Exception:
                pass
                
        await callback_query.message.edit_text(
            f"✅ **Success!**\n\n"
            f"Wiped `{deleted_count}` messages successfully using {client_name}."
        )
        
    except Exception as e:
        await callback_query.message.edit_text(f"❌ **An error occurred during deletion:** `{str(e)}`")
    finally:
        if userbot:
            try:
                await userbot.stop()
            except Exception:
                pass
