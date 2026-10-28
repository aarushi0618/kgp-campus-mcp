"""Personalized Student ERP Timetable Sync Daemon (Shadow Sync Pipeline).

Target: https://erp.iitkgp.ac.in/Acad/student/view_stud_time_table.jsp
Authenticates using iitkgp-erp-login, parses the visual timetable grid,
stores the student schedule in campus_cache.db (user_classes table),
and dumps data/debug_student_timetable.html for inspection.
"""
import asyncio
import os
from pathlib import Path
import re
import sys
from bs4 import BeautifulSoup
import iitkgp_erp_login.erp as erp
import requests

from kgp_mcp.infrastructure.database import (
    insert_classes,
    get_classes,
    DB_PATH,
    ROOT_DIR,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = ROOT_DIR / "data"
DEBUG_HTML_PATH = DATA_DIR / "debug_student_timetable.html"

# Primary target URL for the student personal timetable in ERP
PRIMARY_TIMETABLE_URL = "https://erp.iitkgp.ac.in/Acad/student/view_stud_time_table.jsp"

DAY_MAP = {
    "MON": "Monday",
    "MONDAY": "Monday",
    "TUE": "Tuesday",
    "TUESDAY": "Tuesday",
    "WED": "Wednesday",
    "WEDNESDAY": "Wednesday",
    "THU": "Thursday",
    "THUR": "Thursday",
    "THURSDAY": "Thursday",
    "FRI": "Friday",
    "FRIDAY": "Friday",
    "SAT": "Saturday",
    "SATURDAY": "Saturday",
    "SUN": "Sunday",
    "SUNDAY": "Sunday",
}

# Standard IIT KGP 1-hour lecture slots fallback
DEFAULT_SLOTS = [
    ("08:00 AM", "08:55 AM"),
    ("09:00 AM", "09:55 AM"),
    ("10:00 AM", "10:55 AM"),
    ("11:00 AM", "11:55 AM"),
    ("12:00 PM", "12:55 PM"),
    ("02:00 PM", "02:55 PM"),
    ("03:00 PM", "03:55 PM"),
    ("04:00 PM", "04:55 PM"),
    ("05:00 PM", "05:55 PM"),
]


def _format_time_component(raw: str) -> str:
    """Format raw time strings like '8:0:AM' or '8:00 AM' into '08:00 AM'."""
    raw = raw.strip().replace(":AM", " AM").replace(":PM", " PM")
    m = re.search(r"(\d{1,2}):(\d{1,2})\s*([AP]M)?", raw, re.IGNORECASE)
    if not m:
        return raw.strip()
    hour = int(m.group(1))
    minute = int(m.group(2))
    period = (m.group(3) or "").upper()
    if not period:
        period = "AM" if hour < 12 else "PM"
        if hour > 12:
            hour -= 12
    return f"{hour:02d}:{minute:02d} {period}"


def parse_visual_grid(html: str) -> list[dict]:
    """Parse the student visual timetable grid HTML.

    Step 1: Extract header row to get the time slots by splitting on hyphen '-'
            (e.g., '8:0:AM-8:55:AM' -> ('08:00 AM', '08:55 AM')).
    Step 2: Map each cell to the exact time slot using its column position,
            handling HTML rowspans and colspans so multi-section rows align perfectly.
    Step 3: Extract course code, course name, and room from each non-empty cell.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    classes: list[dict] = []

    # Map course codes to course names from registration tables / legends if available
    course_names_map = {}
    for code_match in re.finditer(
        r"\b([A-Z]{2}\d{5})\b\s*[-:\t|]?\s*([A-Za-z0-9 &,/()\-]+)", soup.get_text()
    ):
        code = code_match.group(1).upper()
        name_cand = code_match.group(2).strip()
        if len(name_cand) > 3 and not re.match(r"^[A-Z]{2}\d{5}$", name_cand):
            cleaned_name = re.sub(
                r"\b(MON|TUE|WED|THU|THUR|FRI|SAT|NC\d+|NR\d+)\b.*$",
                "",
                name_cand,
                flags=re.I,
            ).strip(" -:|")
            if len(cleaned_name) > 3:
                course_names_map[code] = cleaned_name

    # Step 1: Find the table (with border="1" or containing day names)
    table = soup.find("table", border="1")
    if not table:
        for t in soup.find_all("table"):
            text_upper = t.get_text().upper()
            if any(d in text_upper for d in ["MON", "TUE", "WED", "THU", "FRI"]):
                table = t
                break

    if not table:
        tables = soup.find_all("table")
        if tables:
            table = tables[0]
        else:
            return []

    rows = table.find_all("tr")
    if not rows:
        return []

    # Extract time slots from the header row (ignoring first column: 'Day Name')
    header_cells = rows[0].find_all(["th", "td"])
    time_slots: list[tuple[str, str]] = []

    for cell in header_cells[1:]:
        text = cell.get_text(" ", strip=True)
        # Split by hyphen '-'
        parts = text.split("-")
        if len(parts) >= 2:
            start_time = _format_time_component(parts[0])
            end_time = _format_time_component(parts[1])
            time_slots.append((start_time, end_time))

    if not time_slots:
        time_slots = list(DEFAULT_SLOTS)

    # Step 2: Build coordinate grid for 2D cell mapping (handles rowspan/colspan)
    occupied = set()
    grid_cells: dict[tuple[int, int], tuple[any, int, int]] = {}

    for r_idx, r in enumerate(rows):
        c_idx = 0
        cells = r.find_all(["td", "th"])
        for cell in cells:
            while (r_idx, c_idx) in occupied:
                c_idx += 1

            try:
                rowspan = int(cell.get("rowspan", 1))
            except ValueError:
                rowspan = 1

            try:
                colspan = int(cell.get("colspan", 1))
            except ValueError:
                colspan = 1

            for ro in range(rowspan):
                for co in range(colspan):
                    occupied.add((r_idx + ro, c_idx + co))
                    if ro == 0 and co == 0:
                        grid_cells[(r_idx, c_idx)] = (cell, rowspan, colspan)

            c_idx += colspan

    # Step 3: Extract courses safely from the mapped grid
    # Group by physical day block
    current_day = None

    for (r_idx, c_idx), (cell, rowspan, colspan) in sorted(grid_cells.items()):
        # Skip header row
        if r_idx == 0:
            continue

        # Column 0 contains the Day Name (Mon, Tue, etc.)
        if c_idx == 0:
            first_text = cell.get_text(" ", strip=True).upper()
            first_clean = re.sub(r"[^A-Z]", "", first_text)
            for key, full_day in DAY_MAP.items():
                if first_clean == key or first_clean.startswith(key):
                    current_day = full_day
                    break
            continue

        # If current_day is not identified from col 0, trace upwards in col 0
        day_for_cell = current_day
        if not day_for_cell:
            for cur_r in range(r_idx, 0, -1):
                if (cur_r, 0) in grid_cells:
                    d_cell, _, _ = grid_cells[(cur_r, 0)]
                    d_txt = re.sub(r"[^A-Z]", "", d_cell.get_text(" ", strip=True).upper())
                    for key, full_day in DAY_MAP.items():
                        if d_txt == key or d_txt.startswith(key):
                            day_for_cell = full_day
                            break
                    if day_for_cell:
                        break

        if not day_for_cell:
            continue

        # Get cell content
        cell_text = cell.get_text(" ", strip=True)
        if not cell_text or cell_text == "&nbsp;" or cell_text.isspace():
            continue

        # Extract course code (e.g., CH21205)
        code_match = re.search(r"\b([A-Z]{2}\d{5})\b", cell_text)
        if not code_match:
            continue

        course_code = code_match.group(1).upper()

        # Extract room (e.g., NC314, NR123, NC323, NR222)
        room = "Not specified"
        room_match = re.search(
            r"\b([A-Z]{1,2}\d{3}[A-Z]?)\b", cell_text.replace(course_code, "")
        )
        if room_match:
            room = room_match.group(1)
        elif "/" in cell_text:
            parts = cell_text.split("/")
            if len(parts) > 1 and parts[1].strip():
                room = parts[1].strip()

        # Extract or resolve course name
        name_cand = (
            cell_text.replace(course_code, "").replace(room, "").strip(" -/()|:,")
        )
        if len(name_cand) > 3 and not re.match(r"^[A-Z]{2}\d{5}$", name_cand):
            course_name = name_cand
        else:
            course_name = course_names_map.get(
                course_code, f"{course_code} Lecture/Lab"
            )

        # Correct column mapping: c_idx - 1 gives slot index into time_slots
        slot_idx = c_idx - 1
        if 0 <= slot_idx < len(time_slots):
            start_time, end_time = time_slots[slot_idx]
            # Handle colspan across multiple hours if any
            if colspan > 1:
                end_slot_idx = min(slot_idx + colspan - 1, len(time_slots) - 1)
                end_time = time_slots[end_slot_idx][1]
        else:
            start_time, end_time = ("08:00 AM", "08:55 AM")

        # Avoid exact duplicates if table repeated sections
        entry = {
            "course_code": course_code,
            "course_name": course_name,
            "day_of_week": day_for_cell,
            "start_time": start_time,
            "end_time": end_time,
            "location": room,
        }
        if entry not in classes:
            classes.append(entry)

    # Sort classes chronologically by day and start time
    day_order = {
        "Monday": 1,
        "Tuesday": 2,
        "Wednesday": 3,
        "Thursday": 4,
        "Friday": 5,
        "Saturday": 6,
        "Sunday": 7,
    }
    classes.sort(
        key=lambda x: (day_order.get(x["day_of_week"], 8), x["start_time"], x["course_code"])
    )
    return classes


def fetch_student_timetable_html(session: requests.Session) -> str:
    """Fetch timetable HTML from the student timetable URL."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    print(f"  -> Fetching {PRIMARY_TIMETABLE_URL}...", end=" ", flush=True)
    try:
        resp = session.get(PRIMARY_TIMETABLE_URL, headers=headers, timeout=25)
        print(f"Status: {resp.status_code} ({len(resp.text)} bytes)")
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"Failed: {e}")

    # Fallback URLs
    fallback_urls = [
        "https://erp.iitkgp.ac.in/Acad/student/stu_time_table.jsp",
        "https://erp.iitkgp.ac.in/Acad/student_time_table.jsp",
    ]
    for url in fallback_urls:
        print(f"  -> Probing fallback {url}...", end=" ", flush=True)
        try:
            r = session.get(url, headers=headers, timeout=20)
            if r.status_code == 200 and len(r.text) > 500:
                print(f"Found ({len(r.text)} bytes)")
                return r.text
            print(f"Status: {r.status_code}")
        except Exception as e:
            print(f"Failed: {e}")

    return ""


