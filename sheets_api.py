import logging
import time
import httpx
from config import config

logger = logging.getLogger(__name__)


class SheetsAPI:
    def __init__(self, base_url: str = None):
        self.base_url = (base_url or config.SHEETS_API_URL).rstrip("/")
        # Optimized connection pool for low-resource Railway hosting
        self.client = httpx.Client(
            timeout=httpx.Timeout(15.0, connect=8.0),
            limits=httpx.Limits(
                max_connections=3,
                max_keepalive_connections=2
            ),
            follow_redirects=True,
            http2=False  # Disable HTTP/2 for lower memory usage
        )

    def _normalize_user(self, user: dict) -> dict:
        """Normalize user dict to always have correct keys."""
        if 'Telegram User ID' in user:
            return user

        # Old buggy format - map keys
        normalized = {}
        for key, value in user.items():
            if key in VALID_KEYS:
                normalized[key] = value
            else:
                mapped_key = KEY_MAPPING.get(key, key)
                normalized[mapped_key] = value

        for required_key in VALID_KEYS:
            if required_key not in normalized:
                normalized[required_key] = ''

        return normalized

    def fetch_all(self) -> list[dict]:
        """GET ?action=read - returns list of user dicts."""
        url = f"{self.base_url}?action=read"
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                return [self._normalize_user(u) for u in data]
            logger.warning("Unexpected response format from Sheets API: %s", type(data))
            return []
        except httpx.HTTPError as e:
            logger.error("Sheets API fetch failed: %s", e)
            return []
        except ValueError as e:
            logger.error("Sheets API invalid JSON: %s", e)
            return []

    def insert_user(
        self,
        telegram_user_id: str,
        telegram_name: str,
        username: str,
        has_vantage_account: str
    ) -> dict:
        """GET ?action=insert - returns success dict."""
        params = {
            "action": "insert",
            "TelegramUserId": telegram_user_id,
            "TelegramName": telegram_name,
            "Username": username,
            "HasVantageAccount": has_vantage_account.upper()
        }
        url = f"{self.base_url}"
        try:
            resp = self.client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Sheets API insert failed: %s", e)
            return {"success": False, "error": str(e)}
        except ValueError as e:
            logger.error("Sheets API insert invalid JSON: %s", e)
            return {"success": False, "error": str(e)}

    def update_user(
        self,
        telegram_user_id: str,
        telegram_name: str = None,
        username: str = None,
        has_vantage_account: str = None
    ) -> dict:
        """GET ?action=update - returns success dict."""
        params = {
            "action": "update",
            "TelegramUserId": telegram_user_id,
        }
        if telegram_name is not None:
            params["TelegramName"] = telegram_name
        if username is not None:
            params["Username"] = username
        if has_vantage_account is not None:
            params["HasVantageAccount"] = has_vantage_account.upper()

        url = f"{self.base_url}"
        try:
            resp = self.client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Sheets API update failed: %s", e)
            return {"success": False, "error": str(e)}
        except ValueError as e:
            logger.error("Sheets API update invalid JSON: %s", e)
            return {"success": False, "error": str(e)}

    def close(self):
        self.client.close()


# Map old buggy keys to new correct keys
KEY_MAPPING = {
    '1007815760': 'Telegram User ID',
    'Tawhid': 'Telegram Name',
    'TraderTawhid': 'Username',
    'NO': 'Has Vantage Account',
    'NOT_ELIGIBLE': 'Status',
    '2026-10-31T11:10:20.102Z': 'Created At',
}

VALID_KEYS = {
    'Telegram User ID',
    'Telegram Name',
    'Username',
    'Has Vantage Account',
    'Status',
    'Created At',
}


sheets_api = SheetsAPI()