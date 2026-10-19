"""KGP Campus Intelligence MCP Server (MCP SDK v2)."""
import asyncio
import logging

from mcp.server import MCPServer

from kgp_mcp.adapters.dummy_academic import DummyAcademicAdapter
from kgp_mcp.adapters.calendar_adapter import CalendarAdapter
from kgp_mcp.adapters.location_adapter import LocationAdapter
from kgp_mcp.adapters.gymkhana_api_adapter import GymkhanaAPIAdapter
from kgp_mcp.adapters.gymkhana_adapter import GymkhanaHTMLAdapter
from kgp_mcp.config import GYMKHANA_LLM_SECTIONS
from kgp_mcp.infrastructure.cache import get_cache, set_cache, init_db
from kgp_mcp.infrastructure.osm_client import OSMClient
from kgp_mcp.models.campus_entity import CampusEntity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mcp = MCPServer("KGP Campus Intelligence")
init_db()

# ---------------- Adapters ----------------
_academic_adapter = DummyAcademicAdapter()
_calendar_adapter = CalendarAdapter(
    url="https://www.iitkgp.ac.in/documents/ACADEMIC_CALENDAR_2026_27.pdf"
)
_location_adapter = LocationAdapter(
    url="https://hmc.iitkgp.ac.in/web/warden/",
    osm_client=OSMClient(),
)

# Gymkhana JSON API adapters
_gymkhana_events_api = GymkhanaAPIAdapter(is_event=True, limit=100)
_gymkhana_notices_api = GymkhanaAPIAdapter(is_event=False, limit=100)

# Gymkhana LLM-based adapters
_gymkhana_llm_adapters = {
    name: GymkhanaHTMLAdapter(
        url=cfg["url"],
        entity_type=cfg["entity_type"],
        schema_description=cfg["schema_description"],
        example_json=cfg["example_json"],
        ttl=cfg["ttl"],
        tag=name,
    )
    for name, cfg in GYMKHANA_LLM_SECTIONS.items()
}


# ---------------- Core Tools ----------------
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
        set_cache(cache_key, [e.model_dump(mode="json") for e in entities],
                  ttl_seconds=_calendar_adapter.DEFAULT_TTL)
        return entities
    except Exception as e:
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


@mcp.tool()
async def search_locations(query: str, facility_type: str = None) -> list[CampusEntity]:
    """Search campus buildings and facilities (halls, departments, etc.)."""
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
        set_cache(cache_key, [e.model_dump(mode="json") for e in results],
                  ttl_seconds=_location_adapter.DEFAULT_TTL)
        return results
    except Exception as e:
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


@mcp.tool()
async def get_hall_info(hall_name: str) -> list[CampusEntity]:
    """Retrieve information about a specific hall of residence or studio.

    Args:
        hall_name: Name of the hall, e.g. 'Nehru Hall'.
    """
    cache_key = f"hall:{hall_name}"
    cached = get_cache(cache_key)
    if cached:
        return [CampusEntity(**item) for item in cached]

    try:
        entities = await _location_adapter.get_entities()
        query_lower = hall_name.lower().replace(" hall", "").replace(" of residence", "").strip()
        results = [e for e in entities if query_lower in e.title.lower()]
        results = results[:1]
        set_cache(cache_key, [e.model_dump(mode="json") for e in results], ttl_seconds=604800)
        return results
    except Exception as e:
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


# ---------------- Gymkhana Tools ----------------
async def _run_gymkhana_api(adapter, query=None, category=None):
    key = f"gymkhana_api:{adapter.is_event}:{adapter.category}:{query}:{category}"
    cached = get_cache(key)
    if cached:
        return [CampusEntity(**item) for item in cached]
    try:
        entities = await adapter.get_entities()
        if query:
            q = query.lower()
            entities = [e for e in entities if q in e.title.lower() or q in e.description.lower()]
        if category:
            c = category.lower()
            entities = [e for e in entities if c in str(e.metadata.get("category", "")).lower()]
        set_cache(key, [e.model_dump(mode="json") for e in entities], ttl_seconds=adapter.DEFAULT_TTL)
        return entities
    except Exception as e:
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


