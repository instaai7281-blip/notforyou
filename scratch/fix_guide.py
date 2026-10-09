import os

path = "toxic/modules/start.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

pos_start = content.find('@app.on_message(filters.command("guide"))')
pos_end = content.find('@app.on_callback_query(filters.regex("^guide_page_2$"))')

if pos_start != -1 and pos_end != -1:
    new_code = '''@app.on_message(filters.command("guide"))
async def guide_command(_, message: Message):
    bot_username = get_bot_username()
    guide_p1_text = (
        f"<b>📘 USER GUIDE — XTRACTOR BOT PRO (1/3)</b>\\n\\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\\n\\n"
        "<b>✨ 1. PUBLIC CHANNEL / GROUP POSTS:</b>\\n"
        f"Send any public Telegram post link directly to <code>{bot_username}</code>.\\n"
        "<i>Example:</i> <code>https://t.me/public_channel/1234</code>\\n\\n"
        "<b>🔒 2. PRIVATE CHANNEL / GROUP POSTS (XTRACTOR PRO):</b>\\n"
        f"1️⃣ Send <code>/login</code> to <code>{bot_username}</code>.\\n"
        "2️⃣ Enter your phone number with country code: <code>+91XXXXXXXXXX</code>\\n"
        "3️⃣ Check Telegram official chat for your OTP code.\\n"
        "4️⃣ Enter OTP with <b>spaces between digits</b> (e.g., for OTP <code>54321</code> ➔ enter <code>5 4 3 2 1</code>).\\n"
        "5️⃣ Once logged in, send private links or use <code>/batch</code> for bulk extraction!"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Topic Mirror Guide ➔", callback_data="guide_page_2")],
        [InlineKeyboardButton("⚡ Extra Features", callback_data="guide_page_3"), InlineKeyboardButton("💎 View Plans", callback_data="see_plan")],
        [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])
    await message.reply_text(guide_p1_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@app.on_callback_query(filters.regex("^guide_page_1$"))
async def guide_page_1(_, query: CallbackQuery):
    bot_username = get_bot_username()
    guide_p1_text = (
        f"<b>📘 USER GUIDE — XTRACTOR BOT PRO (1/3)</b>\\n\\n"
        f"<b>🤖 Bot Username:</b> <code>{bot_username}</code>\\n\\n"
        "<b>✨ 1. PUBLIC CHANNEL / GROUP POSTS:</b>\\n"
        f"Send any public Telegram post link directly to <code>{bot_username}</code>.\\n"
        "<i>Example:</i> <code>https://t.me/public_channel/1234</code>\\n\\n"
        "<b>🔒 2. PRIVATE CHANNEL / GROUP POSTS (XTRACTOR PRO):</b>\\n"
        f"1️⃣ Send <code>/login</code> to <code>{bot_username}</code>.\\n"
        "2️⃣ Enter your phone number with country code: <code>+91XXXXXXXXXX</code>\\n"
        "3️⃣ Check Telegram official chat for your OTP code.\\n"
        "4️⃣ Enter OTP with <b>spaces between digits</b> (e.g., for OTP <code>54321</code> ➔ enter <code>5 4 3 2 1</code>).\\n"
        "5️⃣ Once logged in, send private links or use <code>/batch</code> for bulk extraction!"
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 Topic Mirror Guide ➔", callback_data="guide_page_2")],
        [InlineKeyboardButton("⚡ Extra Features", callback_data="guide_page_3"), InlineKeyboardButton("💎 View Plans", callback_data="see_plan")],
        [InlineKeyboardButton("💬 Contact Admin", url="https://t.me/CrazyxDeveloper_Bot")]
    ])
    try:
        await query.message.edit_text(guide_p1_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    except Exception:
        pass
'''
    updated = content[:pos_start] + new_code + "\n\n" + content[pos_end:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(updated)
    print("Successfully updated start.py guide handler!")
else:
    print(f"Could not find positions: pos_start={pos_start}, pos_end={pos_end}")
