<h1 align="center">
  ⚡ Telegram Restricted Content Saver & Topic Mirror Bot PRO ⚡
</h1>

A high-performance, enterprise-grade Telegram Bot built with Pyrogram and Telethon for high-speed restricted content cloning, complete topic-to-topic forum mirroring, automated batch processing, media watermarking, and subscription management.

---

## 🌟 Key Features

### 🚀 High-Speed Topic Mirroring Hub (`/mirror`)
- **Complete Forum Supergroup Mirroring**: Automatically scans all topics from source forum and clones them into the target forum supergroup.
- **Auto-Topic Creation & Mapping**: Creates matching forum topics with identical topic titles and icons.
- **Smart Continuation & Resume Engine**: MongoDB-backed session persistence. If interrupted or redeployed, resumes instantly from the exact last mirrored message without creating duplicate topics.
- **Interactive Session Management**: Modify target chat IDs, delete sessions, or continue mirroring with a single click.
- **Real-Time Live Dashboard**: Shows active topic name, file count progress, live transfer speed, ETA, and an interactive **Skip Topic** button.

### 📥 Multi-Source Content Extraction (`/batch`, single links)
- **Restricted Channel/Group Bypassing**: Download and clone protected content (photos, videos, documents, audios, voice notes, stickers, text) from private/public channels and groups.
- **Telethon + Pyrogram Fast Uploader**: Up to 4GB file upload support using userbot session strings.
- **Multi-Client Concurrency**: Automatic load balancing across multiple worker sessions.
- **File Splitting**: Automatically splits files exceeding 2GB/4GB limits.

### 🎨 Advanced Custom Branding & Cleaners
- **Dynamic Blockquote Formatting**: Converts captions and branding tags into clean native Telegram blockquote boxes.
- **Filename Sanitization**: Removes all `@usernames`, `@channels`, and promotional signatures from filenames across all formats (Videos, PDFs, Documents, Audios).
- **Custom Watermarking & Thumbnails**: Support for PDF watermarking and custom/extracted video thumbnail generation.

### 💎 Monetization & User Management
- **Subscription Tiers**: Built-in free vs. premium user limits (`/add`, `/rem`, `/myplan`, `/check`).
- **Shortlink Ads System**: Token-based ad verification system for free users.
- **Auto-Broadcast & Channel Forwarding**: Broadcast announcements and auto-forward messages across channels and groups.

---

## 🛠️ Environment Configuration

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID from my.telegram.org | `12345678` |
| `API_HASH` | Telegram API Hash from my.telegram.org | `abcdef1234567890` |
| `BOT_TOKEN` | Telegram Bot Token from @BotFather | `123456:ABC-DEF...` |
| `MONGO_DB` | MongoDB Atlas connection string | `mongodb+srv://...` |
| `OWNER_ID` | Telegram User ID of the owner | `6947378236` |
| `LOG_GROUP` | Telegram Supergroup ID for logs | `-100...` |
| `CHANNEL_ID` | Force subscribe channel ID (optional) | `0` |
| `STRINGS` | Space-separated Telethon userbot session strings | `session1 session2` |
| `FREEMIUM_LIMIT` | Daily message limit for free users | `10` |
| `PREMIUM_LIMIT` | Daily message limit for premium users | `5000` |

---

## 📦 Deployment

### Local / VPS
```bash
git clone <repo-url>
cd <repo-folder>
pip install -r requirements.txt
python -m toxic
```

---

## 📋 Terms & Conditions

1. **Educational & Personal Use Only**: This software is developed strictly for educational, backup, and personal utility purposes.
2. **Compliance**: Users and deployers are solely responsible for ensuring compliance with Telegram's Terms of Service and applicable local copyright laws.
3. **No Resale or Redistribution**: Reselling, leaking, or unauthorized public redistribution of this proprietary repository is strictly prohibited.
4. **As-Is Warranty**: The software is provided "as-is" without warranties of any kind regarding third-party API changes or Telegram service interruptions.

---

## 📜 License
Proprietary / All rights reserved.
