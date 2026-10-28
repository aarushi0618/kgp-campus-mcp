"""SQLite database layer for personalized campus data (campus_cache.db)."""
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite

# database.py is located at src/kgp_mcp/infrastructure/database.py -> 4 parents to project root
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "campus_cache.db"


async def init_db() -> None:
    """Initialize campus_cache.db with user_classes table."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                course_code TEXT NOT NULL,
                course_name TEXT,
                day_of_week TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                location TEXT
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_classes_user ON user_classes (user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_classes_day ON user_classes (user_id, day_of_week)")
        await db.commit()


async def insert_classes(user_id: str, classes_list: List[Dict[str, Any]]) -> None:
    """Clear existing classes for user_id and insert freshly synced classes."""
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM user_classes WHERE user_id = ?", (user_id,))
        for c in classes_list:
            await db.execute("""
                INSERT INTO user_classes (
                    user_id, course_code, course_name, day_of_week, start_time, end_time, location
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                str(c.get("course_code") or "").strip().upper(),
                str(c.get("course_name") or "").strip(),
                str(c.get("day_of_week") or "").strip().capitalize(),
                str(c.get("start_time") or "").strip(),
                str(c.get("end_time") or "").strip(),
                str(c.get("location") or "Not specified").strip(),
            ))
        await db.commit()


async def get_classes(user_id: str, target_day: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve scheduled classes for user_id, optionally filtered by day_of_week."""
    if not DB_PATH.exists():
        return []

    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if target_day:
            day_clean = target_day.strip().capitalize()
            cursor = await db.execute("""
                SELECT id, user_id, course_code, course_name, day_of_week, start_time, end_time, location
                FROM user_classes
                WHERE user_id = ? AND day_of_week = ?
                ORDER BY start_time ASC
            """, (user_id, day_clean))
        else:
            cursor = await db.execute("""
                SELECT id, user_id, course_code, course_name, day_of_week, start_time, end_time, location
                FROM user_classes
                WHERE user_id = ?
                ORDER BY 
                    CASE day_of_week
                        WHEN 'Monday' THEN 1
                        WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3
                        WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5
                        WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                        ELSE 8
                    END,
                    start_time ASC
            """, (user_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
