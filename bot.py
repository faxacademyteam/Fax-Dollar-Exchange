import logging
import asyncio
import traceback
import sys
import os
import time
from telegram.ext import Application, CommandHandler
from telegram import Update
from telegram.error import NetworkError, TimedOut, Conflict
from telegram.ext import ContextTypes, filters
from config import config
from database import init_db
from eligibility import get_eligibility_handlers, startup_sync, periodic_sync
from schedule import setup_scheduler, safety_check_job, get_today_schedule

# Configure logging - minimal format for low memory
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Reduce noise from libraries - saves CPU/memory
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)


async def post_init(application: Application) -> None:
    """Run after application starts - initialize DB and start scheduler."""
    logger.info("Bot starting up...")

    # Initialize database
    init_db()

    # Startup schedule check - recover from any missed unlock/lock
    await safety_check_job(application.bot)

    # Startup sync from Google Sheets
    await startup_sync(application)

    # Start scheduler (daily unlock/lock + 24h periodic sync)
    scheduler = setup_scheduler(application.bot)
    scheduler.start()
    application.bot_data["scheduler"] = scheduler

    logger.info("Bot fully started - scheduler running")


async def post_shutdown(application: Application) -> None:
    """Run on shutdown - stop scheduler."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    # Close HTTP client
    from sheets_api import sheets_api
    sheets_api.close()

    logger.info("Bot shut down complete")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler - logs errors but keeps bot running for network issues."""
    error = context.error
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    # Skip expected polling errors - bot should keep running
    if isinstance(error, (NetworkError, TimedOut)):
        logger.warning("Network issue (polling will auto-recover): %s", error)
        return
    if isinstance(error, Conflict):
        # Conflict means another bot instance is running - just log it
        logger.warning("Bot conflict detected (another instance running): %s", error)
        return

    # Log all other errors
    logger.error("Unhandled error in update handler:\n%s", tb)

    # Notify admin only for unexpected errors (not network issues)
    admin_id = config.ADMIN_USER_ID
    if admin_id:
        try:
            error_msg = (
                f"⚠️ <b>Bot Error Alert</b>\n\n"
                f"<b>Type:</b> {type(error).__name__}\n"
                f"<b>Message:</b> {str(error)[:500]}"
            )
            await context.bot.send_message(chat_id=admin_id, text=error_msg, parse_mode="HTML")
        except Exception as notify_err:
            logger.error("Failed to send error notification: %s", notify_err)


def is_admin(update: Update) -> bool:
    """Check if message is from admin in private chat (DM)."""
    if not update.effective_chat or not update.effective_user:
        return False
    # Must be private chat
    if update.effective_chat.type != "private":
        return False
    # Must match admin user ID
    return str(update.effective_user.id) == str(config.ADMIN_USER_ID)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /stats - show user statistics (Admin DM only)."""
    if not is_admin(update):
        return

    from database import count_users, count_eligible, count_not_eligible
    total = count_users()
    eligible = count_eligible()
    not_eligible = count_not_eligible()
    pending = total - eligible - not_eligible

    await update.message.reply_text(
        f"📊 <b>Bot Statistics</b>\n\n"
        f"Total users: {total}\n"
        f"✅ Eligible: {eligible}\n"
        f"❌ Not Eligible: {not_eligible}\n"
        f"⏳ Pending: {pending}",
        parse_mode="HTML"
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /health - check bot status (Admin DM only)."""
    if not is_admin(update):
        return

    from database import count_users
    total = count_users()
    await update.message.reply_text(
        f"✅ <b>Bot is running normally</b>\n\n"
        f"Total users in DB: {total}",
        parse_mode="HTML"
    )


async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /sync - manual sync from API (Admin DM only)."""
    if not is_admin(update):
        return

    await update.message.reply_text("🔄 Syncing from API...")
    await periodic_sync(update.get_bot())
    await update.message.reply_text("✅ Sync complete")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /schedule - show today's schedule status (Admin DM only)."""
    if not is_admin(update):
        return

    import pytz
    from datetime import datetime
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")

    from schedule_db import get_today_schedule
    records = get_today_schedule(date_str)

    unlock = records.get("unlock")
    lock = records.get("lock")

    def fmt(rec):
        if not rec:
            return "⏳ No record"
        status_icon = "✅ Success" if rec["status"] == "success" else ("❌ Failed" if rec["status"] == "failed" else "⏳ Pending")
        time_str = rec.get("actual_time", "")
        if time_str:
            try:
                time_str = time_str.split("T")[1][:8] if "T" in time_str else time_str[:8]
            except Exception:
                pass
        retries = rec.get("retry_count", 0)
        return f"{status_icon} | {time_str or 'Not run'} | Retries: {retries}"

    text = (
        f"📅 <b>Schedule Status — {date_str}</b>\n\n"
        f"🟢 Unlock (10:00): {fmt(unlock)}\n"
        f"🔴 Lock (18:00):   {fmt(lock)}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /stop - stop the bot immediately (Admin DM only)."""
    if not is_admin(update):
        return

    await update.message.reply_text("🛑 <b>Stopping bot...</b> Goodbye!", parse_mode="HTML")
    logger.info("Stop command received from admin. Shutting down...")
    
    # Give message time to send, then exit
    await asyncio.sleep(1)
    os._exit(0)


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /restart - restart the bot (Admin DM only)."""
    if not is_admin(update):
        return

    await update.message.reply_text("🔄 <b>Restarting bot...</b> Please wait a moment.", parse_mode="HTML")
    logger.info("Restart command received from admin. Restarting process...")

    await asyncio.sleep(1)
    # Restart the python process
    os.execv(sys.executable, [sys.executable] + sys.argv)


def main() -> None:
    """Main entry point - polling mode only, optimized for low resource usage."""
    config.validate()

    max_retries = 10
    for attempt in range(max_retries):
        try:
            application = (
                Application.builder()
                .token(config.BOT_TOKEN)
                .post_init(post_init)
                .post_shutdown(post_shutdown)
                .concurrent_updates(True)
                .read_timeout(30)
                .write_timeout(30)
                .connect_timeout(30)
                .pool_timeout(30)
                .build()
            )

            application.add_error_handler(error_handler)
            for handler in get_eligibility_handlers():
                application.add_handler(handler)
            application.add_handler(CommandHandler("stats", stats_command))
            application.add_handler(CommandHandler("health", health_command))
            application.add_handler(CommandHandler("sync", sync_command))
            application.add_handler(CommandHandler("schedule", schedule_command))
            application.add_handler(CommandHandler("stop", stop_command))
            application.add_handler(CommandHandler("restart", restart_command))

            logger.info("Starting polling mode (Admin ID: %s)", config.ADMIN_USER_ID)
            application.run_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=30
            )
            break
        except (NetworkError, TimedOut) as e:
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                logger.warning("Network error during startup: %s. Retrying in %ds... (%d/%d)", e, wait, attempt + 1, max_retries)
                time.sleep(wait)
            else:
                logger.critical("Max retries (%d) reached. Bot cannot start. Shutting down.", max_retries)
                sys.exit(1)
        except Exception as e:
            logger.critical("Unhandled startup error: %s", e)
            logger.critical(traceback.format_exc())
            sys.exit(1)


if __name__ == "__main__":
    main()