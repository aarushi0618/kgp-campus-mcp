"""Core CampusEntity schema — all domain services normalize to this shape."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class TimetableSlot(BaseModel):
    """A single timetable slot within a course."""
    day: Literal["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    start_time: str = Field(..., description="HH:MM format, e.g. 10:00")
    end_time: str = Field(..., description="HH:MM format, e.g. 10:55")
    room: Optional[str] = None


class CampusEntity(BaseModel):
    """Normalized campus entity — the common shape all adapters return."""
    id: str = Field(..., description="Globally unique ID, e.g. 'course:cs60050'")
    entity_type: Literal[
        "course", "event", "location", "hall", "notice", "calendar_entry"
    ] = Field(..., description="Discriminator for entity subtype")
    title: str = Field(..., description="Human-readable title")
    description: Optional[str] = Field(None, description="Free-text description")
    source_url: str = Field(..., description="Origin URL scraped/parsed from")
    last_updated: datetime = Field(
        default_factory=datetime.now,
        description="ISO 8601 timestamp of last fetch",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Entity-type-specific extension fields",
    )
    