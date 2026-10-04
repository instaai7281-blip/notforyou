# ---------------------------------------------------
# File Name: shrink.py
# Description: A Pyrogram bot for downloading files from Telegram channels or groups 
#              and uploading them back to Telegram.
# Author: Gagan



# Created: 2025-01-11
# Last Modified: 2025-01-11
# Version: 2.0.5
# License: MIT License
# ---------------------------------------------------

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import random
import requests
import string
import aiohttp
from toxic import app
from toxic.core.func import *
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_DB, WEBSITE_URL, AD_API, LOG_GROUP  
from pyrogram.types import Message

tclient = AsyncIOMotorClient(MONGO_DB)
tdb = tclient["telegram_bot"]
token = tdb["tokens"]
 
 
async def create_ttl_index():
    await token.create_index("expires_at", expireAfterSeconds=0)
 
 
 
Param = {}
 
 
async def generate_random_param(length=8):
    """Generate a random parameter."""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))
 
 
async def get_shortened_url(deep_link):
    api_url = f"https://{WEBSITE_URL}/api?api={AD_API}&url={deep_link}"
 
     
    async with aiohttp.ClientSession() as session:
        async with session.get(api_url) as response:
            if response.status == 200:
                data = await response.json()   
                if data.get("status") == "success":
                    return data.get("shortenedUrl")
    return None
 
 
async def is_user_verified(user_id):
    """Check if a user has an active session."""
    session = await token.find_one({"user_id": user_id})
    return session is not None



# List of big reactions that work
#BIG_REACTIONS = ["❤️", "🔥", "😘", "😍", "🥰", "👻", "🆒", "⚡", "😎", "🌚"]

#@app.on_message(filters.command("") & ~filters.edited)
#async def auto_react_on_all_commands(client: Client, message: Message):
    #try:
        #emoji = random.choice(BIG_REACTIONS)
        #await message.react(emoji)
    #except Exception as e:
        #print(f"[!] Reaction failed: {e}")

 
 
@app.on_message(filters.command("start"))
async def token_handler(client, message):
    """Handle the /start command."""
    
    # ---- GROUP / SUPERGROUP MESSAGE ----
    if message.chat.type in ["group", "supergroup"]:
        
        group_btn = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🤖 Add Me to Your PM", url="https://t.me/YourBotUsername?start=grp")
            ],
            [
                InlineKeyboardButton("📢 Main Channel", url="https://t.me/II_LevelUP_II")
            ]
        ])

        await message.reply_text(
            "**👋 Hello Group Members!**\n\n"
            "⚡ *I'm active in this group!* \n"
            "🚀 Use me in private chat to extract posts safely.\n\n"
            "**➡ Click below to start me in PM.**",
            reply_markup=group_btn
        )
        return
    
    """Handle the /start command."""
    join = 0  # Skip force sub always
    # join = await subscribe(client, message)
    # if join == 1:
    #     return

    user_id = message.chat.id
    try:
        from toxic.core.mongo.users_db import add_user
        await add_user(user_id)
    except Exception as e:
        print(f"Error adding user in start command: {e}")

    if len(message.command) <= 1:
        image_url = "https://freeimage.host/i/F5dGOsj"
        join_button = InlineKeyboardButton("✈️ Main Channel", url="https://t.me/II_LevelUP_II")
        premium_contact = InlineKeyboardButton("👑 𝗖𝗛𝗢𝗦𝗘𝗡 𝗢𝗡𝗘 ⚝", url="https://t.me/CHOSEN_ONEx_bot")
        keyboard = InlineKeyboardMarkup([
            [join_button],
            [premium_contact]
        ])

        # Mention the user in the caption
        user_mention = message.from_user.mention if message.from_user else "User"

        await message.reply_photo(
            image_url,            
            caption=(
                f"👋 **Hello, {user_mention}! Welcome to Xtractor Bot!**\n\n"
                "🔒 I Can Help You To **Extract And Forward Content** from channels or groups that don't allow forwarding.😎\n\n"
                "📌 **How to use me:**\n"
                "➤ Just **send me the post link** if it's Public\n"
                "🔓 I'll send that post(s) to you.\n\n"
                "> 💠 Use /batch For Bulk Forwarding...💀\n"
                "🔐 **Private channel post?**\n\n"                
                "➤ First do /login to extract posts from Private Channel\n\n"
                "💡 Need help? Send /guide\n For More Features Use /settings 😉 \n\n"
            ),
            reply_markup=keyboard,
        )
        return
 
    param = message.command[1] if len(message.command) > 1 else None
    freecheck = await chk_user(message, user_id)
    if freecheck != 1:
        await message.reply("You are a premium user Cutie 😉\n\n Just /start & Use Me  🫠")
        return
 
     
    if param:
        if user_id in Param and Param[user_id] == param:
             
            await token.insert_one({
                "user_id": user_id,
                "param": param,
                "created_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=3),
            })
            del Param[user_id]   
            await message.reply("✅ You have been verified successfully! Enjoy your session for next 3 hours.")
            return
        else:
            await message.reply("❌ Invalid or expired verification link. Please generate a new token.")       
            return



