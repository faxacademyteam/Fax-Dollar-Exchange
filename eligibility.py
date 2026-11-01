import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, CallbackQueryHandler, filters
from telegram import Bot

from database import get_user, upsert_user
from sheets_api import sheets_api
from config import config

logger = logging.getLogger(__name__)

# Pre-compute timezone for faster date calculations
import pytz
TIMEZONE = pytz.timezone(config.TIMEZONE)

# Cache for tracking active timeout jobs per user
# Key: user_id, Value: job ID
_active_timeout_jobs = {}


# ============================================================
# BOT TEXTS - EDIT HERE
# ============================================================

QUESTION_TEXT = (
    "গ্রুপটি শুধুমাত্র যাদের Vantage অ্যাকাউন্ট আছে, "
    "তাদের Dollar Buy/Sell-এর জন্য। "
    "গ্রুপটি ব্যবহার করার আগতে অনুগ্রহ করে জানান,\n\n"
    "<blockquote><b>আপনার কি Vantage অ্যাকাউন্ট আছে?</b></blockquote>\n\n"
    "✅ Yes / হ্যাঁ\n"
    "❌ No / না\n"
)

YES_TEXT = (
    "<blockquote>✅ <b>ধন্যবাদ! আপনি এই Dollar Buy/Sell গ্রুপের "
    "জন্য eligible।</b></blockquote>\n\n"
    "আপনি এখন গ্রুপে <b>Dollar Buy/Sell করতে পারেন।</b> "
    "যেকোনো সহায়তার জন্য Support Team-এর সাথে যোগাযোগ করুন।"
)

NO_TEXT = (
    "<blockquote>❌ <b>দুঃখিত! আপনি এই Dollar Buy/Sell গ্রুপের "
    "জন্য eligible নন।</b></blockquote>\n\n"
    "অনুরোধ করে <b>Support Team-এর সাথে যোগাযোগ করুন।</b> "
    "অথবা, <b>২৪ ঘণ্টা পর আপনাকে auto গ্রুপ থেকে Remove করা হবে।</b>"
)

PENDING_TEXT = (
    "⏳ <b>আপনি এখনো উত্তর দেননি।</b>\n\n"
    "আপনার Vantage অ্যাকাউন্ট আছে কিনা তা জানান। "
    "অনুরোধ করে <b>Yes</b> অথবা <b>No</b> লিখুন অথবা নিচের বাটনে ক্লিক করুন।"
)

TIMED_OUT_TEXT = (
    "⏰ <b>আপনি 5 মিনিট সময় শেষ করেছেন।</b>\n\n"
    "আপনার প্রশ্নের উত্তর দেওয়ার সুযোগ শেষ হয়েছে。\n\n"
    "আবার চেষ্টা করতে নতুন মেসেজ পাঠান।"
)


def build_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Build inline keyboard with per-user callback data."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Yes / হ্যাঁ", callback_data=f"vantage_yes_{user_id}"),
        InlineKeyboardButton("❌ No / না", callback_data=f"vantage_no_{user_id}"),
    ]])