async def _run_gymkhana_llm(section, query=None, category=None):
    adapter = _gymkhana_llm_adapters[section]
    key = f"gymkhana_llm:{section}:{query}:{category}"
    cached = get_cache(key)
    if cached:
        return [CampusEntity(**item) for item in cached]
    try:
        entities = await adapter.get_entities()
        if query:
            q = query.lower()
            entities = [e for e in entities if q in e.title.lower() or q in e.description.lower()]
        if category:
            c = category.lower()
            entities = [e for e in entities if c in str(e.metadata.get("category", "")).lower()]
        set_cache(key, [e.model_dump(mode="json") for e in entities], ttl_seconds=adapter.DEFAULT_TTL)
        return entities
    except Exception as e:
        raise ValueError(f"SOURCE_UNAVAILABLE: {e}")


@mcp.tool()
async def find_gymkhana_events(query: str = None, category: str = None) -> list[CampusEntity]:
    """Find upcoming events from the TSG Gymkhana portal (via JSON API)."""
    return await _run_gymkhana_api(_gymkhana_events_api, query, category)


@mcp.tool()
async def find_gymkhana_notices(query: str = None, category: str = None) -> list[CampusEntity]:
    """Find notices/posts from the TSG Gymkhana portal (via JSON API)."""
    return await _run_gymkhana_api(_gymkhana_notices_api, query, category)


@mcp.tool()
async def find_societies(query: str = None, category: str = None) -> list[CampusEntity]:
    """Find student societies/clubs at IIT KGP."""
    return await _run_gymkhana_llm("societies", query, category)


@mcp.tool()
async def get_hall_of_fame() -> list[CampusEntity]:
    """Get IIT KGP Hall of Fame awards."""
    return await _run_gymkhana_llm("awards")


@mcp.tool()
async def get_gc_results() -> list[CampusEntity]:
    """Get General Championship (GC) results."""
    return await _run_gymkhana_llm("gc_results")


@mcp.tool()
async def get_interiit_results() -> list[CampusEntity]:
    """Get Inter-IIT results."""
    return await _run_gymkhana_llm("interiit_results")


@mcp.tool()
async def get_election_info() -> list[CampusEntity]:
    """Get TSG election info and notices."""
    return await _run_gymkhana_llm("elections")


@mcp.tool()
async def get_nominations() -> list[CampusEntity]:
    """Get current TSG nominated office bearers."""
    return await _run_gymkhana_llm("nominations")


@mcp.tool()
async def get_technology_committee() -> list[CampusEntity]:
    """Get societies under the Technology Committee."""
    return await _run_gymkhana_llm("committee_tech")


@mcp.tool()
async def get_socult_committee() -> list[CampusEntity]:
    """Get societies under the Social & Cultural Committee."""
    return await _run_gymkhana_llm("committee_socult")


@mcp.tool()
async def get_sports_committee() -> list[CampusEntity]:
    """Get societies under the Sports Committee."""
    return await _run_gymkhana_llm("committee_sports")


@mcp.tool()
async def get_welfare_committee() -> list[CampusEntity]:
    """Get societies under the Students' Welfare Committee."""
    return await _run_gymkhana_llm("committee_welfare")


# ---------------- Unified Search ----------------
@mcp.tool()
async def search_all(query: str, limit: int = 20) -> dict:
    """Unified cross-source search across academics, events, and locations.

    Fans out to all tools in parallel. Gracefully degrades if a source fails.
    """
    logger.info(f"Unified search for: '{query}'")

    tasks = {
        "academic": search_courses(query),
        "events": find_gymkhana_events(query),
        "locations": search_locations(query),
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    response = {"query": query, "results": {}, "errors": []}

    for source_name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            logger.warning(f"Source '{source_name}' failed: {result}")
            response["errors"].append({"source": source_name, "error": str(result)})
        else:
            entities = [e.model_dump(mode="json") for e in result[:limit]]
            response["results"][source_name] = entities

    return response


@mcp.tool()
def ping() -> str:
    """Health check."""
    return "pong"


if __name__ == "__main__":
    logger.info("Starting KGP Campus MCP Server over STDIO...")
    mcp.run(transport="stdio")