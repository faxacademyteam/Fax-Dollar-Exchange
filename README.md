# Dollar By Sale Group Bot

A high-performance, production-ready Telegram bot for managing membership eligibility and automated scheduling in large trading groups (100+ members, 100+ messages/day).

---

## 🌟 Comprehensive System Overview & Features

### 1. Membership Eligibility System (`eligibility.py`)
- **Automated Verification**: When a new user sends a message in the group, the bot checks local SQLite database.
- **Exclusions**: 
  - Group **Admins** and members with **"Fax Team"** badges are automatically bypassed (never asked).
  - Users who have already answered `YES` or `NO` are never asked again.
- **Daily Reset**: Users who timed out (`NO_RESPONSE`) or are `PENDING` are asked once per day. If they message on a subsequent day, the bot resends the question.
- **5-Minute Timeout**: 
  - If the user does not respond within 5 minutes, their message is deleted, and they are automatically saved as `NO_RESPONSE` (`NOT_ELIGIBLE`) in both local SQLite and Google Sheets API.
- **Inline Buttons**: Secure per-user callback buttons (`✅ Yes` / `❌ No`) ensuring only the targeted user can click.

### 2. Schedule Management System (`schedule.py`)
- **10:00 AM (UTC+6)**: Automatically unlocks the group (enables all messaging permissions) and pins a styled "Open" announcement for 60 seconds.
- **6:00 PM (UTC+6)**: Automatically locks the group (disables messaging permissions to prevent after-hours spam) and pins a "Closed" announcement for 60 seconds.

### 3. Data Sync & Backup Architecture (`sheets_api.py` & `database.py`)
- **Master Backup**: Google Sheets stores all user eligibility records permanently.
- **Local SQLite Cache**: Handles all message checks locally for instant response times and zero API rate-limit issues.
- **Startup Sync**: Pulls all users from Google Sheets into local SQLite when the bot starts.
- **Periodic Sync**: Automatically syncs every 24 hours in the background.

### 4. Secure Admin Commands (DM Only) (`bot.py`)
Admin commands are strictly restricted to Private Chat (DM) with the designated `ADMIN_USER_ID` (`1007815760`) and **will not work** inside the group chat.

| Command | Description |
| :--- | :--- |
| `/stats` | View membership breakdown (Total, Eligible, Not Eligible, Pending) |
| `/health` | Check bot running status and local DB user count |
| `/sync` | Force an immediate manual sync from Google Sheets API |
| `/stop` | Shut down the bot process cleanly |
| `/restart` | Restart the bot process |

- **Crash Alerts**: If an unhandled exception or crash occurs, the bot automatically sends the error traceback to the Admin via Telegram DM and shuts down immediately.

---

## 🚀 Railway Deployment Guide (Low Cost, Low RAM/CPU)

This project is fully containerized and optimized for **Railway.com** using the Free or Starter tier.

### Step 1: Environment Variables (`.env` / Railway Dashboard)
Set these variables in your Railway project settings:

```env
BOT_TOKEN=9257370907:AAH...c1A8
GROUP_CHAT_ID=-1004430323577
SHEETS_API_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
ADMIN_USER_ID=1007815760
LOG_LEVEL=WARNING
SYNC_INTERVAL_HOURS=24
```

### Step 2: Deploy to Railway
1. Push this folder to a GitHub repository.
2. Go to [Railway.app](https://railway.app), click **New Project** → **Deploy from GitHub repo**.
3. Select your repository. Railway will automatically detect the `Dockerfile` and `Procfile`.
4. Add your Environment Variables in the Railway Dashboard.
5. Deploy! (Runs in polling mode automatically).

---

## 📂 Project File Structure

```
dollar-bot/
├── bot.py              # Main entry point, error handler, admin commands
├── config.py           # Environment config loader
├── database.py         # SQLite connection pool, WAL mode, queries
├── eligibility.py      # Question flow, timeouts, button handlers, sync
├── schedule.py         # APScheduler daily unlock/lock/sync jobs
├── sheets_api.py       # Google Sheets API client (connection pooled)
├── requirements.txt    # Minimal dependencies
├── Dockerfile          # Railway container configuration
├── Procfile            # Railway process definition
├── RAILWAY.md          # Railway deployment notes
└── README.md           # This comprehensive guide
```

---

## ⚙️ Low Resource Performance Optimizations

| Optimization | Implementation | Benefit |
| :--- | :--- | :--- |
| **SQLite WAL Mode** | `PRAGMA journal_mode=WAL` | High concurrency, zero lockups |
| **Thread-Local DB** | Reused database connections | Eliminates connection overhead |
| **HTTP Pooling** | `httpx.Client` with keepalive | Faster API requests, lower RAM |
| **In-Memory Jobs** | Dict mapping user IDs to jobs | $O(1)$ timeout cancellations |
| **Clean Logging** | `LOG_LEVEL=WARNING` in prod | Reduces disk I/O and CPU usage |
| **Indexed Queries** | SQLite indexes on `user_id`, `status` | Instant lookups for 100+ users |

*Expected Railway Resource Usage: **~40–60MB RAM**, **<1% CPU** idle.*

---

## 🛠️ Maintenance & Troubleshooting

- **Changing Bot Texts**: Edit the text constants at the top of `eligibility.py` (`QUESTION_TEXT`, `YES_TEXT`, `NO_TEXT`, etc.).
- **Modifying Schedule Times**: Edit `cron(hour=10, minute=0)` and `cron(hour=18, minute=0)` in `schedule.py`.
- **Database Reset**: Delete `data/bot.db` and restart the bot to perform a clean startup sync.
