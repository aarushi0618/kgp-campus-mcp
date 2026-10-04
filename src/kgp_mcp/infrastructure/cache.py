"""SQLite Caching Layer to ensure statelessness and reduce upstream load."""
import sqlite3
import json
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

DB_PATH = "kgp_mcp_cache.db"

def init_db():
    """Initialize the cache table."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT,
                expires_at REAL
            )
        """)
        conn.commit()

def get_cache(key: str) -> Optional[Any]:
    """Retrieve a value from cache if it hasn't expired."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
        )
        row = cursor.fetchone()
        
        if row:
            value, expires_at = row
            if time.time() < expires_at:
                logger.info(f"[CACHE HIT] Returning cached data for key: {key}")
                return json.loads(value)
            else:
                # Expired, delete it
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                conn.commit()
    
    logger.info(f"[CACHE MISS] No valid cache for key: {key}")
    return None

def set_cache(key: str, value: Any, ttl_seconds: int = 86400):
    """Store a value in cache with a Time-To-Live (default 24 hours)."""
    expires_at = time.time() + ttl_seconds
    serialized_value = json.dumps(value)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, serialized_value, expires_at)
        )
        conn.commit()
    logger.info(f"[CACHE SET] Stored key: {key} for {ttl_seconds} seconds.")