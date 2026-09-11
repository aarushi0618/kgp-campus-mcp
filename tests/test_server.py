"""Tests for the KGP Campus MCP server — Week 1."""
import pytest

from kgp_mcp.adapters.dummy_academic import DummyAcademicAdapter
from kgp_mcp.models.campus_entity import CampusEntity


@pytest.mark.asyncio
async def test_dummy_adapter_returns_entities():
    """The dummy adapter should return at least one CampusEntity."""
    adapter = DummyAcademicAdapter()
    entities = await adapter.get_entities()

    assert len(entities) >= 1
    assert all(isinstance(e, CampusEntity) for e in entities)
    assert all(e.entity_type == "course" for e in entities)


@pytest.mark.asyncio
async def test_dummy_adapter_entity_fields():
    """Entities should have required fields populated."""
    adapter = DummyAcademicAdapter()
    entities = await adapter.get_entities()

    for entity in entities:
        assert entity.id
        assert entity.title
        assert entity.source_url
        assert entity.last_updated is not None


@pytest.mark.asyncio
async def test_search_courses_filters_by_query():
    """search_courses should filter entities by the query string."""
    from kgp_mcp.server import search_courses

    results = await search_courses(query="machine")
    assert len(results) >= 1
    assert any("Machine Learning" in r.title for r in results)


@pytest.mark.asyncio
async def test_search_courses_no_match():
    """search_courses should return empty list for non-matching query."""
    from kgp_mcp.server import search_courses

    results = await search_courses(query="xyz_nonexistent_12345")
    assert results == []


def test_ping():
    """ping should return 'pong'."""
    from kgp_mcp.server import ping

    assert ping() == "pong"