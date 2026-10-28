"""Planner & Timeline Fusion Service for KGP Campus Intelligence MCP.

Fuses:
1. Local SQLite ERP Timetable (`campus_cache.db` -> `user_classes`)
2. Cloud Supabase WhatsApp Events (`whatsapp_events`)
3. Cloud Supabase Academic Deadlines (`academic_deadlines`)
"""
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from kgp_mcp.infrastructure.database import get_classes, ROOT_DIR

logger = logging.getLogger(__name__)

# Load .env from project root and cloud_webhook if present
for env_candidate in (ROOT_DIR / ".env", ROOT_DIR / "cloud_webhook" / ".env"):
    if env_candidate.exists():
        try:
            with open(env_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

SYSTEM_DIRECTIVE_TEXT = (
    "SYSTEM DIRECTIVE: Analyze the gap between classes. If a deadline urgency is > 3.5, "
    "explicitly recommend skipping social events to study in the library. If urgency is low, "
    "recommend attending the campus events. Calculate exact free time blocks."
)


def _resolve_date_and_weekday(target_date: str) -> Tuple[str, str]:
    """Resolve a target_date string ('2026-10-28', 'today', 'tomorrow', or 'Monday')
    into (iso_date_str 'YYYY-MM-DD', day_of_week 'Monday').
    """
    raw = (target_date or "").strip()
    now = datetime.now()

    if not raw or raw.lower() == "today":
        return now.strftime("%Y-%m-%d"), now.strftime("%A")

    if raw.lower() == "tomorrow":
        tmrw = now + timedelta(days=1)
        return tmrw.strftime("%Y-%m-%d"), tmrw.strftime("%A")

    # Try YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%A")
        except ValueError:
            continue

    # Check if user passed a weekday name like 'Monday' or 'Mon'
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for idx, day_name in enumerate(weekdays):
        if raw.lower() == day_name.lower() or raw.lower() == day_name[:3].lower():
            days_ahead = (idx - now.weekday()) % 7
            target_dt = now + timedelta(days=days_ahead)
            return target_dt.strftime("%Y-%m-%d"), day_name

    # Fallback to today's date if unparseable
    return now.strftime("%Y-%m-%d"), now.strftime("%A")


def _parse_time_to_minutes(time_str: str) -> Optional[int]:
    """Convert '08:00 AM' or '14:00' to minutes since midnight."""
    if not time_str:
        return None
    s = time_str.strip().upper()
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)?", s)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    period = m.group(3)
    if period == "PM" and hour < 12:
        hour += 12
    elif period == "AM" and hour == 12:
        hour = 0
    return hour * 60 + minute


def _minutes_to_time_str(minutes: int) -> str:
    """Format minutes since midnight into 'HH:MM AM/PM'."""
    hour = minutes // 60
    minute = minutes % 60
    period = "AM" if hour < 12 else "PM"
    disp_hour = hour
    if disp_hour == 0:
        disp_hour = 12
    elif disp_hour > 12:
        disp_hour -= 12
    return f"{disp_hour:02d}:{minute:02d} {period}"


