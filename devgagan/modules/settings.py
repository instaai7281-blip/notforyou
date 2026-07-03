import asyncio
from pyrogram import filters, Client
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from devgagan import app
from devgagan.core.mongo import db
from devgagan.core.get_func import get_user_branding_tag, set_user_branding_tag, get_user_custom_tags, add_user_custom_tag, delete_user_custom_tag, get_user_spoiler_preference, set_user_spoiler_preference

# ────── Keyboards ──────

def get_main_settings_keyboard(user_id):
    is_spoiler = get_user_spoiler_preference(user_id)
    buttons = [
        [
            InlineKeyboardButton("📝 Custom Caption", callback_data="settings_caption"),
            InlineKeyboardButton("🖼️ Thumbnail", callback_data="settings_thumb")
        ],
        [
            InlineKeyboardButton("📁 Media Filters", callback_data="settings_filters"),
            InlineKeyboardButton("📢 Set Chat ID", callback_data="settings_chatid")
        ],
        [
            InlineKeyboardButton("🧹 Text Cleaning", callback_data="settings_cleaning"),
            InlineKeyboardButton("🏷️ Branding Tag", callback_data="settings_tag")
        ],
        [
            InlineKeyboardButton(f"🌶️ Spoiler Mode: {'ON ✅' if is_spoiler else 'OFF ❌'}", callback_data="toggle_spoiler_settings")
        ],
        [
            InlineKeyboardButton("🔄 Reset All", callback_data="reset_all_settings"),
            InlineKeyboardButton("❌ Close Menu", callback_data="close_settings")
        ]
    ]
    return InlineKeyboardMarkup(buttons)

