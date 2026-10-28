import json
import os
import re
import sys
from bs4 import BeautifulSoup
import iitkgp_erp_login.erp as erp
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OUTPUT_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "erp_timetable_data.json"))
CACHE_DB = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "kgp_mcp_cache.db"))

ACADEMIC_UNIT_CODES = [
    "AE", "AG", "AR", "BT", "CH", "CY", "CE", "CS", "EE", "EC", "GG", "HS",
    "IM", "MA", "ME", "MT", "MI", "NA", "PH", "SD", "AI", "AT", "ET", "CL",
    "TS", "CD", "CR", "RX", "DE", "MS", "RT", "RD", "BE", "DH", "EX", "KS",
    "FH", "FN", "CP", "SH", "SE", "SL", "BS", "ES", "EF", "GS", "NT", "RJ",
    "IP", "ID", "MM", "WM", "RE", "BM", "AF", "AP"
]

SUBJECT_CODE_RE = re.compile(r"^[A-Z]{2}\d{5}$")


def _extract_leaf_tds(container) -> list:
    """Extract leaf <td> cells without duplicating wrapper <td> cells caused by unclosed tags."""
    all_tds = container.find_all("td")
    leaf_tds = []
    for td in all_tds:
        # Skip wrapper td that contains inner tables or other td elements
        if td.find("table") or td.find("td"):
            continue
        if td.get("colspan"):
            continue
        leaf_tds.append(td)
    return leaf_tds


def parse_timetable_table(html: str, dept_code: str) -> list:
    """Robustly parse broken ERP HTML by scanning flat leaf <td> cells and pairing them up."""
    # Strip stray closing tags or parse with html.parser
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="disptab") or soup

    tds = _extract_leaf_tds(table)
    if not tds:
        tds = table.find_all("td")

    entries_by_code: dict[str, dict] = {}
    i = 0
    n = len(tds)

    while i < n:
        cell_text = tds[i].get_text(" ", strip=True)

        # Check if this cell contains a valid subject code (e.g., CH21202)
        if SUBJECT_CODE_RE.match(cell_text):
            subject_code = cell_text

            # Find the boundary of this record (up to 6 following cells, stopping early if another subject code appears)
            next_cells = []
            for offset in range(1, 7):
                if i + offset < n:
                    val = tds[i + offset].get_text(" ", strip=True)
                    if SUBJECT_CODE_RE.match(val):
                        break
                    next_cells.append(val)

            # Standard 7-column layout:
            # [0] Subject Code, [1] Subject Name, [2] Faculty Name, [3] LTP, [4] Credits, [5] Slot, [6] Room
            subject_name = next_cells[0] if len(next_cells) > 0 else "Unknown Subject"
            professors = next_cells[1] if len(next_cells) > 1 else "Not specified"
            ltp = next_cells[2] if len(next_cells) > 2 else ""
            credits = next_cells[3] if len(next_cells) > 3 else ""
            slot = next_cells[4] if len(next_cells) > 4 else "Not specified"
            room_text = next_cells[5] if len(next_cells) > 5 else ""

            # Deduplicate rooms while preserving order, or keep clean room list
            if room_text:
                rooms_unique = list(dict.fromkeys(r.strip() for r in room_text.split(",") if r.strip()))
                room = ", ".join(rooms_unique) if rooms_unique else "Not specified"
            else:
                room = "Not specified"

            entry = {
                "department": dept_code,
                "subject_code": subject_code,
                "subject_name": subject_name or "Unknown Subject",
                "professors": professors or "Not specified",
                "ltp": ltp,
                "credits": credits,
                "slot": slot or "Not specified",
                "room": room,
            }

            # Merge if subject appears multiple times (e.g. multiple sections)
            if subject_code in entries_by_code:
                existing = entries_by_code[subject_code]
                if existing.get("room") == "Not specified" and room != "Not specified":
                    existing["room"] = room
                if existing.get("slot") in ("", "Not specified") and slot not in ("", "Not specified"):
                    existing["slot"] = slot
                if existing.get("professors") in ("", "Not specified") and professors not in ("", "Not specified"):
                    existing["professors"] = professors
            else:
                entries_by_code[subject_code] = entry

            i += 1 + len(next_cells)
        else:
            i += 1

    return list(entries_by_code.values())


def main():
    print("--- 🚀 Starting ERP Full Sync ---")
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        sessionToken, ssoToken = erp.login(headers, session)
        print("✅ Login successful.\n")
    except Exception as e:
        print(f"❌ Login failed: {e}")
        if os.path.exists(OUTPUT_FILE):
            print(f"ℹ️ Keeping existing local timetable data at {OUTPUT_FILE}")
            return
        sys.exit(1)

    master_data = {"department_timetables": []}

    for dept in ACADEMIC_UNIT_CODES:
        url = f"https://erp.iitkgp.ac.in/Acad/timetable_track.jsp?action=second&dept={dept}"
        print(f"  -> Fetching {dept}...", end=" ", flush=True)
        try:
            response = session.get(url, timeout=20)
            if response.status_code == 200:
                entries = parse_timetable_table(response.text, dept)
                master_data["department_timetables"].extend(entries)
                print(f"Found {len(entries)} subjects.")
            else:
                print("No data.")
        except Exception as e:
            print(f"Failed ({e}).")

    if master_data["department_timetables"]:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(master_data, f, indent=2, ensure_ascii=False)

        # Invalidate SQLite cache when JSON is updated
        if os.path.exists(CACHE_DB):
            try:
                os.remove(CACHE_DB)
                print("🗑️ Invalidated SQLite cache (kgp_mcp_cache.db).")
            except Exception:
                pass

        print(f"\n✅ Sync Complete! Saved {len(master_data['department_timetables'])} entries to {OUTPUT_FILE}.")
        print("👉 You can now restart Claude Desktop.")
    else:
        print("\n⚠️ No entries fetched; preserved existing timetable JSON.")


if __name__ == "__main__":
    main()