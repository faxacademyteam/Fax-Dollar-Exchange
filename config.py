import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    # Required
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    GROUP_CHAT_ID: str = os.getenv("GROUP_CHAT_ID", "")
    SHEETS_API_URL: str = os.getenv("SHEETS_API_URL", "")

    # Admin (for error notifications & commands)
    ADMIN_USER_ID: str = os.getenv("ADMIN_USER_ID", "1007815760")

    # Database
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "bot.db"))

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Dhaka")

    # Sync interval (hours) - how often to fetch from API
    SYNC_INTERVAL_HOURS: int = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

    # Optimization settings
    POLL_INTERVAL: float = float(os.getenv("POLL_INTERVAL", "1.0"))
    MAX_CONCURRENT_UPDATES: int = int(os.getenv("MAX_CONCURRENT_UPDATES", "10"))
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "15"))
    DB_TIMEOUT: int = int(os.getenv("DB_TIMEOUT", "5"))

    @classmethod
    def validate(cls) -> None:
        missing = []
        if not cls.BOT_TOKEN:
            missing.append("BOT_TOKEN")
        if not cls.GROUP_CHAT_ID:
            missing.append("GROUP_CHAT_ID")
        if not cls.SHEETS_API_URL:
            missing.append("SHEETS_API_URL")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    @classmethod
    def get_chat_id_int(cls) -> int:
        return int(cls.GROUP_CHAT_ID)


config = Config()