async def run_sync():
    print("=========================================================")
    print("  IIT KGP Personalized Timetable Sync (view_stud_time_table)")
    print("=========================================================")

    # Step 1: Authenticate using iitkgp-erp-login
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        sessionToken, ssoToken = erp.login(headers, session)
        print("✅ Login successful.\n")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        sys.exit(1)

    user_id = (
        getattr(erp, "ROLL_NUMBER", None)
        or os.environ.get("ROLL_NUMBER")
        or ""
    ).strip().upper()
    if not user_id:
        user_id = input("Confirm your Roll Number (e.g. 25CH10025): ").strip().upper()

    print(f"Synchronizing schedule for student: {user_id}")

    # Step 2: Fetch the Personalized Timetable
    html_content = fetch_student_timetable_html(session)

    # Step 5: Debug Fallback - save scraped HTML to data/debug_student_timetable.html
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DEBUG_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content or "<!-- No timetable HTML content fetched -->")
    print(f"ℹ️ Dumped debug HTML to {DEBUG_HTML_PATH}")

    if not html_content:
        print("❌ Could not load timetable HTML. Check debug_student_timetable.html.")
        return

    # Step 3: Parse the Visual Grid with exact time slot alignment
    classes = parse_visual_grid(html_content)
    print(f"Parsed {len(classes)} classes from student timetable.")

    # Step 4: Save to SQLite (campus_cache.db -> user_classes)
    if classes:
        await insert_classes(user_id, classes)
        print(
            f"✅ Successfully inserted {len(classes)} classes for {user_id} into {DB_PATH}"
        )
        saved = await get_classes(user_id)
        print(f"Verified {len(saved)} total classes in SQLite for {user_id}.")
    else:
        print(
            "⚠️ No classes found in the parsed grid. "
            f"Please inspect {DEBUG_HTML_PATH} to inspect the actual table structure."
        )


def main():
    asyncio.run(run_sync())


if __name__ == "__main__":
    main()
