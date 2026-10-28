"""KGP Campus Intelligence MCP Server (MCP SDK v2)."""
import asyncio
from datetime import datetime
import json
import logging
from pathlib import Path
import re
import traceback
from typing import Optional

from mcp.server import MCPServer

from kgp_mcp.adapters.erp_adapter import ERPAdapter
from kgp_mcp.adapters.academic_adapter import AcademicAdapter
from kgp_mcp.adapters.calendar_adapter import CalendarAdapter
from kgp_mcp.adapters.location_adapter import LocationAdapter
from kgp_mcp.adapters.faculty_adapter import FacultyAdapter
from kgp_mcp.adapters.gymkhana_api_adapter import GymkhanaAPIAdapter
from kgp_mcp.adapters.gymkhana_adapter import GymkhanaHTMLAdapter
from kgp_mcp.config import GYMKHANA_LLM_SECTIONS
from kgp_mcp.infrastructure.cache import get_cache, set_cache, init_db as init_cache_db
from kgp_mcp.infrastructure.database import (
    get_classes,
    init_db as init_campus_db,
    DB_PATH as CAMPUS_DB_PATH,
)
from kgp_mcp.infrastructure.osm_client import OSMClient
from kgp_mcp.models.campus_entity import CampusEntity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Absolute paths regardless of CWD
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DATA_FILE = DATA_DIR / "societies_dump.json"
ERP_DATA_FILE = DATA_DIR / "erp_timetable_data.json"
COURSES_DATA_FILE = DATA_DIR / "courses_dump.json"
FACULTY_DATA_FILE = DATA_DIR / "faculty_parsed_cache.json"
COORDINATES_DATA_FILE = DATA_DIR / "hall_coordinates.json"
ERROR_LOG_FILE = DATA_DIR / "mcp_error_log.txt"

mcp = MCPServer("KGP Campus Intelligence")
init_cache_db()

# ---------------- Adapters ----------------
_academic_adapter = AcademicAdapter()
_erp_adapter = ERPAdapter()
_calendar_adapter = CalendarAdapter(url="https://www.iitkgp.ac.in/documents/ACADEMIC_CALENDAR_2026_27.pdf")
_location_adapter = LocationAdapter(url="https://hmc.iitkgp.ac.in/web/warden/", osm_client=OSMClient())
_faculty_adapter = FacultyAdapter()
_gymkhana_events_api = GymkhanaAPIAdapter(is_event=True, limit=100)

_gymkhana_llm_adapters = {
    name: GymkhanaHTMLAdapter(
        url=cfg["url"], entity_type=cfg["entity_type"], schema_description=cfg["schema_description"],
        example_json=cfg["example_json"], ttl=cfg["ttl"], tag=name,
    ) for name, cfg in GYMKHANA_LLM_SECTIONS.items()
}

DEPT_MAP = {
    "chemical": "CH", "chem": "CH", "ch": "CH",
    "computer science": "CS", "cse": "CS", "cs": "CS",
    "mechanical": "ME", "mech": "ME", "me": "ME",
    "electrical": "EE", "ee": "EE",
    "electronics": "EC", "ece": "EC", "ec": "EC",
    "civil": "CE", "ce": "CE",
    "aerospace": "AE", "ae": "AE",
    "biotech": "BT", "biotechnology": "BT", "bt": "BT",
    "mathematics": "MA", "maths": "MA", "ma": "MA",
    "physics": "PH", "ph": "PH",
    "chemistry": "CY", "cy": "CY",
    "metallurgy": "MT", "mt": "MT",
    "mining": "MI", "mi": "MI",
    "ocean": "NA", "naval": "NA", "na": "NA",
    "agricultural": "AG", "agfe": "AG", "ag": "AG",
    "architecture": "AR", "ar": "AR",
    "geology": "GG", "geophysics": "GG", "gg": "GG",
    "humanities": "HS", "hss": "HS", "hs": "HS",
    "industrial": "IM", "ise": "IM", "im": "IM",
    "artificial intelligence": "AI", "ai": "AI",
}


def _log_and_make_error_entity(tool_name: str, exc: Exception) -> list[CampusEntity]:
    try:
        ERROR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n--- Error in {tool_name} ---\n{traceback.format_exc()}\n")
    except Exception as log_err:
        logger.error(f"Failed to write to {ERROR_LOG_FILE}: {log_err}")
    return [
        CampusEntity(
            id="err",
            entity_type="notice",
            title="Tool Error",
            description=str(exc)[:1000],
            source_url="none",
            metadata={"tool": tool_name},
        )
    ]