async def startup_sync(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sync users from Google Sheets to SQLite on bot startup."""
    logger.info("Starting startup sync from Google Sheets...")
    users = sheets_api.fetch_all()
    if not users:
        logger.info("No users found in Sheets (or API error)")
        return

    synced = 0
    tz = TIMEZONE
    today = datetime.now(tz).strftime("%Y-%m-%d")

    for user in users:
        telegram_user_id = str(user.get("Telegram User ID", "")).strip()
        if not telegram_user_id:
            continue

        telegram_name = str(user.get("Telegram Name", "")).strip()
        username = str(user.get("Username", "")).strip()
        has_vantage = str(user.get("Has Vantage Account", "")).strip().upper()
        status = str(user.get("Status", "")).strip().upper()
        created_at = str(user.get("Created At", "")).strip()

        # Keep string values to match API
        if has_vantage not in ("YES", "NO", "NO_RESPONSE"):
            has_vantage = "PENDING"
        status_clean = status if status in ("ELIGIBLE", "NOT_ELIGIBLE") else "PENDING"

        # Determine last_question_date from API's Created At
        last_question_date = None
        if has_vantage in ("NO_RESPONSE", "YES", "NO"):
            if created_at and len(created_at) >= 10:
                last_question_date = created_at[:10]

        upsert_user(
            telegram_user_id=telegram_user_id,
            telegram_name=telegram_name,
            username=username,
            has_vantage_account=has_vantage,
            status=status_clean,
            created_at=created_at,
            last_question_date=last_question_date
        )
        synced += 1

    logger.info("Startup sync complete: %d users synced", synced)


async def delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a message after it's shown."""
    job = context.job
    try:
        await context.bot.delete_message(chat_id=job.data["chat_id"], message_id=job.data["message_id"])
    except Exception:
        pass  # Message might already be deleted or unavailable


async def timeout_question_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-save user as NOT_ELIGIBLE with 'no response' when they don't respond within 5 minutes."""
    job = context.job
    user_id = job.data["user_id"]
    chat_id = job.data["chat_id"]
    question_message_id = job.data["question_message_id"]
    name = job.data.get("name", "Unknown")
    username = job.data.get("username", "")

    # Remove from active jobs tracking
    _active_timeout_jobs.pop(user_id, None)

    # Delete the original question message
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=question_message_id)
    except Exception:
        pass

    # Save to LOCAL DB first
    upsert_user(
        telegram_user_id=user_id,
        telegram_name=name,
        username=username,
        has_vantage_account="NO_RESPONSE",
        status="NOT_ELIGIBLE"
    )

    # Try update first, fall back to insert if user not in API yet
    result = sheets_api.update_user(
        telegram_user_id=user_id,
        telegram_name=name,
        username=username,
        has_vantage_account="NO_RESPONSE"
    )

    # If update fails because user not found, insert instead
    if not result.get("success") and "User not found" in str(result.get("error", "")):
        logger.info("User %s not in API yet, inserting...", user_id)
        result = sheets_api.insert_user(
            telegram_user_id=user_id,
            telegram_name=name,
            username=username,
            has_vantage_account="NO_RESPONSE"
        )

    if not result.get("success"):
        logger.warning("Sheets API operation failed for user %s (timeout): %s", user_id, result.get("error"))
    else:
        logger.info("API success for user %s (timeout): %s", user_id, result)


async def send_question_with_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, name: str, username: str = "") -> None:
    """Send eligibility question and schedule a 5-minute timeout."""
    try:
        msg = await update.message.reply_text(
            QUESTION_TEXT,
            reply_markup=build_keyboard(int(user_id)),
            parse_mode="HTML"
        )

        # Schedule auto-fail after 5 minutes if no response
        job = context.job_queue.run_once(
            timeout_question_job,
            300,
            data={
                "chat_id": update.effective_chat.id,
                "user_id": user_id,
                "name": name,
                "username": username,
                "question_message_id": msg.message_id
            }
        )

        # Track active timeout job
        _active_timeout_jobs[user_id] = job

    except Exception as e:
        logger.error("Failed to send question to user %s: %s", user_id, e)


