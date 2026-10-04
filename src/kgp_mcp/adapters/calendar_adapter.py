"""Calendar Adapter: Fetches and parses IIT KGP academic calendar PDFs."""
import io
import logging
import re
from typing import List

import httpx
import pdfplumber
from tenacity import retry, stop_after_attempt, wait_exponential

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)

class CalendarAdapter(SourceAdapter):
    """Adapter for IIT KGP Academic Calendar (PDF based)."""

    def __init__(self, url: str = ""):
        self.url = url
        # Regex to find the date pattern (dd.mm.yyyy or dd.mm.yyyy to dd.mm.yyyy)
        self.date_pattern = re.compile(
            r"(?P<date>\d{2}\.\d{2}\.\d{4}(?:\s*to\s*\d{2}\.\d{2}\.\d{4})?)"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self) -> bytes:
        """Download the PDF asynchronously with retries."""
        if not self.url:
            raise ValueError("No URL provided for CalendarAdapter")
            
        logger.info(f"Fetching calendar PDF from {self.url}")
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url, timeout=30.0)
            response.raise_for_status()
            return response.content

    async def parse(self, raw: bytes) -> List[CampusEntity]:
        """Parse PDF bytes into CampusEntity objects."""
        entities = []
        
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                # Strategy 1: Extract tables
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table:
                            if row:
                                # Join all columns to handle both separated and merged text
                                combined_text = " ".join([str(cell) for cell in row if cell])
                                entity = self._parse_line(combined_text)
                                if entity:
                                    entities.append(entity)
                else:
                    # Strategy 2: Fallback to raw text
                    text = page.extract_text()
                    if text:
                        for line in text.split("\n"):
                            entity = self._parse_line(line)
                            if entity:
                                entities.append(entity)
                        
        logger.info(f"Parsed {len(entities)} calendar entries.")
        return entities

    def _parse_line(self, line: str) -> CampusEntity | None:
        """Extract event, date, and day from a single messy string."""
        line = line.replace("\n", " ").strip()
        if not line or "SI. No." in line or "EVENT" in line or len(line) < 15:
            return None

        # Find the date in the string
        match = self.date_pattern.search(line)
        if not match:
            return None

        date_str = match.group("date").strip()
        event_part = line[:match.start()].strip()
        day_part = line[match.end():].strip()

        # Clean up event name (remove leading numbers, (a), etc.)
        event = re.sub(r'^[\d\(\)a-z\.]+\s*', '', event_part)
        # Clean up day (remove trailing punctuation or non-day words if any)
        day = day_part.strip(" ()-")
        
        # Basic sanity check
        if not event or not day:
            return None

        return self.to_campus_entity({
            "date": date_str,
            "day": day,
            "event": event
        })

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        """Map parsed data to the standard CampusEntity schema."""
        safe_date = re.sub(r'[^a-zA-Z0-9]', '_', parsed['date'])
        
        return CampusEntity(
            id=f"calendar:{safe_date}",
            entity_type="calendar_entry",
            title=parsed["event"],
            description=f"{parsed['event']} on {parsed['date']} ({parsed['day']})",
            source_url=self.url or "local_pdf",
            metadata={
                "date": parsed["date"],
                "day": parsed["day"],
                "raw_event": parsed["event"]
            }
        )