def _make_no_results_entity(tool_name: str, message: str = "The tool ran but found 0 matches.") -> list[CampusEntity]:
    return [
        CampusEntity(
            id="err",
            entity_type="notice",
            title="No Results",
            description=message,
            source_url="none",
            metadata={"tool": tool_name},
        )
    ]


async def _get_cached_entities(cache_key: str, adapter, ttl: int = 86400, source_file: Optional[str] = None) -> list[CampusEntity]:
    """Helper to load CampusEntity list from SQLite cache (auto-invalidated if source_file is modified)."""
    try:
        cached = get_cache(cache_key, source_file=source_file)
        if cached is not None:
            try:
                return [CampusEntity(**item) for item in cached]
            except Exception as e:
                logger.warning(f"Cached data deserialization failed for {cache_key}, refetching: {e}")

        entities = await adapter.get_entities()
        if entities:
            set_cache(
                cache_key,
                [e.model_dump(mode="json") for e in entities],
                ttl_seconds=ttl,
                source_file=source_file,
            )
        return entities
    except Exception as e:
        logger.error(f"_get_cached_entities failed for {cache_key}: {e}")
        return []


# ---------------- Core Tools ----------------
@mcp.tool()
async def search_courses(query: Optional[str] = None) -> list[CampusEntity]:
    """Search academic courses by keyword across all departments."""
    try:
        entities = await _get_cached_entities(
            "courses_all", _academic_adapter, ttl=86400, source_file=str(COURSES_DATA_FILE)
        )
        q = (query or "").lower().strip()
        if not q:
            results = entities
        else:
            results = [
                e for e in entities
                if q in (e.title or "").lower()
                or q in (e.description or "").lower()
                or q in str(e.metadata.get("course_code", "")).lower()
            ]
        return results
    except Exception as e:
        return _log_and_make_error_entity("search_courses", e)


@mcp.tool()
async def search_faculty(query: Optional[str] = None, department: Optional[str] = None) -> list[CampusEntity]:
    """Search for faculty members by name, research area, or department."""
    try:
        entities = await _get_cached_entities(
            "faculty_all", _faculty_adapter, ttl=86400, source_file=str(FACULTY_DATA_FILE)
        )
        results = entities

        if department:
            d = department.lower().strip()
            target_code = DEPT_MAP.get(d, d.upper())
            results = [
                e for e in results
                if target_code == str(e.metadata.get("department_code", "")).upper()
                or d in str(e.metadata.get("department_name", "")).lower()
            ]

        if query:
            q = query.lower().strip()
            results = [
                e for e in results
                if q in (e.title or "").lower()
                or q in (e.description or "").lower()
                or q in str(e.metadata.get("research_area", "")).lower()
            ]

        if not results:
            return _make_no_results_entity("search_faculty", f"No faculty matched query='{query}', dept='{department}'")
        return results
    except Exception as e:
        return _log_and_make_error_entity("search_faculty", e)


@mcp.tool()
async def get_erp_timetable(department: Optional[str] = None, subject_code: Optional[str] = None) -> list[CampusEntity]:
    """Find the room number, professors, and schedule for a specific subject code (e.g., 'CH21202') or department (e.g., 'CH')."""
    try:
        if not ERP_DATA_FILE.exists():
            logger.warning(f"ERP data file not found: {ERP_DATA_FILE}")
            return _make_no_results_entity("get_erp_timetable", "ERP data file not found.")

        entities = await _get_cached_entities(
            "erp_timetable_all", _erp_adapter, ttl=86400, source_file=str(ERP_DATA_FILE)
        )
        results = entities

        if department:
            d = str(department).lower().strip()
            if d:
                target_code = DEPT_MAP.get(d, d.upper())
                results = [
                    e for e in results
                    if target_code == str(e.metadata.get("department", "")).upper()
                ]

        if subject_code:
            s = str(subject_code).strip().lower()
            if s:
                exact = [
                    e for e in results
                    if str(e.metadata.get("subject_code", "")).lower() == s
                ]
                if exact:
                    results = exact
                else:
                    results = [
                        e for e in results
                        if s in str(e.metadata.get("subject_code", "")).lower()
                        or s in str(e.metadata.get("subject_name", "")).lower()
                        or s in (e.title or "").lower()
                        or s in (e.description or "").lower()
                    ]

        if not results:
            return _make_no_results_entity("get_erp_timetable", f"No timetable found for subject='{subject_code}', dept='{department}'")
        return results
    except Exception as e:
        return _log_and_make_error_entity("get_erp_timetable", e)


