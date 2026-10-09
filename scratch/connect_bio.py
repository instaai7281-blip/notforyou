import os

path = "toxic/modules/start.py"
with open(path, "r", encoding="utf-8", errors="ignore") as f:
    content = f.read()

# Add import for check_user_bio_access at top if not present
if "from toxic.core.bio_check import check_user_bio_access" not in content:
    content = "from toxic.core.bio_check import check_user_bio_access\n" + content

# Replace restrict_unauthorized_users handler
old_func = '''@app.on_message(filters.private, group=-1)
async def restrict_unauthorized_users(client, message: Message):
    # Authorization checks disabled - all commands and features unlocked for all users!
    return'''

new_func = '''@app.on_message(filters.private, group=-1)
async def restrict_unauthorized_users(client, message: Message):
    if not message.text and not message.media:
        return
    if not await check_user_bio_access(client, message):
        await message.stop_propagation()'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Successfully updated start.py with bio check middleware!")
else:
    print("Could not find old_func pattern in start.py")
