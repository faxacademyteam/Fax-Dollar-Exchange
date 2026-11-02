# Dollar By Sale Bot - How to Run

## Quick Start

```bash
cd /Users/tawhid/dollar-bot
source venv/bin/activate
python3 bot.py
```

## Commands

| Command | Description |
|---------|-------------|
| `/health` | Check if bot is running |
| `/stats` | Show user statistics |
| `/sync` | Manual sync from Google Sheets |

## How It Works

1. **New user** sends message → Bot sends eligibility question
2. **5-minute timer** starts
3. User can:
   - Click **Yes** button → Saved as ELIGIBLE
   - Click **No** button → Saved as NOT_ELIGIBLE
   - Type **"yes"** or **"no"** → Same as buttons
   - Type anything else → Question resent, new 5-min timer
   - **Don't respond** in 5 min → Saved as NO_RESPONSE, question deleted

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Main bot entry point |
| `eligibility.py` | Question logic, timeout handling |
| `database.py` | SQLite operations |
| `sheets_api.py` | Google Sheets API client |
| `config.py` | Environment configuration |

## Configuration

Edit `.env` file:
```
BOT_TOKEN=your_bot_token
GROUP_CHAT_ID=-1004430323577
SHEETS_API_URL=https://script.google.com/macros/s/YOUR_ID/exec
DATABASE_PATH=./data/bot.db
```

## Logs

Check logs in terminal where bot is running.

## Troubleshooting

- **"Conflict: terminated by other getUpdates request"** → Only run one bot instance
- **Bot not responding** → Check `.env` has correct token and chat ID
- **API errors** → Check SHEETS_API_URL is correct
