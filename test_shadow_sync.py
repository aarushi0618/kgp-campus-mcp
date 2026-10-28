"""Test suite for the Shadow Sync Architecture and Personalized Class Schedule Pipeline."""
import asyncio
from datetime import datetime, timedelta
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Simulate Claude Desktop running from C:\
os.chdir("C:\\")
print(f"Current Working Directory: {os.getcwd()}")

from database import init_db, insert_classes, get_classes, DB_PATH  # noqa: E402
from kgp_mcp.server import get_user_schedule, smart_activity_planner  # noqa: E402


async def main():
    print(f"\n--- 1. Initializing & Testing Database (campus_cache.db at {DB_PATH}) ---")
    await init_db()

    test_user = "25CH10025"
    now = datetime.now()
    today_name = now.strftime("%A")

    # Generate a class starting 30 minutes from now today to test Hard Stop Elicitation
    class_start = (now + timedelta(minutes=30)).strftime("%I:%M %p")
    class_end = (now + timedelta(minutes=85)).strftime("%I:%M %p")

    mock_classes = [
        {
            "course_code": "CH21205",
            "course_name": "Mechanical Operations",
            "day_of_week": today_name,
            "start_time": class_start,
            "end_time": class_end,
            "location": "NC314",
        },
        {
            "course_code": "CH21202",
            "course_name": "Mass Transfer I",
            "day_of_week": "Monday",
            "start_time": "10:00 AM",
            "end_time": "10:55 AM",
            "location": "NR123",
        },
        {
            "course_code": "CH21203",
            "course_name": "Chemical Process Calculations",
            "day_of_week": "Wednesday",
            "start_time": "11:00 AM",
            "end_time": "11:55 AM",
            "location": "NC141",
        },
    ]

    print(f"Inserting {len(mock_classes)} mock classes for {test_user}...")
    await insert_classes(test_user, mock_classes)

    saved = await get_classes(test_user)
    print(f"Verified {len(saved)} classes in SQLite for {test_user}.")

    print("\n--- 2. Testing get_user_schedule MCP Tool (Entire Week) ---")
    schedule_md = await get_user_schedule(user_id=test_user)
    print(schedule_md)

    print("\n--- 3. Testing get_user_schedule MCP Tool (Filtered Day: Monday) ---")
    monday_md = await get_user_schedule(user_id=test_user, target_day="Monday")
    print(monday_md)

    print("\n--- 4. Testing get_user_schedule MCP Tool (Empty User Fallback) ---")
    empty_md = await get_user_schedule(user_id="NONEXISTENT_USER")
    print(empty_md)

    print("\n--- 5. Testing smart_activity_planner (Hard Stop Dynamic Elicitation) ---")
    directive = await smart_activity_planner(user_id=test_user, current_location="Hall 12", focus_level=None)
    print("Output when focus_level is None:")
    print(directive)
    assert "SYSTEM DIRECTIVE: You must STOP" in directive, "Hard Stop directive failed!"

    print("\n--- 6. Testing smart_activity_planner (With Elicited Focus Level) ---")
    plan = await smart_activity_planner(user_id=test_user, current_location="Hall 12", focus_level="high")
    print("Output when focus_level is 'high':")
    print(plan)

    print("\n✅ test_shadow_sync.py finished successfully with 0 errors!")


if __name__ == "__main__":
    asyncio.run(main())
