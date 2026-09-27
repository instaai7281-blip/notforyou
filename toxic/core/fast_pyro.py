import asyncio
import os
import math
import time
from pyrogram.raw.functions.messages import GetMessages
from pyrogram.raw.types import InputMessageID
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

async def download_chunk(client, dc_id, file_id, offset, limit):
    return await client.get_file_chunk(dc_id, file_id, offset, limit)

async def fast_download(client, message, file_name, progress_bar, progress_args):
    # This is a placeholder for a more complex parallel downloader if needed.
    # For now, we will use the built-in download_media but ensure it's called efficiently.
    # pyrofork/pyrogram already uses multiple chunks if configured.
    return await client.download_media(
        message,
        file_name=file_name,
        progress=progress_bar,
        progress_args=progress_args
    )

async def fast_upload(client, file_path, caption, thumb, duration, width, height, progress_bar, progress_args):
    # Similar to download, we ensure the client is configured for high speed.
    # pyrofork's send_video/document are generally fast.
    # The key is often the 'workers' parameter in the Client constructor.
    ext = file_path.split('.')[-1].lower()
    if ext in ['mp4', 'mkv', 'mov']:
        return await client.send_video(
            chat_id=progress_args[1].chat.id,
            video=file_path,
            caption=caption,
            thumb=thumb,
            duration=duration,
            width=width,
            height=height,
            progress=progress_bar,
            progress_args=progress_args
        )
    else:
        return await client.send_document(
            chat_id=progress_args[1].chat.id,
            document=file_path,
            caption=caption,
            thumb=thumb,
            progress=progress_bar,
            progress_args=progress_args
        )
