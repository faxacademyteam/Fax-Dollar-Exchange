"""
schedule_db.py — Dedicated SQLite database for lock/unlock event tracking.

Separate from users.db so schedule data is easy to maintain,
audit, and purge without touching user data.
"""
import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


def get_schedule_db_path() -> Path:
    path = Path(config.SCHEDULE_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# Thread-local connection
_local = threading.local()


def _get_conn():
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(
            get_schedule_db_path(),
            check_same_thread=False
        )
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA cache_size=-32000")  # 32MB
    return _local.conn


@contextmanager
def get_connection():
    conn = _get_conn()
    try:
        yield conn
    finally:
        pass


def init_schedule_db() -> None:
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedule_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            actual_time TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            message_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON schedule_log(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_date_event ON schedule_log(date, event_type)")
    conn.commit()
    logger.info("Schedule database initialized at %s", get_schedule_db_path())


def get_today_record(date_str: str, event_type: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM schedule_log WHERE date = ? AND event_type = ?",
        (date_str, event_type)
    ).fetchone()
    return dict(row) if row else None


def insert_schedule_record(
    date_str: str,
    event_type: str,
    scheduled_time: str,
    actual_time: Optional[str] = None,
    status: str = "pending",
    retry_count: int = 0,
    message_id: Optional[str] = None
) -> dict:
    conn = _get_conn()
    conn.execute(
        """INSERT INTO schedule_log
           (date, event_type, scheduled_time, actual_time, status, retry_count, message_id)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (date_str, event_type, scheduled_time, actual_time, status, retry_count, message_id)
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM schedule_log WHERE date = ? AND event_type = ? ORDER BY id DESC LIMIT 1",
        (date_str, event_type)
    ).fetchone()
    return dict(row) if row else {}


def update_schedule_record(
    date_str: str,
    event_type: str,
    actual_time: Optional[str] = None,
    status: Optional[str] = None,
    retry_count: Optional[int] = None,
    message_id: Optional[str] = None
) -> dict:
    conn = _get_conn()
    sets = []
    params = []
    if actual_time is not None:
        sets.append("actual_time = ?")
        params.append(actual_time)
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if retry_count is not None:
        sets.append("retry_count = ?")
        params.append(retry_count)
    if message_id is not None:
        sets.append("message_id = ?")
        params.append(message_id)
    if not sets:
        return get_today_record(date_str, event_type) or {}
    params.extend([date_str, event_type])
    conn.execute(
        f"UPDATE schedule_log SET {', '.join(sets)} WHERE date = ? AND event_type = ?",
        params
    )
    conn.commit()
    return get_today_record(date_str, event_type) or {}


def get_today_schedule(date_str: str) -> dict:
    unlock = get_today_record(date_str, "unlock")
    lock = get_today_record(date_str, "lock")
    return {"unlock": unlock, "lock": lock}


def purge_old_records(cutoff_date: str) -> int:
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM schedule_log WHERE date < ?",
        (cutoff_date,)
    )
    conn.commit()
    return cur.rowcount


def close_schedule_db() -> None:
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None