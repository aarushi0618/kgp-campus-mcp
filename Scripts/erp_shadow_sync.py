"""Personalized Student ERP Timetable Sync Daemon (Shadow Sync Pipeline).

Target: https://erp.iitkgp.ac.in/Acad/student/view_stud_time_table.jsp
Authenticates using iitkgp-erp-login, parses the visual timetable grid
respecting the Odd/Even roll number parity split, stores the student
schedule in campus_cache.db (user_classes table), and dumps
data/debug_student_timetable.html for inspection.
"""
import asyncio
import json
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
TIMETABLE_JSON_PATH = DATA_DIR / "erp_timetable_data.json"

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


def get_user_parity(user_id: str) -> str:
    """Determine User Parity ('ODD' or 'EVEN') from the last digit of user_id.

    Example: '25CH10025' -> last digit 5 -> 'ODD'
             '25CH10024' -> last digit 4 -> 'EVEN'
    """
    digits = re.findall(r"\d", user_id or "")
    if not digits:
        return "ODD"
    last_digit = int(digits[-1])
    return "ODD" if last_digit % 2 == 1 else "EVEN"


def _load_course_names_lookup() -> dict[str, str]:
    """Load subject code -> subject name mapping from local ERP timetable cache if present."""
    lookup: dict[str, str] = {}
    if TIMETABLE_JSON_PATH.exists():
        try:
            with open(TIMETABLE_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("department_timetables", []):
                code = str(item.get("subject_code") or "").strip().upper()
                name = str(item.get("subject_name") or "").strip().title()
                if code and name:
                    lookup[code] = name
        except Exception:
            pass
    return lookup


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


def _extract_cell_lines(cell) -> list[str]:
    """Extract clean lines from an HTML cell by splitting on <br> tags and newlines."""
    raw_lines = cell.get_text("\n", strip=True).splitlines()
    cleaned: list[str] = []
    for line in raw_lines:
        s = line.strip()
        if s and s != "\xa0" and s.upper() != "&NBSP;":
            cleaned.append(s)
    return cleaned


def _parse_lines_into_pairs(lines: list[str]) -> list[tuple[str, str]]:
    """Parse cell lines structured as:
        [Course Code 1]
        [Room 1]
        [Course Code 2]
        [Room 2]
    into a list of (course_code, room) tuples in order.
    """
    pairs: list[tuple[str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        code_match = re.search(r"\b([A-Z]{2}\d{5})\b", line)
        if code_match:
            code = code_match.group(1).upper()
            # Check if the next line is the room (and not another course code)
            if i + 1 < n and not re.search(r"\b([A-Z]{2}\d{5})\b", lines[i + 1]):
                room = lines[i + 1].strip()
                pairs.append((code, room))
                i += 2
            else:
                # Fallback if room is on the same line as the course code
                rem = line.replace(code, "").strip(" -/()|:,")
                room = rem if rem else "Not specified"
                pairs.append((code, room))
                i += 1
        else:
            # Handle case where a second room is listed directly below the first room
            if pairs:
                prev_code = pairs[-1][0]
                pairs.append((prev_code, line.strip()))
            i += 1
    return pairs


def parse_visual_grid(html: str, user_id: str = "25CH10025") -> list[dict]:
    """Parse the student visual timetable grid HTML with Odd/Even roll parity filtering.

    1. Determine User Parity from the last digit of user_id (ODD vs EVEN).
    2. Extract header row to get time slots by splitting on '-'.
    3. Map cells into (day_of_week, slot_col_idx) and split cell content by <br> / newlines:
           [Course Code 1]
           [Room 1]
           [Course Code 2]
           [Room 2]
    4. Filter by Parity:
       - If only one room is listed, save it for everyone.
       - If two+ rooms are listed (Odd group first, Even group second):
         - ODD user -> save the first room (index 0)
         - EVEN user -> save the second room (index 1)
    """
    if not html:
        return []

    parity = get_user_parity(user_id)
    soup = BeautifulSoup(html, "html.parser")
    classes: list[dict] = []

    # Load known course names from local cache + page text
    course_names_map = _load_course_names_lookup()
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
            if len(cleaned_name) > 3 and code not in course_names_map:
                course_names_map[code] = cleaned_name

    # Step 1: Find the visual timetable table
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
        parts = text.split("-")
        if len(parts) >= 2:
            start_time = _format_time_component(parts[0])
            end_time = _format_time_component(parts[1])
            time_slots.append((start_time, end_time))

    if not time_slots:
        time_slots = list(DEFAULT_SLOTS)

    # Step 2: Build 2D coordinate grid accounting for rowspan and colspan
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

    # Step 3: Aggregate <br>-split lines per (day_of_week, c_idx) in top-to-bottom order.
    # This handles both:
    #   (a) Multiple <br>-separated [Course Code, Room] pairs inside a single <td>, AND
    #   (b) ERP's rowspan=2 day rows where Odd room is in sub-row 0 and Even room is in sub-row 1.
    slot_lines_map: dict[tuple[str, int], list[str]] = {}
    slot_colspan_map: dict[tuple[str, int], int] = {}
    current_day = None

    for (r_idx, c_idx), (cell, rowspan, colspan) in sorted(grid_cells.items()):
        if r_idx == 0:
            continue

        if c_idx == 0:
            first_text = cell.get_text(" ", strip=True).upper()
            first_clean = re.sub(r"[^A-Z]", "", first_text)
            for key, full_day in DAY_MAP.items():
                if first_clean == key or first_clean.startswith(key):
                    current_day = full_day
                    break
            continue

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

        lines = _extract_cell_lines(cell)
        if not lines:
            continue

        key = (day_for_cell, c_idx)
        if key not in slot_lines_map:
            slot_lines_map[key] = []
            slot_colspan_map[key] = colspan
        slot_lines_map[key].extend(lines)

    # Step 4: Parse lines for each (day, slot) and filter by Odd/Even parity
    for (day_for_cell, c_idx), lines in slot_lines_map.items():
        pairs = _parse_lines_into_pairs(lines)
        if not pairs:
            continue

        # Filter by Parity:
        # - If only 1 room listed, save it for everyone.
        # - If 2+ rooms listed (ERP lists Odd group first, Even group second):
        #   - ODD user -> first room (pairs[0])
        #   - EVEN user -> second room (pairs[1])
        if len(pairs) == 1:
            selected_code, selected_room = pairs[0]
        else:
            if parity == "ODD":
                selected_code, selected_room = pairs[0]
            else:
                selected_code, selected_room = pairs[1]

        course_name = course_names_map.get(
            selected_code, f"{selected_code} Lecture/Lab"
        )

        slot_idx = c_idx - 1
        colspan = slot_colspan_map.get((day_for_cell, c_idx), 1)
        if 0 <= slot_idx < len(time_slots):
            start_time, end_time = time_slots[slot_idx]
            if colspan > 1:
                end_slot_idx = min(slot_idx + colspan - 1, len(time_slots) - 1)
                end_time = time_slots[end_slot_idx][1]
        else:
            start_time, end_time = ("08:00 AM", "08:55 AM")

        entry = {
            "course_code": selected_code,
            "course_name": course_name,
            "day_of_week": day_for_cell,
            "start_time": start_time,
            "end_time": end_time,
            "location": selected_room,
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

    # Support offline re-sync from cached debug_student_timetable.html via --cached
    if "--cached" in sys.argv and DEBUG_HTML_PATH.exists():
        user_id = (
            os.environ.get("ROLL_NUMBER")
            or (sys.argv[sys.argv.index("--cached") + 1] if len(sys.argv) > sys.argv.index("--cached") + 1 else "25CH10025")
        ).strip().upper()
        parity = get_user_parity(user_id)
        print(f"ℹ️ Using cached HTML from {DEBUG_HTML_PATH}")
        print(f"Synchronizing schedule for student: {user_id} (Parity: {parity})")
        html_content = DEBUG_HTML_PATH.read_text(encoding="utf-8")
    else:
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

        parity = get_user_parity(user_id)
        print(f"Synchronizing schedule for student: {user_id} (Parity: {parity})")

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

    # Step 3: Parse the Visual Grid with exact time slot alignment and Odd/Even parity filtering
    classes = parse_visual_grid(html_content, user_id=user_id)
    print(f"Parsed {len(classes)} personalized ({parity}) classes from student timetable.")

    # Step 4: Clear existing rows for user_id and insert newly filtered classes into SQLite
    if classes:
        await insert_classes(user_id, classes)
        print(
            f"✅ Successfully replaced and inserted {len(classes)} classes for {user_id} ({parity}) into {DB_PATH}"
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
