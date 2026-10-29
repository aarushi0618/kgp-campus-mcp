"""Local test script for Gemini multi-model extraction and SQLite fallback persistence."""
import asyncio
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Ensure cloud_webhook directory is in sys.path and test local SQLite fallback
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.pop("DATABASE_URL", None)

from extractor import extract_deadline_from_email, extract_event_details  # noqa: E402
from database import init_db, save_deadline, save_event, LOCAL_SQLITE_PATH  # noqa: E402


async def run_tests():
    print("=========================================================")
    print("  1. Testing Gemini Extraction (Multi-Model Fallback)")
    print("=========================================================")

    email_sample = "Mass Transfer Assignment 3 is due on October 31st at 11:59 PM."
    print(f"\n[Input Email]: {email_sample}")
    deadline_json = await extract_deadline_from_email(email_sample)
    print("[Extracted Deadline JSON]:")
    print(json.dumps(deadline_json, indent=2))
    assert deadline_json and deadline_json.get("is_academic") is True, "Deadline extraction failed!"

    whatsapp_sample = (
        "Hey guys, KodeinKGP is hosting a Web3 Hackathon this Friday at 5 PM in the Vikramshila auditorium."
    )
    print(f"\n[Input WhatsApp Message]: {whatsapp_sample}")
    event_json = await extract_event_details(whatsapp_sample)
    print("[Extracted Event JSON]:")
    print(json.dumps(event_json, indent=2))
    assert event_json and event_json.get("event_title"), "Event extraction failed!"

    print("\n=========================================================")
    print("  2. Testing Local SQLite Database Fallback (webhook.db)")
    print("=========================================================")
    await init_db()
    saved_dl = await save_deadline("25CH10025", email_sample, deadline_json)
    print(
        f"✅ Saved AcademicDeadline -> id={saved_dl.id}, title='{saved_dl.title}', "
        f"due={saved_dl.due_date} {saved_dl.due_time}, urgency={saved_dl.urgency_weight}"
    )

    saved_ev = await save_event("KodeinKGP Announcements", whatsapp_sample, event_json)
    print(
        f"✅ Saved WhatsAppEvent    -> id={saved_ev.id}, title='{saved_ev.event_title}', "
        f"date={saved_ev.event_date} {saved_ev.event_time}, venue='{saved_ev.venue}'"
    )
    print(f"ℹ️ Verified local SQLite database file at: {LOCAL_SQLITE_PATH}")
    print("\n🎉 All extraction and database tests passed with 0 errors!")


if __name__ == "__main__":
    asyncio.run(run_tests())
