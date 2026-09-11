"""Dummy academic adapter — returns hardcoded data for Week 1 plumbing tests."""
from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity


class DummyAcademicAdapter(SourceAdapter):
    """Placeholder adapter that returns hardcoded course entities."""

    async def fetch(self) -> list[dict]:
        """Return hardcoded raw data — no network call yet."""
        return [
            {
                "code": "CS60050",
                "name": "Machine Learning",
                "dept": "CSE",
                "credits": 3.0,
            },
            {
                "code": "EE30001",
                "name": "Digital Signal Processing",
                "dept": "EE",
                "credits": 4.0,
            },
        ]

    async def parse(self, raw: list[dict]) -> list[CampusEntity]:
        """Convert raw dicts into CampusEntity objects."""
        return [self.to_campus_entity(item) for item in raw]

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        """Map a single raw dict to a CampusEntity."""
        return CampusEntity(
            id=f"course:{parsed['code'].lower()}",
            entity_type="course",
            title=parsed["name"],
            description=f"{parsed['name']} ({parsed['dept']})",
            source_url="https://example.iitkgp.ac.in/courses",
            metadata={
                "course_code": parsed["code"],
                "department": parsed["dept"],
                "credits": parsed["credits"],
            },
        )