def _calculate_free_time_blocks(classes: List[Dict[str, Any]]) -> List[str]:
    """Calculate free time gaps between classes within the standard 08:00 AM - 05:55 PM campus day."""
    day_start = 8 * 60       # 08:00 AM (480)
    day_end = 17 * 60 + 55   # 05:55 PM (1075)

    intervals: List[Tuple[int, int]] = []
    for c in classes:
        s_min = _parse_time_to_minutes(str(c.get("start_time") or ""))
        e_min = _parse_time_to_minutes(str(c.get("end_time") or ""))
        if s_min is not None and e_min is not None and e_min > s_min:
            intervals.append((s_min, e_min))

    if not intervals:
        return ["08:00 AM - 05:55 PM (595 mins — Entire Academic Day Free)"]

    intervals.sort(key=lambda x: x[0])

    # Merge contiguous/overlapping class intervals (e.g., 08:00-08:55 and 09:00-09:55 with 5-min passing gap)
    merged: List[Tuple[int, int]] = [intervals[0]]
    for cur_s, cur_e in intervals[1:]:
        prev_s, prev_e = merged[-1]
        if cur_s <= prev_e + 5:
            merged[-1] = (prev_s, max(prev_e, cur_e))
        else:
            merged.append((cur_s, cur_e))

    free_blocks: List[str] = []
    cursor = day_start
    for s_min, e_min in merged:
        if s_min > cursor + 10:
            duration = s_min - cursor
            free_blocks.append(
                f"{_minutes_to_time_str(cursor)} - {_minutes_to_time_str(s_min)} ({duration} mins)"
            )
        cursor = max(cursor, e_min)

    if day_end > cursor + 10:
        duration = day_end - cursor
        free_blocks.append(
            f"{_minutes_to_time_str(cursor)} - {_minutes_to_time_str(day_end)} ({duration} mins)"
        )

    return free_blocks


