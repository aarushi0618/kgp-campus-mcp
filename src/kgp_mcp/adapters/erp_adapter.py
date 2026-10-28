"""ERP Adapter: Reads locally synced department timetables."""
import json
import logging
from pathlib import Path
from typing import List

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_FILE = str(ROOT_DIR / "data" / "erp_timetable_data.json")


class ERPAdapter(SourceAdapter):
    """Reads the JSON cache created by scripts/erp_full_sync.py."""
    DEFAULT_TTL = 86400

    async def fetch(self) -> dict:
        data_path = Path(DATA_FILE)
        if not data_path.exists():
            logger.warning(f"ERP data file not found: {DATA_FILE}")
            return {"department_timetables": []}

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read ERP data file {DATA_FILE}: {e}")
            return {"department_timetables": []}

    async def parse(self, raw: dict) -> List[CampusEntity]:
        entities = []
        for item in raw.get("department_timetables", []):
            try:
                entities.append(self.to_campus_entity(item))
            except Exception as e:
                logger.warning(f"Skipping malformed ERP timetable item: {e}")
        return entities

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        # Use .get() to prevent KeyError crashes
        subject = (parsed.get("subject_code") or "Unknown").strip()
        subject_name = (parsed.get("subject_name") or "").strip()
        profs = (parsed.get("professors") or "Not specified").strip()
        room = (parsed.get("room") or "Not specified").strip()
        slot = (parsed.get("slot") or "Not specified").strip()
        credits = str(parsed.get("credits") or "").strip()
        dept = (parsed.get("department") or subject[:2] or "Unknown").strip()

        title = f"{subject}: {subject_name} ({dept})" if subject_name else f"{subject} ({dept})"
        desc_parts = [
            f"Subject: {subject_name}" if subject_name else None,
            f"Slot: {slot}",
            f"Room: {room}",
            f"Profs: {profs}",
            f"Credits: {credits}" if credits else None,
        ]
        description = " | ".join(p for p in desc_parts if p)

        return CampusEntity(
            id=f"timetable:{dept}:{subject}",
            entity_type="course",
            title=title[:200],
            description=description,
            source_url="https://erp.iitkgp.ac.in/",
            metadata={
                "department": dept,
                "subject_code": subject,
                "subject_name": subject_name,
                "professors": profs,
                "slot": slot,
                "credits": credits,
                "room": room,
                "raw_text": parsed.get("raw_text", ""),
            },
        )