games = {}

def empty_board():
    return [" " for _ in range(9)]

def render_board(board):
    symbols = [s if s != " " else "⬜" for s in board]
    rows = [symbols[i:i+3] for i in range(0, 9, 3)]
    return "\n".join(["".join(row) for row in rows])

def check_winner(board):
    combos = [(0,1,2),(3,4,5),(6,7,8),
              (0,3,6),(1,4,7),(2,5,8),
              (0,4,8),(2,4,6)]
    for a,b,c in combos:
        if board[a] == board[b] == board[c] != " ":
            return board[a]
    if " " not in board:
        return "draw"
    return None

def build_keyboard(game_id):
    board = games[game_id]["board"]
    buttons = []
    for i in range(0, 9, 3):
        row = []
        for j in range(3):
            cell = board[i+j]
            emoji = cell if cell != " " else "⬜"
            row.append(InlineKeyboardButton(emoji, callback_data=f"{game_id}_{i+j}"))
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def register_tictactoe(app):
    @app.on_message(filters.command("startgame"))
    async def start_game(client, message):
        player_x = message.from_user.id
        games[player_x] = {
            "board": empty_board(),
            "turn": "X",
            "players": {"X": player_x, "O": None}
        }
        await message.reply_text(
            "🎮 *Tic Tac Toe Started!*\nSend this to a friend — whoever presses first joins as O.",
            reply_markup=build_keyboard(player_x)
        )

    @app.on_callback_query()
    async def handle_move(client, query):
        try:
            data = query.data.split("_")
            game_id = int(data[0])
            move = int(data[1])

            if game_id not in games:
                await query.answer("Game not found!", show_alert=True)
                return

            game = games[game_id]
            player_id = query.from_user.id

            # Assign O if not joined yet
            if game["players"]["O"] is None and player_id != game["players"]["X"]:
                game["players"]["O"] = player_id

            # Turn check
            symbol = "X" if player_id == game["players"]["X"] else "O"
            if symbol != game["turn"]:
                await query.answer("⏳ Not your turn!", show_alert=True)
                return

            board = game["board"]
            if board[move] != " ":
                await query.answer("❌ Spot already taken!")
                return

            # Make move
            board[move] = "❌" if symbol == "X" else "⭕"
            winner = check_winner(board)

            if winner:
                if winner == "draw":
                    text = "🤝 *It's a draw!*"
                else:
                    text = f"🏆 *{winner} wins!*"
                await query.message.edit_text(
                    text + "\n\n" + render_board(board),
                    reply_markup=None
                )
                del games[game_id]
            else:
                game["turn"] = "O" if symbol == "X" else "X"
                await query.message.edit_text(
                    f"🎮 *Tic Tac Toe*\nTurn: {game['turn']}\n\n{render_board(board)}",
                    reply_markup=build_keyboard(game_id)
                )

        except Exception as e:
            await query.answer(f"Error: {e}", show_alert=True)


# 🔗 /sharelink command
@app.on_message(filters.command("shareme"))
async def sharelink_handler(client, message: Message):
    bot = await client.get_me()
    bot_username = bot.username

    bot_link = f"https://t.me/{bot_username}?start=True"
    share_link = f"https://t.me/share/url?url={bot_link}&text=🚀%20Check%20out%20this%20awesome%20bot%20to%20unlock%20restricted%20Telegram%20content!%20Try%20now%20"

    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Me With Others 🫠", url=share_link)]
    ])

    await message.reply_text(
        f"✨ **Spread the Magic!**\n\n"
        f"Help others discover this bot that can save **restricted channel media**, even if forwarding is off! 🔒\n\n"
        f"Click a button below 👇 share me with your friends!",
        reply_markup=reply_markup
    )

 
