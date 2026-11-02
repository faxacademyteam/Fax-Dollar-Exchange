import logging
import asyncio
from datetime import datetime, timedelta
import pytz
from telegram import Bot
from telegram.error import TelegramError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import config
from schedule_db import (
    init_schedule_db,
    get_today_record,
    insert_schedule_record,
    update_schedule_record,
    purge_old_records,
    get_today_schedule
)
from eligibility import periodic_sync

logger = logging.getLogger(__name__)

OPEN_NOTICE = (
    "<blockquote>⏰ <b>Buy-Sell Time: 10 AM – 6 PM</b></blockquote>\n\n"
    "🟢 <b>গ্রুপ OPEN হয়েছে! 🏦</b>\n\n"
    "আজ সকাল ১০টা থেকে ডলার Buy-Sell কার্যক্রম "
    "শুরু হয়েছে। এখন আপনারা ডলার কেনা-বেচা "
    "করতে পারবেন।\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🔴 <b>Group Auto OFF:</b> সন্ধ্যা ৬টায়।\n\n"
    "<blockquote>🙏 <b>ধন্যবাদ | Thank You</b> 🤍</blockquote>"
)

CLOSE_NOTICE = (
    "<blockquote>⏰ <b>Buy-Sell Time: 10 AM – 6 PM</b></blockquote>\n\n"
    "🔴 <b>আজকের মতো গ্রুপ বন্ধ!</b>\n"
    "আজ সন্ধ্যা ৬টায় গ্রুপ অটো OFF হয়েছে।\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🟢 <b>Tomorrow:</b> সকাল ১০টায় গ্রুপ "
    "আবার অটো OPEN হবে।\n\n"
    "<blockquote>🙏 <b>ধন্যবাদ | Thank You</b> 🤍</blockquote>"
)

PERMISSIONS_KEYS = [
    "can_send_messages",
    "can_send_audios",
    "can_send_documents",
    "can_send_photos",
    "can_send_videos",
    "can_send_video_notes",
    "can_send_voice_notes",
    "can_send_polls",
    "can_send_other_messages",
    "can_add_web_page_previews",
]


def build_permissions(allow: bool) -> dict:
    return {key: allow for key in PERMISSIONS_KEYS}


async def set_group_permissions(bot: Bot, allow: bool) -> None:
    """Enable or disable all message-sending permissions for the group."""
    permissions = build_permissions(allow)
    try:
        await bot.set_chat_permissions(
            chat_id=config.get_chat_id_int(),
            permissions=permissions,
            use_independent_chat_permissions=True
        )
        logger.info("Group permissions updated: %s", "UNLOCKED" if allow else "LOCKED")
    except TelegramError as e:
        logger.error("Failed to set chat permissions: %s", e)
        raise


