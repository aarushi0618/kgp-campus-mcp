"""Location Adapter: Scrapes HMC warden page + enriches with OSM coordinates."""
import logging
import re
from typing import Dict, List, Optional

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.infrastructure.osm_client import OSMClient
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)

# Matches hall names ending in "Hall of Residence"
HALL_PATTERN = re.compile(
    r"([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,6}\s+Hall of Residence)"
)

# Warden name: "Prof. First Last" — MAX 3 words (avoids swallowing departments)
PROF_PATTERN = re.compile(r"Prof\.\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2}")

# Role markers
ROLE_PATTERN = re.compile(r"(ASSISTANT\s+WARDEN(?:\s*\(WELFARE\))?|WARDEN)")

# Keywords that signal the START of a department name (used to trim overgreedy matches)
DEPT_KEYWORDS = {
    "Agricultural", "Engineering", "Science", "Sciences", "Technology",
    "School", "Department", "Centre", "Center", "College", "Institute",
    "Computer", "Chemical", "Civil", "Electrical", "Electronics",
    "Mechanical", "Metallurgical", "Mining", "Ocean", "Industrial",
    "Physics", "Chemistry", "Mathematics", "Humanities", "Geology",
    "Geophysics", "Economics", "Management", "Architecture", "Aerospace",
    "Law", "Education", "Rubber", "Nano", "Materials", "Medical",
    "Petroleum", "Naval", "Biotechnology", "Rehabilitation", "Energy",
    "Earth", "Atmospheric",
    # Proper names that prefix department titles
    "Ranbir", "Vinod", "Rajiv", "Gandhi", "Deysarkar", "Rekhi", "Dr", "Gupta",
}


class LocationAdapter(SourceAdapter):
    """Adapter for IIT KGP halls: HMC scrapes names/wardens + OSM for coordinates."""

    DEFAULT_TTL = 604800  # 7 days — static data

    def __init__(self, url: str, osm_client: Optional[OSMClient] = None):
        self.url = url
        self.osm_client = osm_client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self) -> str:
        logger.info(f"Fetching HMC page from {self.url}")
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url, timeout=20.0, follow_redirects=True)
            response.raise_for_status()
            return response.text

    async def parse(self, raw: str) -> List[CampusEntity]:
        soup = BeautifulSoup(raw, "html.parser")
        halls_data = self._extract_halls_from_soup(soup)
        logger.info(f"Extracted {len(halls_data)} halls from HMC page.")

        coords_map: Dict[str, Dict] = {}
        if self.osm_client is not None:
            try:
                coords_map = await self.osm_client.get_coordinates_map()
                logger.info(f"Fetched coordinates for {len(coords_map)} halls from OSM.")
            except Exception as e:
                logger.warning(f"OSM fetch failed, proceeding without coordinates: {e}")

        entities = []
        for hall in halls_data:
            normalized = self._normalize(hall["name"])
            coords = coords_map.get(normalized, {})
            hall.update(coords)
            entities.append(self.to_campus_entity(hall))
        return entities

    def _extract_halls_from_soup(self, soup: BeautifulSoup) -> List[Dict]:
        main = soup.find("main") or soup.find("article") or soup.body
        if main is None:
            logger.warning("Could not find main content in HMC page.")
            return []

        for tag in main.find_all(["nav", "footer", "script", "style", "aside", "header", "form"]):
            tag.decompose()

        text = main.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        matches = list(HALL_PATTERN.finditer(text))
        logger.info(f"Regex found {len(matches)} 'Hall of Residence' matches.")

        halls = []
        seen = set()

        for i, match in enumerate(matches):
            hall_name = self._clean_hall_name(match.group(1).strip())
            if not (10 <= len(hall_name) <= 100):
                continue
            if hall_name in seen:
                continue
            seen.add(hall_name)

            content_start = match.end()
            content_end = matches[i + 1].start() if (i + 1) < len(matches) else len(text)
            warden_text = text[content_start:content_end]

            wardens = self._extract_wardens_from_text(warden_text)
            primary = next((w for w in wardens if w["role"] == "WARDEN"), None)
            assistants = [w for w in wardens if "ASSISTANT" in w["role"]]

            # Dedupe assistants
            seen_assistants = set()
            unique_assistants = []
            for a in assistants:
                if a["name"] not in seen_assistants:
                    seen_assistants.add(a["name"])
                    unique_assistants.append(a)

            halls.append({
                "name": hall_name,
                "facility_type": "hostel",
                "warden": primary["name"] if primary else None,
                "warden_department": primary["department"] if primary else None,
                "assistant_wardens": "; ".join(
                    f"{a['name']} ({a['department']})" for a in unique_assistants
                ) or None,
                "warden_count": len(wardens),
            })
        return halls

    @staticmethod
    def _clean_hall_name(name: str) -> str:
        for prefix in [
            "Assistant Warden. ", "Assistant Warden ",
            "Warden. ", "Warden ",
        ]:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        return name

    def _extract_wardens_from_text(self, text: str) -> List[Dict[str, str]]:
        """Extract warden entries. Trims trailing department words that sneak into prof names."""
        results = []
        prof_matches = list(PROF_PATTERN.finditer(text))

        for i, prof_match in enumerate(prof_matches):
            raw_name = prof_match.group().strip()
            start = prof_match.end()
            end = prof_matches[i + 1].start() if (i + 1) < len(prof_matches) else len(text)
            chunk = text[start:end]

            role_match = ROLE_PATTERN.search(chunk)
            if role_match:
                role = role_match.group().strip()
                department_raw = chunk[:role_match.start()].strip()
            else:
                role = "UNKNOWN"
                department_raw = chunk.strip()

            # Trim trailing department keywords from the prof name
            name_words = raw_name.split()
            trimmed: List[str] = []
            while len(name_words) > 3 and name_words[-1] in DEPT_KEYWORDS:
                trimmed.insert(0, name_words.pop())
            clean_name = " ".join(name_words)

            # Prepend trimmed words to department (reconstruct full name)
            department = " ".join(trimmed + [department_raw]) if trimmed else department_raw
            department = re.sub(r"\s+", " ", department).strip()
            department = re.sub(r"^(of|and|in|for)\s+", "", department, flags=re.IGNORECASE)

            results.append({
                "name": clean_name,
                "role": role,
                "department": department,
            })
        return results

    @staticmethod
    def _normalize(name: str) -> str:
        n = name.lower()
        for suffix in [" hall of residence", " hall", " hostel", " of residence"]:
            n = n.replace(suffix, "")
        return n.strip()

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        safe_name = re.sub(r"[^a-zA-Z0-9]", "_", parsed["name"].lower())

        metadata = {
            "facility_type": parsed.get("facility_type", "hostel"),
            "building_name": parsed["name"],
        }
        for field in [
            "warden", "warden_department", "assistant_wardens",
            "warden_count", "latitude", "longitude",
        ]:
            if parsed.get(field) is not None:
                metadata[field] = parsed[field]

        desc_parts = [parsed["name"]]
        if parsed.get("warden"):
            desc_parts.append(f"Warden: {parsed['warden']}")
        if parsed.get("warden_department"):
            desc_parts.append(f"({parsed['warden_department']})")
        if parsed.get("latitude") and parsed.get("longitude"):
            desc_parts.append(
                f"Coordinates: {parsed['latitude']:.4f}, {parsed['longitude']:.4f}"
            )

        return CampusEntity(
            id=f"location:{safe_name}",
            entity_type="location",
            title=parsed["name"],
            description=" | ".join(desc_parts),
            source_url=self.url,
            metadata=metadata,
        )