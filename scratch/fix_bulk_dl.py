import os

path = "toxic/core/get_func.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    lines = f.readlines()

new_block = [
    '            target_file_path = os.path.join(temp_dir, filename)\n',
    '            try:\n',
    '                file = await userbot.download_media(\n',
    '                    msg,\n',
    '                    file_name=target_file_path,\n',
    '                    progress=progress_bar,\n',
    '                    progress_args=("╭─────────────────────╮\\n│      **__Downloading__...**\\n├─────────────────────┤", edit, time.time())\n',
    '                )\n',
    '            except FileReferenceExpired:\n',
    '                print("[BULK DOWNLOAD] FileReferenceExpired encountered! Refetching fresh message...")\n',
    '                try:\n',
    '                    msg = await userbot.get_messages(resolved_chat_id, message_id)\n',
    '                    file = await userbot.download_media(\n',
    '                        msg,\n',
    '                        file_name=target_file_path,\n',
    '                        progress=progress_bar,\n',
    '                        progress_args=("╭─────────────────────╮\\n│      **__Downloading__...**\\n├─────────────────────┤", edit, time.time())\n',
    '                    )\n',
    '                except Exception as ex:\n',
    '                    print(f"[BULK DOWNLOAD] Refetch download failed: {ex}")\n',
    '                    file = None\n',
    '            except Exception as e:\n',
    '                print(f"[BULK DOWNLOAD] Download error: {e}")\n',
    '                file = None\n'
]

lines[1431:1438] = new_block

with open(path, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("Replaced bulk download block by line indexes successfully!")