async def resubmit_question(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, name: str, username: str = "") -> None:
    """Resend the eligibility question to a pending user."""
    try:
        # Send new question
        msg = await update.message.reply_text(
            PENDING_TEXT,
            reply_markup=build_keyboard(int(user_id)),
            parse_mode="HTML"
        )

        # Schedule new 5-minute timeout
        job = context.job_queue.run_once(
            timeout_question_job,
            300,
            data={
                "chat_id": update.effective_chat.id,
                "user_id": user_id,
                "name": name,
                "username": username,
                "question_message_id": msg.message_id
            }
        )

        # Track active timeout job
        _active_timeout_jobs[user_id] = job

    except Exception as e:
        logger.error("Failed to resend question to user %s: %s", user_id, e)


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any message in the group - check if user exists, prompt if new."""
    if not update.message or not update.message.from_user:
        return

    # Only process messages in the target group
    if str(update.effective_chat.id) != config.GROUP_CHAT_ID:
        return

    # Check for admin or Fax Team roles (member status)
    try:
        member = await context.bot.get_chat_member(
            chat_id=update.effective_chat.id, 
            user_id=update.message.from_user.id
        )
        # Admins have 'creator' or 'administrator' status
        if member.status in ('creator', 'administrator'):
            return
        # You can also check custom titles if this is a supergroup
        if member.custom_title and ('Admin' in member.custom_title or 'Fax Team' in member.custom_title):
            return
    except Exception as e:
        logger.warning("Could not check member status for %s: %s", update.message.from_user.id, e)
        # If we can't check, proceed with normal logic (safer to ask than to allow unverified)

    user = update.message.from_user
    telegram_user_id = str(user.id)

    # Check if user exists in local DB
    existing = get_user(telegram_user_id)

    if existing:
        has_vantage = existing.get("has_vantage_account")

        # If user explicitly answered YES or NO, never ask again
        if has_vantage in ("YES", "NO"):
            return

        # If user has NO_RESPONSE or PENDING, check daily reset
        if has_vantage in ("PENDING", "NO_RESPONSE"):
            tz = TIMEZONE
            today = datetime.now(tz).strftime("%Y-%m-%d")
            last_question_date = existing.get("last_question_date")

            if last_question_date == today:
                # Already asked today - silent ignore
                return

            # New day - resend question
            display_name = existing.get("telegram_name") or user.first_name or user.full_name or "বন্ধু"
            existing_username = existing.get("username") or ""
            await send_question_with_timeout(update, context, telegram_user_id, display_name, existing_username)
            # Update last_question_date
            upsert_user(
                telegram_user_id=telegram_user_id,
                telegram_name=display_name,
                username=existing_username,
                has_vantage_account=has_vantage,
                status=existing.get("status"),
                last_question_date=today
            )
            return

    # New user - save as pending and ask question
    tz = TIMEZONE
    today = datetime.now(tz).strftime("%Y-%m-%d")
    upsert_user(
        telegram_user_id=telegram_user_id,
        telegram_name=user.full_name,
        username=user.username or "",
        has_vantage_account="PENDING",
        status="PENDING",
        last_question_date=today
    )

    # Send question with 5-minute timeout
    display_name = user.first_name or user.full_name or "বন্ধু"
    await send_question_with_timeout(update, context, telegram_user_id, display_name, user.username or "")


async def on_callback_yes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'Yes' button press - only the user who was asked can click."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    if not callback_data.startswith("vantage_yes_"):
        await query.answer("❌ এই বাটন আপনার জন্য নয়", show_alert=True)
        return

    expected_user_id = callback_data.rsplit("_", 1)[-1]
    clicker_id = str(query.from_user.id)

    if clicker_id != expected_user_id:
        await query.answer("❌ আপনি এই প্রশ্নের উত্তর দেওয়ার অধিকার নাই", show_alert=True)
        return

    user = query.from_user
    telegram_user_id = clicker_id

    # Cancel the timeout job if it exists
    job = _active_timeout_jobs.pop(telegram_user_id, None)
    if job:
        job.schedule_removal()

    # Update local DB - use string values to match API
    upsert_user(
        telegram_user_id=telegram_user_id,
        telegram_name=user.full_name,
        username=user.username or "",
        has_vantage_account="YES",
        status="ELIGIBLE"
    )

    # Push to Google Sheets - try update first, fall back to insert
    result = sheets_api.update_user(
        telegram_user_id=telegram_user_id,
        telegram_name=user.full_name,
        username=user.username or "",
        has_vantage_account="YES"
    )

    # If update fails because user not found, insert instead
    if not result.get("success") and "User not found" in str(result.get("error", "")):
        logger.info("User %s not in API yet, inserting...", telegram_user_id)
        result = sheets_api.insert_user(
            telegram_user_id=telegram_user_id,
            telegram_name=user.full_name,
            username=user.username or "",
            has_vantage_account="YES"
        )

    if not result.get("success"):
        logger.warning("Sheets API operation failed for user %s: %s", telegram_user_id, result.get("error"))

    try:
        # Edit message with result
        await query.edit_message_text(YES_TEXT, parse_mode="HTML")

        # Auto-delete message after 5 minutes (300 seconds)
        context.job_queue.run_once(
            delete_message_job,
            300,
            data={
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id
            }
        )
    except Exception as e:
        logger.error("Failed to edit message for user %s: %s", telegram_user_id, e)


async def on_callback_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle 'No' button press - only the user who was asked can click."""
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    if not callback_data.startswith("vantage_no_"):
        await query.answer("❌ এই বাটন আপনার জন্য নয়", show_alert=True)
        return

    expected_user_id = callback_data.rsplit("_", 1)[-1]
    clicker_id = str(query.from_user.id)

    if clicker_id != expected_user_id:
        await query.answer("❌ আপনি এই প্রশ্নের উত্তর দেওয়ার অধিকার নাই", show_alert=True)
        return

    user = query.from_user
    telegram_user_id = clicker_id

    # Cancel the timeout job if it exists
    job = _active_timeout_jobs.pop(telegram_user_id, None)
    if job:
        job.schedule_removal()

    # Update local DB - use string values to match API
    upsert_user(
        telegram_user_id=telegram_user_id,
        telegram_name=user.full_name,
        username=user.username or "",
        has_vantage_account="NO",
        status="NOT_ELIGIBLE"
    )

    # Push to Google Sheets - try update first, fall back to insert
    result = sheets_api.update_user(
        telegram_user_id=telegram_user_id,
        telegram_name=user.full_name,
        username=user.username or "",
        has_vantage_account="NO"
    )

    # If update fails because user not found, insert instead
    if not result.get("success") and "User not found" in str(result.get("error", "")):
        logger.info("User %s not in API yet, inserting...", telegram_user_id)
        result = sheets_api.insert_user(
            telegram_user_id=telegram_user_id,
            telegram_name=user.full_name,
            username=user.username or "",
            has_vantage_account="NO"
        )

    if not result.get("success"):
        logger.warning("Sheets API operation failed for user %s: %s", telegram_user_id, result.get("error"))

    try:
        # Edit message with result
        await query.edit_message_text(NO_TEXT, parse_mode="HTML")

        # Auto-delete message after 5 minutes (300 seconds)
        context.job_queue.run_once(
            delete_message_job,
            300,
            data={
                "chat_id": query.message.chat_id,
                "message_id": query.message.message_id
            }
        )
    except Exception as e:
        logger.error("Failed to edit message for user %s: %s", telegram_user_id, e)


