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


@pytest.mark.asyncio
async def test_find_societies_reads_json_dump():
    """find_societies should load all societies from data/societies_dump.json."""
    from kgp_mcp.server import find_societies

    socs = await find_societies()
    assert len(socs) >= 50
    assert all(isinstance(s, CampusEntity) for s in socs)
    koss = await find_societies(query="koss")
    assert len(koss) >= 1


@pytest.mark.asyncio
async def test_get_erp_timetable_reads_json_dump():
    """get_erp_timetable should return subject schedule, professors, room, and slot."""
    from kgp_mcp.server import get_erp_timetable

    res = await get_erp_timetable(subject_code="CH21202")
    assert len(res) == 1
    entity = res[0]
    assert entity.metadata["subject_code"] == "CH21202"
    assert "MASS TRANSFER" in entity.title.upper()
    assert "Slot:" in entity.description
    assert "Room:" in entity.description


def test_gymkhana_events_handles_null_dates():
    """GymkhanaAPIAdapter should gracefully handle null or malformed event_date."""
    from kgp_mcp.adapters.gymkhana_api_adapter import GymkhanaAPIAdapter

    adapter = GymkhanaAPIAdapter(is_event=True)
    entity = adapter.to_campus_entity({
        "id": "null-date-1",
        "title": "Prasthanam Selection",
        "description": "Dramatics selection",
        "is_event": True,
        "event_date": None,
        "created_at": "2026-07-30T19:54:40.844Z",
    })
    assert entity is not None
    assert entity.entity_type == "event"
    assert entity.metadata["event_date"] != ""