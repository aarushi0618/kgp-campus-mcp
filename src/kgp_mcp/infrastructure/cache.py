"""SQLite Caching Layer to ensure statelessness and reduce upstream load."""
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Use pathlib to reliably find the project root and data directory
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "kgp_mcp_cache.db"


def init_db():
    """Initialize the cache table (including source_mtime for automatic file-update invalidation)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at REAL,
                source_mtime REAL DEFAULT 0
            )
        """)
        # Ensure source_mtime column exists on older databases
        try:
            conn.execute("ALTER TABLE cache ADD COLUMN source_mtime REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        conn.commit()


def invalidate_cache(key: Optional[str] = None):
    """Invalidate a specific cache key, or clear the entire SQLite cache if key is None."""
    if not DB_PATH.exists():
        return
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if key:
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            else:
                conn.execute("DELETE FROM cache")
            conn.commit()
    except Exception as e:
        logger.warning(f"Failed to invalidate cache: {e}")


def get_cache(key: str, source_file: Optional[str] = None) -> Optional[Any]:
    """Retrieve a value from cache if it hasn't expired and the underlying JSON file hasn't been modified."""
    if not DB_PATH.exists():
        return None

    current_mtime = 0.0
    if source_file and Path(source_file).exists():
        try:
            current_mtime = os.path.getmtime(source_file)
        except OSError:
            current_mtime = 0.0

    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "SELECT value, expires_at, source_mtime FROM cache WHERE key = ?", (key,)
            )
            row = cursor.fetchone()

            if row:
                value, expires_at, cached_mtime = row[0], row[1], (row[2] or 0.0)
                # Invalidate if expired OR if the backing JSON file is newer than the cached entry
                if time.time() < expires_at and (not current_mtime or abs(current_mtime - cached_mtime) < 1e-3):
                    logger.info(f"[CACHE HIT] Returning cached data for key: {key}")
                    return json.loads(value)
                else:
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
    except Exception as e:
        logger.warning(f"Cache read error for {key}: {e}")

    logger.info(f"[CACHE MISS] No valid cache for key: {key}")
    return None


def set_cache(key: str, value: Any, ttl_seconds: int = 86400, source_file: Optional[str] = None):
    """Store a value in cache with a Time-To-Live (default 24 hours) and optional source_file mtime."""
    expires_at = time.time() + ttl_seconds
    serialized_value = json.dumps(value)
    current_mtime = 0.0
    if source_file and Path(source_file).exists():
        try:
            current_mtime = os.path.getmtime(source_file)
        except OSError:
            current_mtime = 0.0

    try:
        init_db()
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at, source_mtime) VALUES (?, ?, ?, ?)",
                (key, serialized_value, expires_at, current_mtime),
            )
            conn.commit()
        logger.info(f"[CACHE SET] Stored key: {key} for {ttl_seconds} seconds.")
    except Exception as e:
        logger.warning(f"Cache write error for {key}: {e}")
