"""Tests for the unified search_all tool."""
import pytest
from unittest.mock import patch

from kgp_mcp.models.campus_entity import CampusEntity
from kgp_mcp.server import search_all


@pytest.mark.asyncio
async def test_search_all_graceful_degradation():
    """
    Test that search_all returns partial results if one source fails.
    """
    # Mock the individual tools, returning proper CampusEntity objects
    async def mock_courses(q):
        return [CampusEntity(
            id="course:123",
            entity_type="course",
            title="Mock Course",
            source_url="http://test"
        )]

    async def mock_events(q):
        raise Exception("API Down")  # Simulate failure

    async def mock_locs(q, facility_type=None):
        return [CampusEntity(
            id="loc:456",
            entity_type="location",
            title="Mock Hall",
            source_url="http://test"
        )]

    # Patch them in the server module
    with patch("kgp_mcp.server.search_courses", side_effect=mock_courses), \
         patch("kgp_mcp.server.find_gymkhana_events", side_effect=mock_events), \
         patch("kgp_mcp.server.search_locations", side_effect=mock_locs):
        
        result = await search_all("test")

        # Assertions for successes
        assert result["query"] == "test"
        assert "academic" in result["results"]
        assert "locations" in result["results"]
        assert len(result["results"]["academic"]) == 1
        assert result["results"]["academic"][0]["title"] == "Mock Course"
        
        # Assertions for graceful degradation
        assert "events" not in result["results"]
        assert len(result["errors"]) == 1
        assert result["errors"][0]["source"] == "events"
        assert "API Down" in result["errors"][0]["error"]