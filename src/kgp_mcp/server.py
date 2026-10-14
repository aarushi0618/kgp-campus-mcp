"""KGP Campus Intelligence MCP Server (MCP SDK v2)."""
import logging

from mcp.server import MCPServer

from kgp_mcp.adapters.dummy_academic import DummyAcademicAdapter
from kgp_mcp.adapters.calendar_adapter import CalendarAdapter
from kgp_mcp.adapters.location_adapter import LocationAdapter
from kgp_mcp.infrastructure.cache import get_cache, set_cache, init_db
from kgp_mcp.infrastructure.osm_client import OSMClient
from kgp_mcp.models.campus_entity import CampusEntity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = MCPServer("KGP Campus Intelligence")
init_db()

# Adapters
_academic_adapter = DummyAcademicAdapter()
_calendar_adapter = CalendarAdapter(
    url="https://www.iitkgp.ac.in/documents/ACADEMIC_CALENDAR_2026_27.pdf"
)
_osm_client = OSMClient()
_location_adapter = LocationAdapter(
    url="https://hmc.iitkgp.ac.in/web/warden/",
    osm_client=_osm_client,
)


@mcp.tool()
async def search_courses(query: str) -> list[CampusEntity]:
    """Search academic courses by keyword."""
    entities = await _academic_adapter.get_entities()
    q = query.lower()
    return [
        e for e in entities
        if q in e.title.lower() or q in e.metadata.get("course_code", "").lower()
    ]


@mcp.tool()
async def get_academic_calendar(
    academic_year: str = "2026-27", category: str = "calendar"
) -> list[CampusEntity]:
    """Retrieve the academic calendar or important dates/notices."""
    cache_key = f"calendar:{academic_year}:{category}"
    cached = get_cache(cache_key)
    if cached:
        return [CampusEntity(**item) for item in cached]

    try:
        raw = await _calendar_adapter.fetch()
        entities = await _calendar_adapter.parse(raw)
        set_cache(cache_key, [e.model_dump() for e in entities],
                  ttl_seconds=_calendar_adapter.DEFAULT_TTL)
        return entities
    except Exception as e:
        logger.error(f"Calendar fetch failed: {e}")
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


@mcp.tool()
async def search_locations(
    query: str, facility_type: str = None
) -> list[CampusEntity]:
    """Search campus buildings and facilities (halls, departments, etc.).

    Args:
        query: Free-text search (e.g. 'Nehru', 'LBS', 'Vidyasagar').
        facility_type: Optional filter, e.g. 'hostel', 'department'.
    """
    cache_key = f"locations:{query}:{facility_type}"
    cached = get_cache(cache_key)
    if cached:
        return [CampusEntity(**item) for item in cached]

    try:
        entities = await _location_adapter.get_entities()
        q = query.lower()
        results = [
            e for e in entities
            if q in e.title.lower()
            and (facility_type is None
                 or facility_type.lower() in e.metadata.get("facility_type", "").lower())
        ]
        set_cache(cache_key, [e.model_dump() for e in results],
                  ttl_seconds=_location_adapter.DEFAULT_TTL)
        return results
    except Exception as e:
        logger.error(f"Locations fetch failed: {e}")
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


@mcp.tool()
def ping() -> str:
    """Health check."""
    return "pong"


if __name__ == "__main__":
    logger.info("Starting KGP Campus MCP Server over STDIO...")
    mcp.run(transport="stdio")