import os

path = "toxic/core/get_func.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

# Add FileReferenceExpired import if needed
if "from pyrogram.errors import FileReferenceExpired" not in text:
    text = "from pyrogram.errors import FileReferenceExpired\n" + text

# 1. Update download_media in get_msg
old_dl_1 = '''            file = await client.download_media(
                msg,
                file_name=target_file_path,            
                progress_args=("╔══━⚡️ Downloading ⚡️━══╗\\n", edit, time.time()),
                progress=progress_bar
            )
        except Exception as e:
            print(f"Download error: {e}")
            file = None'''

new_dl_1 = '''            file = await client.download_media(
                msg,
                file_name=target_file_path,            
                progress_args=("╔══━⚡️ Downloading ⚡️━══╗\\n", edit, time.time()),
                progress=progress_bar
            )
        except FileReferenceExpired:
            print("[DOWNLOAD] FileReferenceExpired encountered! Refetching fresh message...")
            try:
                msg = await client.get_messages(msg.chat.id, msg.id)
                file = await client.download_media(
                    msg,
                    file_name=target_file_path,            
                    progress_args=("╔══━⚡️ Downloading ⚡️━══╗\\n", edit, time.time()),
                    progress=progress_bar
                )
            except Exception as ex:
                print(f"[DOWNLOAD] Refetch download failed: {ex}")
                file = None
        except Exception as e:
            print(f"Download error: {e}")
            file = None'''

# 2. Update audio thumb download 1
old_thumb_1 = '''            if not thumb_path and msg.audio.thumbs:
                try:
                    thumb_path = await app.download_media(msg.audio.thumbs[0].file_id)
                    original_thumb_downloaded = True
                except Exception as e:
                    print(f"[AUDIO THUMB] Error downloading original audio thumb: {e}")
                    thumb_path = None'''

new_thumb_1 = '''            if not thumb_path and msg.audio and msg.audio.thumbs:
                try:
                    thumb_path = await app.download_media(msg.audio.thumbs[0].file_id)
                    original_thumb_downloaded = True
                except FileReferenceExpired:
                    try:
                        fresh_m = await app.get_messages(msg.chat.id, msg.id)
                        if fresh_m and fresh_m.audio and fresh_m.audio.thumbs:
                            thumb_path = await app.download_media(fresh_m.audio.thumbs[0].file_id)
                            original_thumb_downloaded = True
                    except Exception as ex:
                        print(f"[AUDIO THUMB] Refetch thumb failed: {ex}")
                        thumb_path = None
                except Exception as e:
                    print(f"[AUDIO THUMB] Error downloading original audio thumb: {e}")
                    thumb_path = None'''

# 3. Update download_media in get_bulk_msg
old_dl_2 = '''            file = await userbot.download_media(
                msg,
                file_name=target_file_path,
                progress=progress_bar,
                progress_args=("╭─────────────────────╮\\n│      **__Downloading__...**\\n├─────────────────────┤", edit, time.time())
            )'''

new_dl_2 = '''            try:
                file = await userbot.download_media(
                    msg,
                    file_name=target_file_path,
                    progress=progress_bar,
                    progress_args=("╭─────────────────────╮\\n│      **__Downloading__...**\\n├─────────────────────┤", edit, time.time())
                )
            except FileReferenceExpired:
                print("[BULK DOWNLOAD] FileReferenceExpired encountered! Refetching fresh message...")
                try:
                    msg = await userbot.get_messages(msg.chat.id, msg.id)
                    file = await userbot.download_media(
                        msg,
                        file_name=target_file_path,
                        progress=progress_bar,
                        progress_args=("╭─────────────────────╮\\n│      **__Downloading__...**\\n├─────────────────────┤", edit, time.time())
                    )
                except Exception as ex:
                    print(f"[BULK DOWNLOAD] Refetch download failed: {ex}")
                    file = None'''

if old_dl_1 in text:
    text = text.replace(old_dl_1, new_dl_1)
    print("Replaced old_dl_1 successfully!")
else:
    print("Could not find old_dl_1")

if old_thumb_1 in text:
    text = text.replace(old_thumb_1, new_thumb_1)
    print("Replaced old_thumb_1 successfully!")
else:
    print("Could not find old_thumb_1")

if old_dl_2 in text:
    text = text.replace(old_dl_2, new_dl_2)
    print("Replaced old_dl_2 successfully!")
else:
    print("Could not find old_dl_2")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)
