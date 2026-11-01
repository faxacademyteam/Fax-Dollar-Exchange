import logging
import asyncio
import traceback
import sys
import os
from telegram.ext import Application, CommandHandler
from telegram import Update
from telegram.ext import ContextTypes, filters
from config import config
from database import init_db
from eligibility import get_eligibility_handlers, startup_sync, periodic_sync
from schedule import setup_scheduler

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
    """Global error handler - notify admin on error and shut down immediately."""
    error = context.error
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))

    # Log the full error
    logger.error("Unhandled error in update handler:\n%s", tb)

    # Notify admin and shut down
    admin_id = config.ADMIN_USER_ID
    if admin_id:
        try:
            error_msg = (
                f"🚨 <b>Bot Error / Crash Alert</b>\n\n"
                f"<b>Type:</b> {type(error).__name__}\n"
                f"<b>Message:</b> {str(error)[:500]}\n"
                f"<b>Status:</b> Bot is shutting down immediately."
            )
            await context.bot.send_message(chat_id=admin_id, text=error_msg, parse_mode="HTML")
        except Exception as notify_err:
            logger.error("Failed to send error notification: %s", notify_err)

    # Exit process immediately on crash
    logger.critical("Shutting down due to unhandled error...")
    os._exit(1)


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

    # Build application with minimal settings for low resource usage
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

    # Add error handler
    application.add_error_handler(error_handler)

    # Add eligibility handlers (group message processing)
    for handler in get_eligibility_handlers():
        application.add_handler(handler)

    # Add admin commands (case-insensitive via lowercase)
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("sync", sync_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("restart", restart_command))

    # Polling mode only - optimized for low CPU
    logger.info("Starting polling mode (Admin ID: %s)", config.ADMIN_USER_ID)
    application.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
        poll_interval=1.0,
        timeout=30
    )


if __name__ == "__main__":
    main()