# ============================================================
# DOLLAR BY SALE BOT - Railway Configuration
# Optimized for Low CPU/RAM
# ============================================================

# Recommended Railway Settings:
# - Plan: Free tier (500MB RAM) or Starter ($5/month for more RAM)
# - Region: Asia/South (closest to Bangladesh)
# - Health Check: Disabled (Telegram polling doesn't need HTTP endpoint)

# Environment Variables:
# BOT_TOKEN=your_bot_token_here
# GROUP_CHAT_ID=-1004430323577
# SHEETS_API_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
# ADMIN_USER_ID=your_telegram_user_id (for error notifications)
# LOG_LEVEL=WARNING  (production: use WARNING to reduce I/O)
# SYNC_INTERVAL_HOURS=24  (increase to 48 to reduce API calls)

# Memory Optimization Tips:
# - Set LOG_LEVEL=WARNING in production
# - Use Python 3.9-slim Docker base (already configured)
# - No unnecessary packages installed
# - SQLite WAL mode for efficient concurrent access

# For low-cost Railway hosting:
# - Use Free tier (500MB RAM, 0.1 CPU)
# - Set LOG_LEVEL=WARNING for production to reduce overhead
# - Increase SYNC_INTERVAL_HOURS=48 to reduce API calls