def get_filters_keyboard(user_data):
    filters_data = user_data.get("filters", {})
    def toggle_text(key):
        return "✅" if filters_data.get(key, True) else "❌"

    buttons = [
        [InlineKeyboardButton(f"{toggle_text('video')} Video", callback_data="toggle_video"),
         InlineKeyboardButton(f"{toggle_text('document')} Document", callback_data="toggle_document")],
        [InlineKeyboardButton(f"{toggle_text('audio')} Audio", callback_data="toggle_audio"),
         InlineKeyboardButton(f"{toggle_text('photo')} Photo", callback_data="toggle_photo")],
        [InlineKeyboardButton(f"{toggle_text('sticker')} Sticker", callback_data="toggle_sticker"),
         InlineKeyboardButton(f"{toggle_text('html')} HTML", callback_data="toggle_html")],
        [InlineKeyboardButton(f"{toggle_text('text')} Text", callback_data="toggle_text"),
         InlineKeyboardButton("🔄 Reset", callback_data="reset_filters")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_caption_keyboard(user_data):
    caption_enabled = user_data.get("caption_enabled", True)
    status_text = "✅ Enabled" if caption_enabled else "❌ Disabled"
    
    buttons = [
        [InlineKeyboardButton(f"Status: {status_text}", callback_data="toggle_caption_status")],
        [
            InlineKeyboardButton("✏️ Set Caption", callback_data="set_new_caption"),
            InlineKeyboardButton("🗑️ Delete", callback_data="delete_caption")
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_thumb_keyboard(user_data):
    buttons = [
        [
            InlineKeyboardButton("✏️ Set New", callback_data="set_new_thumb"),
            InlineKeyboardButton("🗑️ Delete", callback_data="delete_thumb")
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_cleaning_keyboard(user_data):
    buttons = [
        [
            InlineKeyboardButton("➕ Add Word", callback_data="add_clean_word"),
            InlineKeyboardButton("🗑️ Clear List", callback_data="clear_clean_words")
        ],
        [
            InlineKeyboardButton("🔄 Replace Words", callback_data="set_replacement"),
            InlineKeyboardButton("🗑️ Clear Repl.", callback_data="clear_replacements")
        ],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(buttons)

def get_tag_keyboard(user_id):
    current_tag = get_user_branding_tag(user_id)
    custom_tags = get_user_custom_tags(user_id)
    
    from devgagan.core.get_func import load_user_data
    is_keep_original = load_user_data(user_id, "keep_original_caption", False)
    
    buttons = []
    
    # 0) Raw Caption Toggle
    buttons.append([InlineKeyboardButton(f"🔗 Raw Caption (No Clean): {'ON ✅' if is_keep_original else 'OFF ❌'}", callback_data="toggle_keep_original")])
    
    # 1) Stolen Happiness Preset
    is_sh_selected = (current_tag == "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
    buttons.append([InlineKeyboardButton(f"🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝ {'✅' if is_sh_selected else ''}", callback_data="set_tag_stolenhappiness")])
    
    # 2) Custom saved tags (up to 5)
    for i, tag in enumerate(custom_tags):
        is_active = (current_tag == tag)
        buttons.append([
            InlineKeyboardButton(f"✨ {tag[:20]}... {'✅' if is_active else ''}" if len(tag) > 20 else f"✨ {tag} {'✅' if is_active else ''}", callback_data=f"set_tag_select_{i}"),
            InlineKeyboardButton("❌", callback_data=f"set_tag_delete_{i}")
        ])
        
    # 3) Add new custom tag button if less than 5
    if len(custom_tags) < 5:
        buttons.append([InlineKeyboardButton("➕ Add Custom Tag", callback_data="set_tag_add")])
        
    buttons.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")])
    return InlineKeyboardMarkup(buttons)

# ────── Command Handler ──────

@app.on_message(filters.command("settings") & filters.private)
async def settings_command(client, message):
    await message.reply_text(
        "⚙️ **Personalize Your Experience**\n\nConfigure your extraction preferences, branding, and filters using the buttons below.",
        reply_markup=get_main_settings_keyboard(message.chat.id)
    )

# ────── Navigation & Main Callbacks ──────

@app.on_callback_query(filters.regex(r"^(settings_filters|back_to_main|close_settings|settings_thumb|settings_chatid|settings_cleaning|settings_tag)$"))
async def main_nav_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    user_data = await db.get_data(user_id) or {}
    
    if data == "close_settings":
        await callback_query.message.delete()
        return
    elif data == "back_to_main":
        await callback_query.message.edit_text(
            "⚙️ **Personalize Your Experience**\n\nConfigure your extraction preferences, branding, and filters using the buttons below.",
            reply_markup=get_main_settings_keyboard(user_id)
        )
    elif data == "settings_filters":
        await callback_query.message.edit_text(
            "📁 **Media Filters**\n\nToggle which media types you want the bot to process:",
            reply_markup=get_filters_keyboard(user_data)
        )
    elif data == "settings_thumb":
        thumb_status = "✅ Set" if user_data.get("thumb") else "❌ Not Set"
        await callback_query.message.edit_text(
            f"🖼️ **Custom Thumbnail Settings**\n\n**Current Status:** {thumb_status}\n\nSetting a custom thumbnail will apply it to all videos and documents extracted.",
            reply_markup=get_thumb_keyboard(user_data)
        )
    elif data == "settings_chatid":
        chat_id = user_data.get("chat_id", "Your DM (Default)")
        await callback_query.message.edit_text(
            f"📢 **Auto-Forward Settings**\n\n**Currently Uploading To:** `{chat_id}`\n\nIf you set a Channel/Group ID, the bot will automatically upload all extracted content there instead of your DM.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Set Chat ID", callback_data="set_new_chatid"),
                 InlineKeyboardButton("🗑️ Reset", callback_data="delete_chatid")],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main")]
            ])
        )
    elif data == "settings_cleaning":
        clean_words = user_data.get("clean_words", [])
        replace_words = user_data.get("replacement_words", {})
        
        text = "🧹 **Text Cleaning & Replacements**\n\n"
        text += f"**Clean Words:** {', '.join(clean_words) if clean_words else 'None'}\n"
        text += f"**Replacements:** {len(replace_words)} active rules\n\n"
        text += "> These rules apply to original captions before your custom caption is added."
        
        await callback_query.message.edit_text(text, reply_markup=get_cleaning_keyboard(user_data))
    elif data == "settings_tag":
        current_tag = user_data.get("branding_tag", "🖤 Sᴛꪮʟᴇɴ Hᴀᴘപ⚝")
        current_tag = user_data.get("branding_tag", "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
        preview_text = (
            f"🏷️ **Branding Tag Settings**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Current Tag: `{current_tag}`\n\n"
            f"📝 **How it will look in your captions:**\n"
            f"> 📁 **File:** `movie_title.mp4`\n"
            f"> ───\n"
            f"> **{current_tag}**\n\n"
            f"This branding tag appears in the captions of your files and on PDF document pages. Select a preset or set a custom tag below:"
        )
        await callback_query.message.edit_text(
            preview_text,
            reply_markup=get_tag_keyboard(callback_query.from_user.id)
        )

# ────── Caption Actions ──────

@app.on_callback_query(filters.regex(r"^settings_caption$"))
async def caption_settings_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    user_data = await db.get_data(user_id) or {}
    caption = user_data.get("caption", "Not Set")
    
    text = f"📝 **Custom Caption Settings**\n\n**Current Caption:**\n`{caption}`\n\n> You can use `{{caption}}` placeholder to keep the original caption alongside your custom text."
    await callback_query.message.edit_text(text, reply_markup=get_caption_keyboard(user_data))

@app.on_callback_query(filters.regex(r"^(toggle_caption_status|delete_caption|set_new_caption)$"))
async def caption_actions_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    user_data = await db.get_data(user_id) or {}

    if data == "toggle_caption_status":
        current_status = user_data.get("caption_enabled", True)
        new_status = not current_status
        await db.update_data(user_id, {"caption_enabled": new_status})
        await callback_query.answer(f"Caption {'Enabled' if new_status else 'Disabled'}")
        
    elif data == "delete_caption":
        await db.remove_caption(user_id)
        await callback_query.answer("Caption deleted successfully", show_alert=True)
        
    elif data == "set_new_caption":
        await callback_query.message.delete()
        ask = await client.ask(user_id, "📝 **Send your new custom caption now.**\n\n> Use `{caption}` where you want the original text to appear.\n> Send /cancel to abort.")
        
        if ask.text == "/cancel":
            await ask.reply("Action cancelled.")
        else:
            await db.set_caption(user_id, ask.text)
            await ask.reply(f"✅ **Caption updated successfully!**\n\n`{ask.text}`")
        
        await asyncio.sleep(0.5)
        await settings_command(client, ask)
        return

    await caption_settings_callback(client, callback_query)

# ────── Thumbnail Actions ──────

@app.on_callback_query(filters.regex(r"^(set_new_thumb|delete_thumb)$"))
async def thumb_actions_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "delete_thumb":
        await db.remove_thumbnail(user_id)
        from config import THUMBNAIL_DIR
        import os
        thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except Exception:
                pass
        await callback_query.answer("Thumbnail deleted", show_alert=True)
    elif data == "set_new_thumb":
        await callback_query.message.delete()
        ask = await client.ask(user_id, "🖼️ **Send the photo you want to set as thumbnail.**\n\n> Send /cancel to abort.")
        
        if ask.photo:
            import os
            from config import THUMBNAIL_DIR
            from devgagan.core.func import optimize_thumbnail
            thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
            await ask.download(file_name=thumbnail_path)
            optimize_thumbnail(thumbnail_path)
            try:
                with open(thumbnail_path, "rb") as f:
                    binary_data = f.read()
                await db.set_thumbnail(user_id, binary_data)
            except Exception as e:
                print(f"[ERROR] Failed to save thumbnail to DB: {e}")
            await ask.reply("✅ **Thumbnail updated successfully!**")
        elif ask.text == "/cancel":
            await ask.reply("Action cancelled.")
        else:
            await ask.reply("❌ **Invalid input. Please send a photo.**")
        
        await asyncio.sleep(0.5)
        await settings_command(client, ask)
        return

    user_data = await db.get_data(user_id) or {}
    await main_nav_callback(client, callback_query)

# ────── Chat ID Actions ──────

@app.on_callback_query(filters.regex(r"^(set_new_chatid|delete_chatid)$"))
async def chatid_actions_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "delete_chatid":
        await db.remove_channel(user_id)
        await callback_query.answer("Auto-forward reset to DM", show_alert=True)
    elif data == "set_new_chatid":
        await callback_query.message.delete()
        ask = await client.ask(
            user_id,
            "📢 **Send the Channel, Group ID, or Message Link.**\n\n"
            "> **Examples:**\n"
            "> • `-100123456789` (Plain ID)\n"
            "> • `https://t.me/c/123456789/430/431` (Message link with Topic ID)\n\n"
            "> Send /cancel to abort."
        )
        
        if ask.text == "/cancel":
            await ask.reply("Action cancelled.")
        else:
            val = ask.text.strip()
            from devgagan.core.get_func import parse_target_chat
            parsed_chat = parse_target_chat(val)
            
            chat_to_save = parsed_chat
            try:
                chat_to_save = int(parsed_chat)
            except ValueError:
                pass
                
            await db.set_channel(user_id, chat_to_save)
            await ask.reply(f"✅ **Auto-forward set to:** `{chat_to_save}`")
        
        await asyncio.sleep(0.5)
        await settings_command(client, ask)
        return

    await main_nav_callback(client, callback_query)

# ────── Cleaning Actions ──────

@app.on_callback_query(filters.regex(r"^(add_clean_word|clear_clean_words|set_replacement|clear_replacements)$"))
async def cleaning_actions_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "clear_clean_words":
        await db.all_words_remove(user_id)
        await callback_query.answer("Clean words list cleared")
    elif data == "clear_replacements":
        await db.remove_replace(user_id)
        await callback_query.answer("Replacement rules cleared")
    elif data == "add_clean_word":
        await callback_query.message.delete()
        ask = await client.ask(user_id, "🧹 **Send the word you want to clean from captions.**\n\n> Separate multiple words with spaces.\n> Send /cancel to abort.")
        if ask.text != "/cancel":
            words = ask.text.split()
            await db.clean_words(user_id, words)
            await ask.reply(f"✅ **Added {len(words)} words to cleaning list.**")
        await asyncio.sleep(0.5)
        await settings_command(client, ask)
        return
    elif data == "set_replacement":
        await callback_query.message.delete()
        ask = await client.ask(user_id, "🔄 **Send the words in format:** `word > replacement`\n\n> Example: `oldword > newword`\n> Send /cancel to abort.")
        if ask.text != "/cancel" and ">" in ask.text:
            parts = ask.text.split(">")
            to_replace = parts[0].strip()
            replace_with = parts[1].strip()
            await db.replace_caption(user_id, replace_with, to_replace)
            await ask.reply(f"✅ **Rule added:** `{to_replace}` ➜ `{replace_with}`")
        else:
             await ask.reply("❌ **Invalid format.**")
        await asyncio.sleep(0.5)
        await settings_command(client, ask)
        return

    await main_nav_callback(client, callback_query)

# ────── Branding Tag Actions ──────

@app.on_callback_query(filters.regex(r"^(set_tag_stolenhappiness|set_tag_add|set_tag_select_\d+|set_tag_delete_\d+|toggle_keep_original)$"))
async def tag_actions_callback(client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "toggle_keep_original":
        from devgagan.core.get_func import save_user_data, load_user_data
        current_val = load_user_data(user_id, "keep_original_caption", False)
        new_val = not current_val
        save_user_data(user_id, "keep_original_caption", new_val)
        await callback_query.answer(f"Raw Caption Mode: {'Enabled' if new_val else 'Disabled'}")

    elif data == "set_tag_stolenhappiness":
        set_user_branding_tag(user_id, "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
        await callback_query.answer("Branding tag set to Stolen Happiness Preset")
        
    elif data == "set_tag_add":
        custom_tags = get_user_custom_tags(user_id)
        if len(custom_tags) >= 5:
            await callback_query.answer("❌ You can save up to 5 custom tags only! Delete one first.", show_alert=True)
            return
            
        await callback_query.message.delete()
        ask = await client.ask(user_id, "🏷️ **Send your custom branding tag now.**\n\n> Send /cancel to abort.")
        
        if ask.text == "/cancel":
            await ask.reply("Action cancelled.")
        else:
            success, msg = add_user_custom_tag(user_id, ask.text)
            await ask.reply(f"{'✅' if success else '❌'} {msg}")
        await asyncio.sleep(0.5)
        await settings_command(client, ask)
        return

    elif data.startswith("set_tag_select_"):
        tag_index = int(data.split("_")[-1])
        custom_tags = get_user_custom_tags(user_id)
        if 0 <= tag_index < len(custom_tags):
            tag = custom_tags[tag_index]
            set_user_branding_tag(user_id, tag)
            await callback_query.answer(f"Selected: {tag}")
        else:
            await callback_query.answer("Invalid tag index")

    elif data.startswith("set_tag_delete_"):
        tag_index = int(data.split("_")[-1])
        success, msg = delete_user_custom_tag(user_id, tag_index)
        await callback_query.answer(msg, show_alert=True)

    # Refresh page
    user_data = await db.get_data(user_id) or {}
    current_tag = user_data.get("branding_tag", "🖤 Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝")
    preview_text = (
        f"🏷️ **Branding Tag Settings**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current Tag: `{current_tag}`\n\n"
        f"📝 **How it will look in your captions:**\n"
        f"> 📁 **File:** `movie_title.mp4`\n"
        f"> ───\n"
        f"> **{current_tag}**\n\n"
        f"This branding tag appears in the captions of your files and on PDF document pages. Select a preset or set a custom tag below:"
    )
    await callback_query.message.edit_text(
        preview_text,
        reply_markup=get_tag_keyboard(callback_query.from_user.id)
    )

# ────── Filter & Reset Actions ──────

@app.on_message(filters.private)
# Note: we need to adjust regex below to support sticker and html
@app.on_callback_query(filters.regex(r"^toggle_(video|document|audio|photo|text|sticker|html)$"))
async def toggle_filter(client, callback_query: CallbackQuery):
    media_type = callback_query.data.split("_")[1]
    user_id = callback_query.from_user.id
    
    user_data = await db.get_data(user_id) or {}
    filters_data = user_data.get("filters", {})
    new_status = not filters_data.get(media_type, True)
    
    await db.set_filter(user_id, media_type, new_status)
    updated_data = await db.get_data(user_id) or {}
    await callback_query.message.edit_reply_markup(reply_markup=get_filters_keyboard(updated_data))
    await callback_query.answer(f"{media_type.capitalize()} turned {'ON' if new_status else 'OFF'}")

@app.on_callback_query(filters.regex(r"^(reset_filters|reset_all_settings)$"))
async def reset_actions_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    
    if data == "reset_filters":
        for media_type in ["video", "document", "audio", "photo", "text", "sticker", "html"]:
            await db.set_filter(user_id, media_type, True)
        await callback_query.answer("Filters reset")
    elif data == "reset_all_settings":
        # Full wipe (except session/premium status if they exist elsewhere)
        await db.remove_thumbnail(user_id)
        from config import THUMBNAIL_DIR
        import os
        thumbnail_path = os.path.join(THUMBNAIL_DIR, f"{user_id}.jpg")
        if os.path.exists(thumbnail_path):
            try:
                os.remove(thumbnail_path)
            except Exception:
                pass
        await db.remove_caption(user_id)
        await db.remove_replace(user_id)
        await db.all_words_remove(user_id)
        await db.remove_channel(user_id)
        await callback_query.answer("All settings reset to default", show_alert=True)
    
    updated_data = await db.get_data(user_id) or {}
    await main_nav_callback(client, callback_query)

# ────── Spoiler Settings Toggle ──────

@app.on_callback_query(filters.regex(r"^toggle_spoiler_settings$"))
async def toggle_spoiler_settings_callback(client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    current_val = get_user_spoiler_preference(user_id)
    new_val = not current_val
    set_user_spoiler_preference(user_id, new_val)
    await callback_query.answer(f"Spoiler mode set to {'ON' if new_val else 'OFF'}")
    await callback_query.message.edit_reply_markup(
        reply_markup=get_main_settings_keyboard(user_id)
    )
