# Dollar By Sale Group Bot

A high-performance, production-ready Telegram bot for managing membership eligibility and automated scheduling in trading groups.

---

## 📁 Project Structure

```
dollar-bot/
├── bot.py              # Main entry point & admin command handler
├── config.py           # Configuration & environment loader
├── database.py         # SQLite connection pool & WAL mode
├── eligibility.py      # Question flow, timeouts, buttons & sync
├── schedule.py         # Daily unlock/lock & periodic sync scheduler
├── sheets_api.py       # Google Sheets API client (connection pooled)
├── requirements.txt    # Python dependencies
├── Dockerfile          # Railway container configuration
├── Procfile            # Railway process definition
├── docs/text/          # Documentation & setup guides
└── README.md           # This overview
```

---

## 🚀 Quick Setup & Deployment

### 1. Environment Variables (`.env`)
```env
BOT_TOKEN=your_bot_token_here
GROUP_CHAT_ID=-1004430323577
SHEETS_API_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
ADMIN_USER_ID=1007815760
LOG_LEVEL=WARNING
SYNC_INTERVAL_HOURS=24
```

### 2. Run Locally
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python bot.py
```

### 3. Deploy to Railway
1. Push to GitHub.
2. Link repo in [Railway.app](https://railway.app).
3. Add environment variables in Railway dashboard.

---

## 🔒 Admin Commands (DM Only)
Send these commands in a **Private Chat (DM)** with the bot:
- `/stats` - View membership statistics
- `/health` - Check bot health & DB count
- `/sync` - Force manual sync from API
- `/stop` - Stop bot process
- `/restart` - Restart bot process
