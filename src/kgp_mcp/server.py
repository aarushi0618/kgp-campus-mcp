"""KGP Campus Intelligence MCP Server (MCP SDK v2)."""
import logging

from mcp.server import MCPServer

from kgp_mcp.adapters.dummy_academic import DummyAcademicAdapter
from kgp_mcp.adapters.calendar_adapter import CalendarAdapter
from kgp_mcp.infrastructure.cache import get_cache, set_cache, init_db
from kgp_mcp.models.campus_entity import CampusEntity

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server (v2 API)
mcp = MCPServer("KGP Campus Intelligence")

# Initialize Database on startup
init_db()

# Instantiate adapters
_academic_adapter = DummyAcademicAdapter()
_calendar_adapter = CalendarAdapter(
    url="https://www.iitkgp.ac.in/documents/ACADEMIC_CALENDAR_2026_27.pdf"
)


@mcp.tool()
async def search_courses(query: str) -> list[CampusEntity]:
    """Search academic courses by keyword."""
    logger.info("search_courses called with query='%s'", query)
    entities = await _academic_adapter.get_entities()
    query_lower = query.lower()
    return [
        e for e in entities
        if query_lower in e.title.lower()
        or query_lower in e.metadata.get("course_code", "").lower()
    ]


@mcp.tool()
async def get_academic_calendar(
    academic_year: str = "2026-27",
    category: str = "calendar",
) -> list[CampusEntity]:
    """Retrieve the academic calendar or important dates/notices."""
    cache_key = f"calendar:{academic_year}:{category}"

    cached_data = get_cache(cache_key)
    if cached_data:
        return [CampusEntity(**item) for item in cached_data]

    logger.info("Cache miss. Fetching fresh calendar data...")
    try:
        raw_pdf_bytes = await _calendar_adapter.fetch()
        entities = await _calendar_adapter.parse(raw_pdf_bytes)
        set_cache(cache_key, [e.model_dump() for e in entities], ttl_seconds=86400)
        return entities
    except Exception as e:
        logger.error(f"Failed to fetch calendar: {e}")
        raise ValueError(f"SOURCE_UNAVAILABLE: Could not fetch calendar. Error: {e}")


@mcp.tool()
def ping() -> str:
    """Health check tool."""
    return "pong"


if __name__ == "__main__":
    logger.info("Starting KGP Campus MCP Server over STDIO...")
    mcp.run(transport="stdio")