@mcp.tool()
async def search_locations(query: Optional[str] = None, facility_type: Optional[str] = None) -> list[CampusEntity]:
    """Search campus buildings and facilities (halls, departments, etc.)."""
    try:
        entities = await _get_cached_entities(
            "locations_all", _location_adapter, ttl=604800, source_file=str(COORDINATES_DATA_FILE)
        )
        q = (query or "").lower().strip()
        results = [
            e for e in entities
            if (not q or q in (e.title or "").lower() or q in (e.description or "").lower())
            and (facility_type is None or facility_type.lower() in str(e.metadata.get("facility_type", "")).lower())
        ]
        if not results:
            return _make_no_results_entity("search_locations", f"No locations matched query='{query}', facility_type='{facility_type}'")
        return results
    except Exception as e:
        return _log_and_make_error_entity("search_locations", e)


@mcp.tool()
async def get_academic_calendar(academic_year: Optional[str] = "2026-27", category: Optional[str] = "calendar") -> list[CampusEntity]:
    """Retrieve the academic calendar or important dates/notices."""
    try:
        results = await _get_cached_entities(f"calendar_{academic_year or '2026-27'}", _calendar_adapter, ttl=86400)
        if not results:
            return _make_no_results_entity("get_academic_calendar", f"No calendar entries found for year='{academic_year}'")
        return results
    except Exception as e:
        return _log_and_make_error_entity("get_academic_calendar", e)


# ---------------- Gymkhana Tools ----------------
@mcp.tool()
async def find_gymkhana_events(query: Optional[str] = None, category: Optional[str] = None) -> list[CampusEntity]:
    """Find upcoming events from the TSG Gymkhana portal."""
    try:
        entities = await _gymkhana_events_api.get_entities()

        if query:
            q = str(query).lower().strip()
            if q:
                entities = [
                    e for e in entities
                    if q in (e.title or "").lower()
                    or q in (e.description or "").lower()
                    or q in str(e.metadata.get("society", "")).lower()
                    or q in str(e.metadata.get("category", "")).lower()
                ]

        if category:
            c = str(category).lower().strip()
            if c:
                entities = [
                    e for e in entities
                    if c in str(e.metadata.get("category", "")).lower()
                    or c in str(e.metadata.get("event_category", "")).lower()
                ]

        # Sort safely by event_date string comparison (newest first) without strict datetime parsing
        entities = sorted(entities, key=lambda x: str(x.metadata.get("event_date", "")), reverse=True)
        if not entities:
            return _make_no_results_entity("find_gymkhana_events", f"No events found for query='{query}', category='{category}'")
        return entities
    except Exception as e:
        return _log_and_make_error_entity("find_gymkhana_events", e)


@mcp.tool()
async def find_societies(query: Optional[str] = None, category: Optional[str] = None) -> list[CampusEntity]:
    """Find student societies/clubs at IIT KGP by name or category."""
    try:
        if not DATA_FILE.exists():
            logger.warning(f"Societies dump not found at {DATA_FILE}")
            return _make_no_results_entity("find_societies", f"Societies dump file missing at {DATA_FILE}")

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            socs = json.load(f)

        results = []
        for s in socs:
            if not isinstance(s, dict):
                continue
            name = str(s.get("name", "Unknown") or "Unknown").strip()
            if not name:
                name = "Unknown"
            cat = str(s.get("category", "General") or "General").strip()
            desc = str(s.get("description", "") or "").strip()
            slug = str(s.get("slug", "") or name.lower().replace(" ", "_")).strip()

            if category:
                c = str(category).lower().strip()
                if c and c not in cat.lower():
                    continue

            if query:
                q = str(query).lower().strip()
                if q and (
                    q not in name.lower()
                    and q not in desc.lower()
                    and q not in cat.lower()
                    and q not in slug.lower()
                ):
                    continue

            results.append(CampusEntity(
                id=f"society:{slug}",
                entity_type="location",
                title=name[:200],
                description=desc[:2000],
                source_url="https://gymkhana.iitkgp.ac.in/societies",
                metadata={
                    "category": s.get("category", "General") or "General",
                    "slug": s.get("slug", "") or slug,
                },
            ))

        if not results:
            return _make_no_results_entity("find_societies", f"No societies found matching query='{query}', category='{category}'")
        return results
    except Exception as e:
        return _log_and_make_error_entity("find_societies", e)