def get_eligibility_handlers():
    """Return all handlers for the eligibility system."""
    return [
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            on_group_message
        ),
        CallbackQueryHandler(on_callback_yes, pattern="^vantage_yes_"),
        CallbackQueryHandler(on_callback_no, pattern="^vantage_no_"),
    ]


async def periodic_sync(bot: Bot) -> None:
    """Periodic sync from Google Sheets API to local SQLite (runs every 24h)."""
    logger.info("Starting periodic sync from Google Sheets...")
    users = sheets_api.fetch_all()
    if not users:
        logger.info("Periodic sync: No users found in Sheets (or API error)")
        return

    synced = 0
    new_users = 0
    tz = TIMEZONE

    for user in users:
        telegram_user_id = str(user.get("Telegram User ID", "")).strip()
        if not telegram_user_id:
            continue

        telegram_name = str(user.get("Telegram Name", "")).strip()
        username = str(user.get("Username", "")).strip()
        has_vantage = str(user.get("Has Vantage Account", "")).strip().upper()
        status = str(user.get("Status", "")).strip().upper()
        created_at = str(user.get("Created At", "")).strip()

        if has_vantage not in ("YES", "NO", "NO_RESPONSE"):
            has_vantage = "PENDING"
        status_clean = status if status in ("ELIGIBLE", "NOT_ELIGIBLE") else "PENDING"

        # Determine last_question_date from API's Created At
        last_question_date = None
        if has_vantage in ("NO_RESPONSE", "YES", "NO"):
            if created_at and len(created_at) >= 10:
                last_question_date = created_at[:10]

        existing = get_user(telegram_user_id)
        if not existing:
            new_users += 1

        upsert_user(
            telegram_user_id=telegram_user_id,
            telegram_name=telegram_name,
            username=username,
            has_vantage_account=has_vantage,
            status=status_clean,
            created_at=created_at,
            last_question_date=last_question_date
        )
        synced += 1

    logger.info("Periodic sync complete: %d total synced, %d new users added", synced, new_users)