async def _fetch_cloud_events_and_deadlines(
    user_id: str,
    iso_date: str,
    end_date_7d: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Query Supabase / Cloud PostgreSQL for WhatsAppEvent on iso_date and
    AcademicDeadline within [iso_date, end_date_7d].

    Supports:
    1. Supabase Python SDK (`supabase-py`) via SUPABASE_URL + SUPABASE_KEY
    2. Direct PostgreSQL connection via `asyncpg` using DATABASE_URL / SUPABASE_DB_URL

    Raises RuntimeError if neither is configured or if the cloud query fails.
    """
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = (
        os.getenv("SUPABASE_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )

    # Strategy 1: Use supabase-py client if SUPABASE_URL and SUPABASE_KEY are provided
    if supabase_url and supabase_key:
        from supabase import create_client

        client = create_client(supabase_url, supabase_key)
        events_resp = (
            client.table("whatsapp_events")
            .select("*")
            .eq("event_date", iso_date)
            .execute()
        )
        deadlines_resp = (
            client.table("academic_deadlines")
            .select("*")
            .eq("user_id", user_id)
            .gte("due_date", iso_date)
            .lte("due_date", end_date_7d)
            .order("urgency_weight", desc=True)
            .execute()
        )
        return list(events_resp.data or []), list(deadlines_resp.data or [])

    # Strategy 2: Use asyncpg directly with DATABASE_URL / SUPABASE_DB_URL
    db_url = (
        os.getenv("SUPABASE_DB_URL", "").strip()
        or os.getenv("DATABASE_URL", "").strip()
    )
    if db_url and ("postgres://" in db_url or "postgresql" in db_url):
        import asyncpg

        dsn = (
            db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
            .replace("postgres://", "postgresql://", 1)
        )
        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            event_rows = await conn.fetch(
                """
                SELECT id, group_name, event_title, event_date, event_time, venue, description
                FROM whatsapp_events
                WHERE event_date = $1
                ORDER BY event_time ASC NULLS LAST
                """,
                iso_date,
            )
            deadline_rows = await conn.fetch(
                """
                SELECT id, user_id, course_code, title, due_date, due_time, urgency_weight
                FROM academic_deadlines
                WHERE user_id = $1 AND due_date >= $2 AND due_date <= $3
                ORDER BY urgency_weight DESC, due_date ASC
                """,
                user_id,
                iso_date,
                end_date_7d,
            )
            return [dict(r) for r in event_rows], [dict(r) for r in deadline_rows]
        finally:
            await conn.close()

    raise RuntimeError("No Supabase/PostgreSQL credentials configured (SUPABASE_URL/SUPABASE_KEY or DATABASE_URL).")


async def get_fused_daily_timeline(user_id: str, target_date: str) -> str:
    """Build a fused daily timeline combining local SQLite classes, cloud WhatsApp events,
    and upcoming academic deadlines (next 7 days).
    """
    user_clean = str(user_id or "").strip().upper()
    if not user_clean:
        return "Please provide a valid student Roll Number (e.g., '25CH10025')."

    iso_date, day_of_week = _resolve_date_and_weekday(target_date)
    dt_obj = datetime.strptime(iso_date, "%Y-%m-%d")
    end_date_7d = (dt_obj + timedelta(days=7)).strftime("%Y-%m-%d")

    # 1. Query Local SQLite campus_cache.db for classes on day_of_week
    local_classes = await get_classes(user_clean, target_day=day_of_week)
    free_blocks = _calculate_free_time_blocks(local_classes)

    # 2. Query Cloud Supabase (WhatsAppEvent on target_date + AcademicDeadline in next 7 days)
    cloud_available = True
    cloud_events: List[Dict[str, Any]] = []
    cloud_deadlines: List[Dict[str, Any]] = []

    try:
        cloud_events, cloud_deadlines = await _fetch_cloud_events_and_deadlines(
            user_id=user_clean,
            iso_date=iso_date,
            end_date_7d=end_date_7d,
        )
    except Exception as e:
        logger.warning(f"Supabase cloud query failed, falling back to local classes only: {e}")
        cloud_available = False

    # 3. Format into clean Markdown
    lines: List[str] = [
        f"# 🗓️ Fused Daily Timeline for `{user_clean}`",
        f"**Target Date**: `{iso_date}` (**{day_of_week}**)",
        "",
    ]

    if not cloud_available:
        lines.append("> ⚠️ **Cloud data unavailable, showing local classes only.**")
        lines.append("")

    # Section A: Local Classes
    lines.append(f"## 📚 Local Classes ({day_of_week})")
    if local_classes:
        for c in local_classes:
            code = c.get("course_code", "Unknown")
            name = c.get("course_name") or code
            start = c.get("start_time", "")
            end = c.get("end_time", "")
            room = c.get("location", "Not specified")
            lines.append(f"- **{start} - {end}** | `{code}` {name} | 📍 Room: **{room}**")
    else:
        lines.append(f"_No scheduled classes found for {user_clean} on {day_of_week}._")
    lines.append("")

    # Section B: Calculated Free Time Blocks
    lines.append("## ⏳ Calculated Free Time Blocks (08:00 AM - 05:55 PM)")
    for block in free_blocks:
        lines.append(f"- 🟢 **{block}**")
    lines.append("")

    # Section C: Cloud WhatsApp Events & Academic Deadlines (if cloud succeeded)
    if cloud_available:
        lines.append(f"## 🎉 Campus Events on `{iso_date}` (WhatsApp Cloud Feed)")
        if cloud_events:
            for ev in cloud_events:
                title = ev.get("event_title") or "Untitled Event"
                ev_time = ev.get("event_time") or "TBA"
                venue = ev.get("venue") or "TBA"
                grp = ev.get("group_name") or "Campus Group"
                desc = ev.get("description") or ""
                lines.append(
                    f"- **{ev_time}** | **{title}** (📍 {venue}) _[{grp}]_ — {desc}"
                )
        else:
            lines.append(f"_No campus events scheduled on {iso_date}._")
        lines.append("")

        lines.append(f"## 🚨 Upcoming Academic Deadlines (`{iso_date}` to `{end_date_7d}`)")
        if cloud_deadlines:
            for dl in cloud_deadlines:
                title = dl.get("title") or "Academic Task"
                code = dl.get("course_code") or "General"
                d_date = dl.get("due_date") or iso_date
                d_time = dl.get("due_time") or "23:59"
                urgency = float(dl.get("urgency_weight") or 1.0)
                badge = "🔴 HIGH URGENCY" if urgency > 3.5 else "🟡 NORMAL URGENCY"
                lines.append(
                    f"- **{d_date} {d_time}** | `[Urgency: {urgency:.1f} - {badge}]` "
                    f"`{code}` — **{title}**"
                )
        else:
            lines.append("_No academic deadlines due in the next 7 days._")
        lines.append("")

    # 4. Append the required SYSTEM DIRECTIVE
    lines.append(SYSTEM_DIRECTIVE_TEXT)
    return "\n".join(lines)
