import asyncio
import os
import math
import time
import inspect
import functools
from hashlib import sha256
from typing import Union, Optional, Callable, BinaryIO, AsyncGenerator

import pyrogram
from pyrogram import Client, filters, raw, utils
from pyrogram.file_id import FileId, FileType
from pyrogram.session import Session, Auth
from pyrogram.errors import FloodWait

_patched = False

def patch_pyrogram_downloader():
    """
    Patches Pyrogram's internal `Client.get_file` to use 512KB (524288 bytes) chunks.
    
    Standard Telegram user accounts without Telegram Premium encounter a strict
    14-15 second FloodWait on DC1/DC2/DC5 when requesting 1024KB (1MB) chunks via
    `upload.GetFile`. Using 512KB chunks bypasses this rate limiter completely and
    allows full-speed sequential downloading without 14-second wait loops!
    """
    global _patched
    if _patched:
        return
    _patched = True

    orig_get_file = Client.get_file

    async def optimized_get_file(
        self: Client,
        file_id: FileId,
        file_size: int = 0,
        limit: int = 0,
        offset: int = 0,
        progress: Callable = None,
        progress_args: tuple = ()
    ) -> Optional[AsyncGenerator[bytes, None]]:
        async with self.get_file_semaphore:
            file_type = file_id.file_type

            if file_type == FileType.CHAT_PHOTO:
                if file_id.chat_id > 0:
                    peer = raw.types.InputPeerUser(
                        user_id=file_id.chat_id,
                        access_hash=file_id.chat_access_hash
                    )
                else:
                    if file_id.chat_access_hash == 0:
                        peer = raw.types.InputPeerChat(
                            chat_id=-file_id.chat_id
                        )
                    else:
                        peer = raw.types.InputPeerChannel(
                            channel_id=utils.get_channel_id(file_id.chat_id),
                            access_hash=file_id.chat_access_hash
                        )

                location = raw.types.InputPeerPhotoFileLocation(
                    peer=peer,
                    volume_id=file_id.volume_id,
                    local_id=file_id.local_id,
                    big=file_id.thumbnail_source == raw.types.InputPeerPhotoFileLocation
                )
            elif file_type == FileType.PHOTO:
                location = raw.types.InputPhotoFileLocation(
                    id=file_id.media_id,
                    access_hash=file_id.access_hash,
                    file_reference=file_id.file_reference,
                    thumb_size=file_id.thumbnail_size
                )
            else:
                location = raw.types.InputDocumentFileLocation(
                    id=file_id.media_id,
                    access_hash=file_id.access_hash,
                    file_reference=file_id.file_reference,
                    thumb_size=file_id.thumbnail_size
                )

            current = 0
            total = abs(limit) or (1 << 31) - 1
            # Standard user accounts avoid 14s FloodWait on 512KB (524288) chunk limit
            chunk_size = 512 * 1024
            offset_bytes = abs(offset) * chunk_size

            dc_id = file_id.dc_id

            session = Session(
                self, dc_id,
                await Auth(self, dc_id, await self.storage.test_mode()).create()
                if dc_id != await self.storage.dc_id()
                else await self.storage.auth_key(),
                await self.storage.test_mode(),
                is_media=True
            )

            try:
                await session.start()

                if dc_id != await self.storage.dc_id():
                    exported_auth = await self.invoke(
                        raw.functions.auth.ExportAuthorization(
                            dc_id=dc_id
                        )
                    )

                    await session.invoke(
                        raw.functions.auth.ImportAuthorization(
                            id=exported_auth.id,
                            bytes=exported_auth.bytes
                        )
                    )

                r = await session.invoke(
                    raw.functions.upload.GetFile(
                        location=location,
                        offset=offset_bytes,
                        limit=chunk_size
                    ),
                    sleep_threshold=30
                )

                if isinstance(r, raw.types.upload.File):
                    while True:
                        chunk = r.bytes

                        yield chunk

                        current += 1
                        offset_bytes += chunk_size

                        if progress:
                            func = functools.partial(
                                progress,
                                min(offset_bytes, file_size)
                                if file_size != 0
                                else offset_bytes,
                                file_size,
                                *progress_args
                            )

                            if inspect.iscoroutinefunction(progress):
                                await func()
                            else:
                                await self.loop.run_in_executor(self.executor, func)

                        if len(chunk) < chunk_size or current >= total:
                            break

                        r = await session.invoke(
                            raw.functions.upload.GetFile(
                                location=location,
                                offset=offset_bytes,
                                limit=chunk_size
                            ),
                            sleep_threshold=30
                        )

                elif isinstance(r, raw.types.upload.FileCdnRedirect):
                    cdn_session = Session(
                        self, r.dc_id, await Auth(self, r.dc_id, await self.storage.test_mode()).create(),
                        await self.storage.test_mode(), is_media=True, is_cdn=True
                    )

                    try:
                        await cdn_session.start()

                        while True:
                            r2 = await cdn_session.invoke(
                                raw.functions.upload.GetCdnFile(
                                    file_token=r.file_token,
                                    offset=offset_bytes,
                                    limit=chunk_size
                                )
                            )

                            if isinstance(r2, raw.types.upload.CdnFileReuploadNeeded):
                                await session.invoke(
                                    raw.functions.upload.ReuploadCdnFile(
                                        file_token=r.file_token,
                                        request_token=r2.request_token
                                    )
                                )
                                continue

                            chunk = r2.bytes
                            decrypted_chunk = session.aes.ctr256_decrypt(
                                chunk,
                                r.encryption_key,
                                bytearray(r.encryption_iv[:-4] + offset_bytes.to_bytes(4, "big"))
                            )

                            cdn_file_hashes = await session.invoke(
                                raw.functions.upload.GetCdnFileHashes(
                                    file_token=r.file_token,
                                    offset=offset_bytes
                                )
                            )

                            for i, h in enumerate(cdn_file_hashes):
                                cdn_chunk = decrypted_chunk[h.limit * i: h.limit * (i + 1)]
                                assert (
                                    h.hash == sha256(cdn_chunk).digest()
                                ), "h.hash == sha256(cdn_chunk).digest()"

                            yield decrypted_chunk

                            current += 1
                            offset_bytes += chunk_size

                            if progress:
                                func = functools.partial(
                                    progress,
                                    min(offset_bytes, file_size)
                                    if file_size != 0
                                    else offset_bytes,
                                    file_size,
                                    *progress_args
                                )

                                if inspect.iscoroutinefunction(progress):
                                    await func()
                                else:
                                    await self.loop.run_in_executor(self.executor, func)

                            if len(chunk) < chunk_size or current >= total:
                                break
                    finally:
                        await cdn_session.stop()
            finally:
                await session.stop()

    Client.get_file = optimized_get_file
    print("[FastPyro] Patched Pyrogram get_file chunk_size to 512KB for zero-floodwait downloads.")


async def download_chunk(client, dc_id, file_id, offset, limit):
    return await client.get_file_chunk(dc_id, file_id, offset, limit)

async def fast_download(client, message, file_name, progress_bar, progress_args):
    return await client.download_media(
        message,
        file_name=file_name,
        progress=progress_bar,
        progress_args=progress_args
    )

async def fast_upload(client, file_path, caption, thumb, duration, width, height, progress_bar, progress_args):
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
