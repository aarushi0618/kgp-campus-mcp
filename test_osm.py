
"""Tests for loading hall coordinates without requiring network access."""
import asyncio
import json
from pathlib import Path

from kgp_mcp.infrastructure.osm_client import OSMClient


def test_hall_coordinates_file_exists_and_is_valid():
    json_path = (
        Path(__file__).parent / "data" / "hall_coordinates.json"
    )

    assert json_path.exists(), f"Missing coordinate file: {json_path}"

    with json_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    halls = raw.get("halls", [])
    assert isinstance(halls, list), "'halls' must be a list"

    for hall in halls:
        assert hall.get("name"), f"Hall missing name: {hall}"
        assert isinstance(hall.get("latitude"), (int, float))
        assert isinstance(hall.get("longitude"), (int, float))


def test_osm_client_loads_coordinates():
    async def run_test():
        client = OSMClient()
        return await client.get_coordinates_map()

    coords = asyncio.run(run_test())

    assert isinstance(coords, dict)
