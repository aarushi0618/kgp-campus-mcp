"""Tests for Gymkhana adapters."""
from kgp_mcp.adapters.gymkhana_api_adapter import GymkhanaAPIAdapter
from kgp_mcp.adapters.gymkhana_adapter import GymkhanaHTMLAdapter


def test_api_adapter_to_entity_event():
    a = GymkhanaAPIAdapter(is_event=True)
    e = a.to_campus_entity({
        "id": "abc12345",
        "title": "Hackathon",
        "description": "A test hackathon",
        "is_event": True,
        "society_name": "KOSS",
        "category_name": "Technology",
        "event_date": "2026-10-10T14:00:00Z",
    })
    assert e is not None
    assert e.entity_type == "event"
    assert e.title == "Hackathon"
    assert e.metadata["society"] == "KOSS"
    assert e.metadata["category"] == "Technology"


def test_api_adapter_to_entity_notice():
    a = GymkhanaAPIAdapter(is_event=False)
    e = a.to_campus_entity({
        "id": "xyz67890",
        "title": "Library Pass",
        "description": "New pass system",
        "is_event": False,
    })
    assert e is not None
    assert e.entity_type == "notice"


def test_api_adapter_skips_empty_title():
    a = GymkhanaAPIAdapter()
    assert a.to_campus_entity({"id": "1", "title": ""}) is None
    assert a.to_campus_entity({"id": "2"}) is None


def test_llm_adapter_to_entity_from_name():
    a = GymkhanaHTMLAdapter(
        url="http://test", entity_type="location",
        schema_description="test", example_json='{"name": "X"}',
        ttl=3600, tag="test",
    )
    e = a.to_campus_entity({"name": "KOSS", "category": "Independent"})
    assert e is not None
    assert "KOSS" in e.title
    assert e.metadata["source_tag"] == "test"


def test_llm_adapter_skips_empty():
    a = GymkhanaHTMLAdapter(
        url="http://test", entity_type="location",
        schema_description="test", example_json='{"name": "X"}',
        ttl=3600, tag="test",
    )
    assert a.to_campus_entity({}) is None