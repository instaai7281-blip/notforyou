import os

path = "toxic/core/get_func.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Pattern for msg.audio in get_msg
old_audio_block_1 = '''        if msg.audio:
            if not await is_enabled(sender, "audio"):
                return
            caption_html = format_caption_to_html(caption) if caption else None
            result = await app.send_audio(target_chat_id, file, caption=caption_html, parse_mode=ParseMode.HTML, reply_to_message_id=topic_id)
            await result.copy(LOG_GROUP)
            await check_and_auto_forward(sender, result, caption=caption_html)
            await edit.delete(1)
            return'''

new_audio_block_1 = '''        if msg.audio:
            if not await is_enabled(sender, "audio"):
                return

            # 1. Poster / Thumbnail logic: Custom thumbnail if set, else Original Audio poster/thumbs
            thumb_path = thumbnail(sender)
            original_thumb_downloaded = False
            if not thumb_path and msg.audio.thumbs:
                try:
                    thumb_path = await app.download_media(msg.audio.thumbs[0].file_id)
                    original_thumb_downloaded = True
                except Exception as e:
                    print(f"[AUDIO THUMB] Error downloading original audio thumb: {e}")
                    thumb_path = None

            # 2. Artist Name logic: Set performer for songs, keep intact for course/batch audio
            title = msg.audio.title or msg.audio.file_name or "Audio"
            title_lower = title.lower()
            is_lecture = any(kw in title_lower for kw in ['lecture', 'class', 'chapter', 'batch', 'session', 'ep', 'part', 'lec', 'course'])
            performer = "💗....⚝ 𓇢𓆸" if not is_lecture else msg.audio.performer

            # 3. Caption logic: Song Name + Brand Tag
            tag = get_user_branding_tag(sender)
            filename_clean = clean_surrogates(title)
            song_caption = f"> **{filename_clean}**\\n\\n> **{tag}**"
            caption_html = format_caption_to_html(song_caption)

            result = await app.send_audio(
                target_chat_id,
                file,
                caption=caption_html,
                performer=performer,
                title=title,
                thumb=thumb_path,
                parse_mode=ParseMode.HTML,
                reply_to_message_id=topic_id
            )

            if original_thumb_downloaded and thumb_path and os.path.exists(thumb_path):
                try:
                    os.remove(thumb_path)
                except Exception:
                    pass

            await result.copy(LOG_GROUP)
            await check_and_auto_forward(sender, result, caption=caption_html)
            await edit.delete(1)
            return'''

old_audio_block_2 = '''            elif msg.audio:
                await app.send_audio(target_chat_id, file, caption=final_caption, reply_to_message_id=topic_id)'''

new_audio_block_2 = '''            elif msg.audio:
                thumb_path = thumbnail(sender)
                original_thumb_downloaded = False
                if not thumb_path and msg.audio.thumbs:
                    try:
                        thumb_path = await app.download_media(msg.audio.thumbs[0].file_id)
                        original_thumb_downloaded = True
                    except Exception as e:
                        print(f"[AUDIO THUMB] Error downloading original audio thumb: {e}")
                        thumb_path = None

                title = msg.audio.title or msg.audio.file_name or "Audio"
                title_lower = title.lower()
                is_lecture = any(kw in title_lower for kw in ['lecture', 'class', 'chapter', 'batch', 'session', 'ep', 'part', 'lec', 'course'])
                performer = "💗....⚝ 𓇢𓆸" if not is_lecture else msg.audio.performer

                tag = get_user_branding_tag(sender)
                filename_clean = clean_surrogates(title)
                song_caption = f"> **{filename_clean}**\\n\\n> **{tag}**"
                caption_html = format_caption_to_html(song_caption)

                result = await app.send_audio(
                    target_chat_id,
                    file,
                    caption=caption_html,
                    performer=performer,
                    title=title,
                    thumb=thumb_path,
                    parse_mode=ParseMode.HTML,
                    reply_to_message_id=topic_id
                )

                if original_thumb_downloaded and thumb_path and os.path.exists(thumb_path):
                    try:
                        os.remove(thumb_path)
                    except Exception:
                        pass'''

if old_audio_block_1 in text:
    text = text.replace(old_audio_block_1, new_audio_block_1)
    print("Replaced old_audio_block_1 successfully!")
else:
    print("Could not find old_audio_block_1")

if old_audio_block_2 in text:
    text = text.replace(old_audio_block_2, new_audio_block_2)
    print("Replaced old_audio_block_2 successfully!")
else:
    print("Could not find old_audio_block_2")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