async def send_pin_wait_unpin(bot: Bot, text: str) -> str:
    """Send message, pin with notification, wait 60s, then unpin. Returns message_id."""
    try:
        message = await bot.send_message(
            chat_id=config.get_chat_id_int(),
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        msg_id = str(message.message_id)

        await bot.pin_chat_message(
            chat_id=config.get_chat_id_int(),
            message_id=message.message_id,
            disable_notification=False
        )
        logger.info("Message %s sent and pinned with notification", msg_id)

        # Unpin in background task so scheduler is not blocked for 60 seconds
        async def unpin_later():
            await asyncio.sleep(60)
            try:
                await bot.unpin_chat_message(
                    chat_id=config.get_chat_id_int(),
                    message_id=int(msg_id)
                )
                logger.info("Message %s unpinned after 60 seconds", msg_id)
            except Exception as unpin_err:
                logger.warning("Failed to unpin message %s: %s", msg_id, unpin_err)

        asyncio.create_task(unpin_later())
        return msg_id

    except TelegramError as e:
        logger.error("Failed to send/pin message: %s", e)
        raise


async def notify_admin(bot: Bot, text: str) -> None:
    """Send DM to admin if ADMIN_USER_ID is set."""
    if not config.ADMIN_USER_ID:
        return
    try:
        await bot.send_message(
            chat_id=config.ADMIN_USER_ID,
            text=text,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Failed to notify admin: %s", e)


async def execute_unlock(bot: Bot, is_recovery: bool = False) -> bool:
    """Perform group unlock, send notice, and log to schedule.db."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    now_iso = now.isoformat()

    rec = get_today_record(date_str, "unlock")
    if rec and rec.get("status") == "success":
        logger.info("Unlock already logged as success for today (%s)", date_str)
        return True

    retry_count = (rec.get("retry_count", 0) + 1) if rec else 1
    if not rec:
        insert_schedule_record(
            date_str=date_str,
            event_type="unlock",
            scheduled_time="10:00",
            status="pending",
            retry_count=1
        )

    try:
        logger.info("Executing unlock job (Recovery: %s)", is_recovery)
        await set_group_permissions(bot, allow=True)
        msg_id = await send_pin_wait_unpin(bot, OPEN_NOTICE)

        update_schedule_record(
            date_str=date_str,
            event_type="unlock",
            actual_time=now_iso,
            status="success",
            retry_count=retry_count,
            message_id=msg_id
        )

        if is_recovery:
            await notify_admin(
                bot,
                f"⚠️ <b>Schedule Recovery Notice</b>\n\n"
                f"Group unlock at 10:00 AM was missed/pending.\n"
                f"Auto-recovered and UNLOCKED at {now.strftime('%H:%M:%S')} ({config.TIMEZONE})."
            )
        else:
            await notify_admin(
                bot,
                f"🟢 <b>Schedule Status</b>\n\nGroup successfully UNLOCKED at 10:00 AM."
            )
        return True

    except Exception as e:
        logger.error("Unlock execution failed (attempt %d): %s", retry_count, e)
        update_schedule_record(
            date_str=date_str,
            event_type="unlock",
            status="failed",
            retry_count=retry_count
        )
        if retry_count >= config.MAX_RETRIES:
            await notify_admin(
                bot,
                f"❌ <b>Schedule Alert</b>\n\n"
                f"Failed to UNLOCK group after {retry_count} attempts.\n"
                f"Error: {e}"
            )
        return False


async def execute_lock(bot: Bot, is_recovery: bool = False) -> bool:
    """Perform group lock, send notice, and log to schedule.db."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    now_iso = now.isoformat()

    rec = get_today_record(date_str, "lock")
    if rec and rec.get("status") == "success":
        logger.info("Lock already logged as success for today (%s)", date_str)
        return True

    retry_count = (rec.get("retry_count", 0) + 1) if rec else 1
    if not rec:
        insert_schedule_record(
            date_str=date_str,
            event_type="lock",
            scheduled_time="18:00",
            status="pending",
            retry_count=1
        )

    try:
        logger.info("Executing lock job (Recovery: %s)", is_recovery)
        await set_group_permissions(bot, allow=False)
        msg_id = await send_pin_wait_unpin(bot, CLOSE_NOTICE)

        update_schedule_record(
            date_str=date_str,
            event_type="lock",
            actual_time=now_iso,
            status="success",
            retry_count=retry_count,
            message_id=msg_id
        )

        if is_recovery:
            await notify_admin(
                bot,
                f"⚠️ <b>Schedule Recovery Notice</b>\n\n"
                f"Group lock at 6:00 PM was missed/pending.\n"
                f"Auto-recovered and LOCKED at {now.strftime('%H:%M:%S')} ({config.TIMEZONE})."
            )
        else:
            await notify_admin(
                bot,
                f"🔴 <b>Schedule Status</b>\n\nGroup successfully LOCKED at 6:00 PM."
            )
        return True

    except Exception as e:
        logger.error("Lock execution failed (attempt %d): %s", retry_count, e)
        update_schedule_record(
            date_str=date_str,
            event_type="lock",
            status="failed",
            retry_count=retry_count
        )
        if retry_count >= config.MAX_RETRIES:
            await notify_admin(
                bot,
                f"❌ <b>Schedule Alert</b>\n\n"
                f"Failed to LOCK group after {retry_count} attempts.\n"
                f"Error: {e}"
            )
        return False


async def safety_check_job(bot: Bot) -> None:
    """30-minute safety timer & startup check — checks DB and auto-recovers missed actions."""
    tz = pytz.timezone(config.TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    hour = now.hour

    logger.debug("Running 30-min schedule safety check (Date: %s, Hour: %d)", date_str, hour)

    # 1. Between 10:00 AM and 5:59 PM -> Check if 10 AM unlock was missed
    if 10 <= hour < 18:
        rec = get_today_record(date_str, "unlock")
        if not rec or rec.get("status") != "success":
            # Is recovery if past 10:05
            is_rec = not (hour == 10 and now.minute < 5)
            logger.warning("Safety check: Unlock missing/failed for today. Triggering unlock (Recovery: %s)", is_rec)
            await execute_unlock(bot, is_recovery=is_rec)

    # 2. At or after 6:00 PM (18:00+) -> Check if 6 PM lock was missed
    elif hour >= 18:
        rec = get_today_record(date_str, "lock")
        if not rec or rec.get("status") != "success":
            # Is recovery if past 18:05
            is_rec = not (hour == 18 and now.minute < 5)
            logger.warning("Safety check: Lock missing/failed for today. Triggering lock (Recovery: %s)", is_rec)
            await execute_lock(bot, is_recovery=is_rec)


async def purge_old_schedule_job() -> None:
    """Daily job at 00:30 AM to delete schedule logs older than 7 days."""
    tz = pytz.timezone(config.TIMEZONE)
    cutoff = (datetime.now(tz) - timedelta(days=config.SCHEDULE_RETENTION_DAYS)).strftime("%Y-%m-%d")
    deleted = purge_old_records(cutoff)
    logger.info("Purged %d old schedule records older than %s", deleted, cutoff)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Create and configure the async scheduler (runs in bot's event loop)."""
    init_schedule_db()

    scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)

    # 10:00 AM - Unlock
    scheduler.add_job(
        execute_unlock,
        CronTrigger(hour=10, minute=0, timezone=config.TIMEZONE),
        args=[bot, False],
        id="unlock_job",
        replace_existing=True
    )

    # 6:00 PM - Lock
    scheduler.add_job(
        execute_lock,
        CronTrigger(hour=18, minute=0, timezone=config.TIMEZONE),
        args=[bot, False],
        id="lock_job",
        replace_existing=True
    )

    # Every 30 minutes - Safety Check Timer
    scheduler.add_job(
        safety_check_job,
        IntervalTrigger(minutes=config.SAFETY_CHECK_INTERVAL_MIN, timezone=config.TIMEZONE),
        args=[bot],
        id="safety_check_job",
        replace_existing=True
    )

    # Daily at 00:30 AM - Purge old logs (> 7 days)
    scheduler.add_job(
        purge_old_schedule_job,
        CronTrigger(hour=0, minute=30, timezone=config.TIMEZONE),
        id="purge_schedule_job",
        replace_existing=True
    )

    # Periodic sync from API (every 24 hours by default)
    scheduler.add_job(
        periodic_sync,
        IntervalTrigger(hours=config.SYNC_INTERVAL_HOURS, timezone=config.TIMEZONE),
        args=[bot],
        id="periodic_sync",
        replace_existing=True
    )

    logger.info(
        "Scheduler configured: Unlock 10:00, Lock 18:00, Safety check every %dmin, Sync every %dh (%s)",
        config.SAFETY_CHECK_INTERVAL_MIN,
        config.SYNC_INTERVAL_HOURS,
        config.TIMEZONE
    )
    return scheduler