@mcp.tool()
async def get_hall_of_fame() -> list[CampusEntity]:
    """Get IIT KGP Hall of Fame awards."""
    try:
        results = await _get_cached_entities("gymkhana_awards", _gymkhana_llm_adapters["awards"], ttl=86400)
        if not results:
            return _make_no_results_entity("get_hall_of_fame", "No Hall of Fame entries found.")
        return results
    except Exception as e:
        return _log_and_make_error_entity("get_hall_of_fame", e)


@mcp.tool()
async def get_election_info() -> list[CampusEntity]:
    """Get TSG election info and notices."""
    try:
        results = await _get_cached_entities("gymkhana_elections", _gymkhana_llm_adapters["elections"], ttl=3600)
        if not results:
            return _make_no_results_entity("get_election_info", "No election notices found.")
        return results
    except Exception as e:
        return _log_and_make_error_entity("get_election_info", e)


@mcp.tool()
async def get_gc_results() -> list[CampusEntity]:
    """Get General Championship (GC) results."""
    try:
        results = await _get_cached_entities("gymkhana_gc_results", _gymkhana_llm_adapters["gc_results"], ttl=86400)
        if not results:
            return _make_no_results_entity("get_gc_results", "No GC results found.")
        return results
    except Exception as e:
        return _log_and_make_error_entity("get_gc_results", e)


@mcp.tool()
async def get_technology_committee() -> list[CampusEntity]:
    """Get societies under the Technology Committee."""
    try:
        results = await find_societies(category="Technology")
        if not results:
            return _make_no_results_entity("get_technology_committee", "No societies found under Technology Committee.")
        return results
    except Exception as e:
        return _log_and_make_error_entity("get_technology_committee", e)


# ---------------- Personalized Class Schedule Tools ----------------
@mcp.tool()
async def get_user_schedule(user_id: str, target_day: Optional[str] = None) -> str:
    """Fetch the student's personalized class schedule from the local SQLite shadow sync database."""
    try:
        user_clean = str(user_id or "").strip().upper()
        if not user_clean:
            return "No user_id provided. Please specify your Roll Number (e.g., '25CH10025')."

        classes = await get_classes(user_clean, target_day=target_day)
        if not classes:
            return (
                f"No schedule found for student {user_clean}. "
                "Please run python erp_shadow_sync.py in your terminal to sync your ERP timetable."
            )

        # Format output as clean Markdown grouped by day
        lines = [f"### 📅 Class Schedule for {user_clean}"]
        if target_day:
            lines[0] += f" ({target_day.strip().capitalize()})"
        lines.append("")

        current_day = None
        for c in classes:
            day = c.get("day_of_week", "Unknown Day")
            if day != current_day:
                current_day = day
                lines.append(f"#### **{current_day}**")

            code = c.get("course_code", "Unknown Code")
            name = c.get("course_name") or code
            start = c.get("start_time", "")
            end = c.get("end_time", "")
            time_str = f"{start} - {end}" if end else start
            room = c.get("location", "Not specified")

            lines.append(f"- **{time_str}** | `{code}` {name} | 📍 Room: **{room}**")

        return "\n".join(lines)
    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"get_user_schedule crashed: {error_msg}")
        try:
            ERROR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(ERROR_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n--- Error in get_user_schedule ---\n{error_msg}\n")
        except Exception:
            pass
        return "No schedule found. Please run python erp_shadow_sync.py in your terminal to sync your ERP timetable."


def _parse_time_minutes(time_str: str) -> Optional[int]:
    """Parse time string like '10:00 AM' or '14:30' into minutes since midnight."""
    if not time_str:
        return None
    time_str = time_str.strip().upper()
    m = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)?", time_str)
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


