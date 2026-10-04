# ---------------------------------------------------
# File Name: speedtest.py
# Description: Advanced high-speed server speedtest module for Toxic Bot Pro.
# ---------------------------------------------------

import time
import asyncio
from pyrogram import filters
from pyrogram.enums import ParseMode
from telethon import events

from toxic import app, botStartTime
from toxic import sex as gagan

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d '
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h '
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m '
    seconds = int(seconds)
    result += f'{seconds}s'
    return result.strip()


def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None or size_in_bytes == 0:
        return '0 B'
    index = 0
    size = float(size_in_bytes)
    while size >= 1024 and index < len(SIZE_UNITS) - 1:
        size /= 1024
        index += 1
    return f'{round(size, 2)} {SIZE_UNITS[index]}'


def speed_convert(bps: float) -> str:
    """Converts bits per second to human-readable Mbps and MB/s."""
    if not bps or bps <= 0:
        return "0.00 Mbps (0.00 MB/s)"
    mbps = bps / 1_000_000
    mbytes_sec = bps / (8 * 1024 * 1024)
    if mbytes_sec >= 1.0:
        return f"{mbps:.2f} Mbps ({mbytes_sec:.2f} MB/s)"
    else:
        kbytes_sec = bps / (8 * 1024)
        return f"{mbps:.2f} Mbps ({kbytes_sec:.2f} KB/s)"


def run_speedtest_sync():
    """Runs speedtest synchronously inside a worker thread to avoid blocking Pyrogram/Telethon asyncio loop."""
    import speedtest
    s = speedtest.Speedtest()
    s.get_best_server()
    s.download()
    s.upload()
    try:
        s.results.share()
    except Exception:
        pass
    return s.results.dict()


def build_speedtest_report(result: dict) -> str:
    dl_bps = result.get('download', 0)
    ul_bps = result.get('upload', 0)
    ping = result.get('ping', 0)
    
    server = result.get('server', {})
    client = result.get('client', {})
    
    server_name = server.get('name', 'Unknown')
    server_country = server.get('country', 'Unknown')
    sponsor = server.get('sponsor', 'Unknown')
    latency = server.get('latency', ping)
    
    isp = client.get('isp', 'Unknown')
    client_country = client.get('country', 'Unknown')
    
    sent_bytes = result.get('bytes_sent', 0)
    recv_bytes = result.get('bytes_received', 0)
    
    uptime_str = get_readable_time(time.time() - botStartTime)
    
    report_text = (
        "<blockquote><b>⚡ XTRACTOR BOT PRO — SERVER SPEED TEST ⚡</b></blockquote>\n\n"
        "<blockquote><b>📊 SPEED METRICS:</b>\n"
        f"• <b>📥 Download Speed:</b> <code>{speed_convert(dl_bps)}</code>\n"
        f"• <b>📤 Upload Speed:</b> <code>{speed_convert(ul_bps)}</code>\n"
        f"• <b>⚡ Latency / Ping:</b> <code>{ping:.1f} ms</code>\n"
        f"• <b>⏱️ Bot Uptime:</b> <code>{uptime_str}</code></blockquote>\n\n"
        "<blockquote><b>🌐 TEST SERVER:</b>\n"
        f"• <b>Sponsor:</b> <code>{sponsor}</code>\n"
        f"• <b>Location:</b> <code>{server_name}, {server_country}</code>\n"
        f"• <b>Server Latency:</b> <code>{latency:.1f} ms</code></blockquote>\n\n"
        "<blockquote><b>👤 HOST & NETWORK DETAILS:</b>\n"
        f"• <b>ISP:</b> <code>{isp}</code> ({client_country})\n"
        f"• <b>Data Sent:</b> <code>{get_readable_file_size(sent_bytes)}</code>\n"
        f"• <b>Data Received:</b> <code>{get_readable_file_size(recv_bytes)}</code></blockquote>\n\n"
        "🖤 <b>Sᴛꪮʟᴇɴ Hᴀᴘᴘɪɴᴇss ⚝</b>"
    )
    return report_text


# -------------------------------------------------------------
# PYROGRAM HANDLER FOR /speedtest & /speed
# -------------------------------------------------------------
@app.on_message(filters.command(["speedtest", "speed"]))
async def pyrogram_speedtest_cmd(client, message):
    status_msg = await message.reply(
        "⚡ <b>Running High-Speed Server Test... Please wait...</b>",
        parse_mode=ParseMode.HTML
    )
    
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_speedtest_sync)
        report = build_speedtest_report(result)
        image_url = result.get('share')
        
        if image_url:
            try:
                await status_msg.delete()
                await message.reply_photo(
                    photo=image_url,
                    caption=report,
                    parse_mode=ParseMode.HTML
                )
                return
            except Exception:
                pass

        await status_msg.edit_text(report, parse_mode=ParseMode.HTML)
    except Exception as err:
        print(f"[SpeedTest Error]: {err}")
        await status_msg.edit_text(
            f"❌ <b>Speedtest Failed:</b> <code>{err}</code>",
            parse_mode=ParseMode.HTML
        )


# -------------------------------------------------------------
# TELETHON HANDLER FOR /speedtest & /speed
# -------------------------------------------------------------
@gagan.on(events.NewMessage(incoming=True, pattern=r'^/(speedtest|speed)'))
async def telethon_speedtest_cmd(event):
    status_msg = await event.reply("⚡ Running High-Speed Server Test... Please wait...")
    
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, run_speedtest_sync)
        report = build_speedtest_report(result)
        image_url = result.get('share')
        
        if image_url:
            try:
                await event.reply(report, file=image_url, parse_mode='html')
                await status_msg.delete()
                return
            except Exception:
                pass

        await status_msg.edit(report, parse_mode='html')
    except Exception as err:
        print(f"[Telethon SpeedTest Error]: {err}")
        try:
            await status_msg.edit(f"❌ <b>Speedtest Failed:</b> <code>{err}</code>", parse_mode='html')
        except Exception:
            pass
