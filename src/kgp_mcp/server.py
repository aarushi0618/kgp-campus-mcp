
import logging

from mcp.server.mcpserver import MCPServer

from kgp_mcp.adapters.dummy_academic import DummyAcademicAdapter
from kgp_mcp.models.campus_entity import CampusEntity

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP server using MCPServer
mcp = MCPServer("KGP Campus Intelligence")

# Instantiate the dummy adapter (will be replaced with real adapters later)
_academic_adapter = DummyAcademicAdapter()


@mcp.tool()
async def search_courses(query: str) -> list[CampusEntity]:
    """Search academic courses by keyword.

    Args:
        query: Free-text search term (course name or code).

    Returns:
        List of matching CampusEntity objects with entity_type='course'.
    """
    logger.info("search_courses called with query='%s'", query)

    # Fetch all entities from the adapter
    entities = await _academic_adapter.get_entities()

    # Filter by query (case-insensitive match on title or course_code)
    query_lower = query.lower()
    results = [
        entity
        for entity in entities
        if query_lower in entity.title.lower()
        or query_lower in entity.metadata.get("course_code", "").lower()
    ]

    logger.info("search_courses returned %d results", len(results))
    return results


@mcp.tool()
def ping() -> str:
    """Health check tool — returns 'pong' if the server is running."""
    return "pong"


if __name__ == "__main__":
    logger.info("Starting KGP Campus MCP Server over STDIO...")
    mcp.run(transport="stdio")