@mcp.tool()
async def smart_activity_planner(
    user_id: str,
    current_location: Optional[str] = None,
    focus_level: Optional[str] = None,
) -> str:
    """Dynamic activity and study planner that reasons over today's timetable and user location."""
    try:
        user_clean = str(user_id or "").strip().upper()
        if not user_clean:
            return "Please provide your student Roll Number."

        today_name = datetime.now().strftime("%A")
        today_classes = await get_classes(user_clean, target_day=today_name)

        # Check if the user has a class soon (within the next 120 minutes or currently underway)
        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute
        upcoming_class = None

        for c in today_classes:
            start_min = _parse_time_minutes(c.get("start_time"))
            end_min = _parse_time_minutes(c.get("end_time"))
            if start_min is not None:
                # Class in next 120 min OR ongoing right now
                if (start_min - 120 <= now_minutes <= (end_min or (start_min + 60))):
                    upcoming_class = c
                    break

        # Hard Stop Dynamic Elicitation Directive
        # If user has a class/deadline soon AND focus_level is None: STOP and ask user
        if upcoming_class and not focus_level:
            return (
                "SYSTEM DIRECTIVE: You must STOP and ask the user: "
                "'Are you able to focus where you are right now, or are you feeling distracted?' "
                "Wait for the user to reply, then call this tool again with the focus_level parameter."
            )

        # If all parameters are provided, return recommendation based on schedule, location, and focus level
        lines = [f"### 🎯 Smart Study & Activity Recommendation for {user_clean}"]
        lines.append(f"- **Today**: {today_name} ({len(today_classes)} classes on schedule)")
        if current_location:
            lines.append(f"- **Current Location**: {current_location}")
        if focus_level:
            lines.append(f"- **Focus State**: {focus_level.title()}")
        lines.append("")

        focus_clean = (focus_level or "").lower()
        if upcoming_class:
            c_code = upcoming_class.get("course_code")
            c_name = upcoming_class.get("course_name") or c_code
            c_loc = upcoming_class.get("location", "classroom")
            c_time = upcoming_class.get("start_time")
            lines.append(f"⚠️ **Upcoming Class Soon**: `{c_code}` ({c_name}) at **{c_time}** in **{c_loc}**.")

            if "distract" in focus_clean or "low" in focus_clean or "tired" in focus_clean:
                lines.append(
                    f"💡 **Recommendation**: Since you're feeling distracted/low focus, take a 10-minute quiet walk "
                    f"towards {c_loc} or grab water at the department lobby before class begins. Avoid starting heavy deep work now."
                )
            else:
                lines.append(
                    f"💡 **Recommendation**: You have high focus! Use the remaining time near {c_loc} (e.g. Nalanda Classroom Complex study area) "
                    f"for a quick 25-minute Pomodoro review of `{c_code}` lecture slides."
                )
        else:
            if "distract" in focus_clean or "low" in focus_clean:
                lines.append(
                    "💡 **Recommendation**: No immediate classes found. Since focus is low, head to the Central Library "
                    "or Nehru Museum cafe for a change of scenery and light revision."
                )
            else:
                lines.append(
                    "💡 **Recommendation**: Excellent focus state with no immediate class conflicts! "
                    "Great window for a 90-minute deep work block on assignments or research in your department lab or Central Library."
                )

        return "\n".join(lines)
    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"smart_activity_planner crashed: {error_msg}")
        return f"Could not generate planner recommendation: {e}"


# ---------------- Unified Search ----------------
@mcp.tool()
async def search_all(query: str, limit: int = 20) -> dict:
    """Unified cross-source search across academics, ERP timetable, events, locations, and societies."""
    try:
        tasks = {
            "academic": search_courses(query),
            "erp_timetable": get_erp_timetable(subject_code=query),
            "events": find_gymkhana_events(query),
            "locations": search_locations(query),
            "societies": find_societies(query=query),
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        response = {"query": query, "results": {}, "errors": []}

        for source_name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                response["errors"].append({"source": source_name, "error": str(result)})
            else:
                entities = [e.model_dump(mode="json") for e in (result or [])[:limit]]
                response["results"][source_name] = entities

        return response
    except Exception as e:
        logger.error(f"search_all failed: {e}")
        return {"query": query, "results": {}, "errors": [{"source": "search_all", "error": str(e)}]}


@mcp.tool()
def ping() -> str:
    """Health check."""
    try:
        return "pong"
    except Exception:
        return "pong"


if __name__ == "__main__":
    logger.info("Starting KGP Campus MCP Server over STDIO...")
    mcp.run(transport="stdio")
