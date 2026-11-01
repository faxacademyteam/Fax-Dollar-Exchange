import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


def get_db_path() -> Path:
    path = Path(config.DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# Thread-local connection for concurrent access
_local = threading.local()


def _get_conn():
    """Get thread-local connection with WAL mode for better concurrency."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(get_db_path(), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        # Enable WAL mode for better read/write concurrency
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        _local.conn.execute("PRAGMA temp_store=MEMORY")
    return _local.conn


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = _get_conn()
    try:
        yield conn
    finally:
        pass  # Keep connection alive for reuse


def init_db() -> None:
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id TEXT UNIQUE NOT NULL,
            telegram_name TEXT,
            username TEXT,
            has_vantage_account TEXT,
            status TEXT,
            last_question_date TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_id ON users(telegram_user_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_has_vantage ON users(has_vantage_account)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_status ON users(status)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_last_question ON users(last_question_date)
    """)
    conn.commit()
    logger.info("Database initialized at %s (WAL mode enabled)", get_db_path())


def get_user(telegram_user_id: str) -> Optional[dict]:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,)
    ).fetchone()
    return dict(row) if row else None


def upsert_user(
    telegram_user_id: str,
    telegram_name: str = "",
    username: str = "",
    has_vantage_account: Optional[str] = None,
    status: str = "PENDING",
    last_question_date: Optional[str] = None,
    created_at: Optional[str] = None
) -> dict:
    conn = _get_conn()
    existing = conn.execute(
        "SELECT id FROM users WHERE telegram_user_id = ?",
        (telegram_user_id,)
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE users
            SET telegram_name = ?, username = ?,
                has_vantage_account = ?, status = ?,
                last_question_date = COALESCE(?, last_question_date),
                updated_at = datetime('now')
            WHERE telegram_user_id = ?
        """, (telegram_name, username, has_vantage_account, status, last_question_date, telegram_user_id))
    else:
        conn.execute("""
            INSERT INTO users (telegram_user_id, telegram_name, username, has_vantage_account, status, last_question_date, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (telegram_user_id, telegram_name, username, has_vantage_account, status, last_question_date, created_at))

    conn.commit()
    return get_user(telegram_user_id) or {}


def get_all_users() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


def get_pending_users() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM users WHERE has_vantage_account = 'PENDING' ORDER BY created_at DESC"
    ).fetchall()
    return [dict(row) for row in rows]


def count_users() -> int:
    conn = _get_conn()
    return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def count_eligible() -> int:
    conn = _get_conn()
    return conn.execute("SELECT COUNT(*) FROM users WHERE status = 'ELIGIBLE'").fetchone()[0]


def count_not_eligible() -> int:
    conn = _get_conn()
    return conn.execute("SELECT COUNT(*) FROM users WHERE status = 'NOT_ELIGIBLE'").fetchone()[0]


def close_db() -> None:
    """Close thread-local connection."""
    if hasattr(_local, "conn") and _local.conn:
        _local.conn.close()
        _local.conn = None