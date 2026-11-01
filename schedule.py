import logging
from telegram import Bot
from telegram.error import TelegramError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from config import config

from eligibility import periodic_sync

logger = logging.getLogger(__name__)

OPEN_NOTICE = (
    "<blockquote>⏰ <b>Buy-Sell Time: 10 AM – 6 PM</b></blockquote>\n\n"
    "🟢 <b>গ্রুপ OPEN হযেছ! 🏦</b>\n\n"
    "আজ সকাল ১০টা থেকে ডলার Buy-Sell কার্যক্রম "
    "শুরু হযেছে। এখন আপনারা ডলার কেনা-বেচা "
    "করতে পারবেন।\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "🔴 <b>Group Auto OFF:</b> সন্ধ্যা ৬টায়।\n\n"
    "<blockquote>🙏 <b>ধন্যবাদ | Thank You</b> 🤍</blockquote>"
)

CLOSE_NOTICE = (
    "<blockquote>⏰ <b>Buy-Sell Time: 10 AM – 6 PM</b></blockquote>\n\n"
    "🔴 <b>আজকের মতো গ্রুপ বন্ধ!</b>\n"
    "আজ সন্ধ্যা ৬টায় গ্রুপ অটো OFF হযেছে।\n"
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


async def send_pin_wait_unpin(bot: Bot, text: str) -> None:
    """Send message, pin with notification, wait 60s, then unpin."""
    try:
        message = await bot.send_message(
            chat_id=config.get_chat_id_int(),
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        message_id = message.message_id

        await bot.pin_chat_message(
            chat_id=config.get_chat_id_int(),
            message_id=message_id,
            disable_notification=False
        )
        logger.info("Message %d sent and pinned with notification", message_id)

        import asyncio
        await asyncio.sleep(60)

        await bot.unpin_chat_message(
            chat_id=config.get_chat_id_int(),
            message_id=message_id
        )
        logger.info("Message %d unpinned after 60 seconds", message_id)

    except TelegramError as e:
        logger.error("Failed to send/pin/unpin message: %s", e)
        raise


async def unlock_job(bot: Bot) -> None:
    """10:00 AM job - unlock group and send OPEN notice."""
    logger.info("Running unlock job (10:00 AM)")
    await set_group_permissions(bot, allow=True)
    await send_pin_wait_unpin(bot, OPEN_NOTICE)


async def lock_job(bot: Bot) -> None:
    """6:00 PM job - lock group and send OFF notice."""
    logger.info("Running lock job (6:00 PM)")
    await set_group_permissions(bot, allow=False)
    await send_pin_wait_unpin(bot, CLOSE_NOTICE)


def setup_scheduler(bot: Bot) -> BackgroundScheduler:
    """Create and configure the background scheduler."""
    scheduler = BackgroundScheduler(timezone=config.TIMEZONE)

    # 10:00 AM - Unlock
    scheduler.add_job(
        unlock_job,
        CronTrigger(hour=10, minute=0, timezone=config.TIMEZONE),
        args=[bot],
        id="unlock_job",
        name="Unlock group at 10:00 AM",
        replace_existing=True
    )

    # 6:00 PM - Lock
    scheduler.add_job(
        lock_job,
        CronTrigger(hour=18, minute=0, timezone=config.TIMEZONE),
        args=[bot],
        id="lock_job",
        name="Lock group at 6:00 PM",
        replace_existing=True
    )

    # Periodic sync from API (every 24 hours by default)
    scheduler.add_job(
        periodic_sync,
        IntervalTrigger(hours=config.SYNC_INTERVAL_HOURS, timezone=config.TIMEZONE),
        args=[bot],
        id="periodic_sync",
        name=f"Periodic API sync every {config.SYNC_INTERVAL_HOURS}h",
        replace_existing=True
    )

    logger.info(
        "Scheduler configured: unlock 10:00, lock 18:00, sync every %dh (UTC+6)",
        config.SYNC_INTERVAL_HOURS
    )
    return scheduler