"""Location coordinates client.

Primary source: local JSON file (data/hall_coordinates.json).
Optional live source: OpenStreetMap Overpass API (disabled by default
because the free endpoint is unreliable and rate-limited).

Coordinates are static data (halls don't move), so hardcoding is a
production-grade approach for this use case.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Path to the local coordinates file
COORDINATES_FILE = Path(__file__).parent.parent.parent.parent / "data" / "hall_coordinates.json"


class OSMClient:
    """Provides hall coordinates. Loads from a local JSON file."""

    def __init__(self, use_live_osm: bool = False):
        self._cache: Optional[Dict[str, Dict]] = None
        self.use_live_osm = use_live_osm

    async def get_coordinates_map(self) -> Dict[str, Dict[str, float]]:
        """Return mapping: normalized hall name -> {latitude, longitude}."""
        if self._cache is not None:
            return self._cache

        self._cache = self._load_local_coordinates()
        logger.info(f"Loaded {len(self._cache)} hall coordinates from JSON.")
        return self._cache

    def _load_local_coordinates(self) -> Dict[str, Dict[str, float]]:
        """Load coordinates from data/hall_coordinates.json."""
        if not COORDINATES_FILE.exists():
            logger.warning(f"Coordinates file not found: {COORDINATES_FILE}")
            return {}

        try:
            with open(COORDINATES_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load coordinates: {e}")
            return {}

        result = {}
        for entry in raw.get("halls", []):
            name = entry.get("name", "")
            if not name:
                continue
            result[self._normalize(name)] = {
                "latitude": entry["latitude"],
                "longitude": entry["longitude"],
            }
        return result

    @staticmethod
    def _normalize(name: str) -> str:
        """Normalize hall name for matching."""
        n = name.lower()
        for suffix in [" hall of residence", " hall", " hostel", " of residence"]:
            n = n.replace(suffix, "")
        return n.strip()