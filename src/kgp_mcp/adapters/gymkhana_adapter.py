"""Gymkhana HTML Adapter: LLM-based extraction for JS-rendered pages."""
import logging
import re
import uuid
from typing import Dict, List

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.infrastructure.llm_extractor import LLMExtractor
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)


class GymkhanaHTMLAdapter(SourceAdapter):
    """Config-driven LLM adapter for any Gymkhana HTML page."""

    def __init__(
        self,
        url: str,
        entity_type: str,
        schema_description: str,
        example_json: str,
        ttl: int,
        tag: str,
    ):
        self.url = url
        self.entity_type = entity_type
        self.schema_description = schema_description
        self.example_json = example_json
        self.DEFAULT_TTL = ttl
        self.tag = tag
        self.extractor = LLMExtractor()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self) -> str:
        logger.info(f"[{self.tag}] Fetching {self.url}")
        async with httpx.AsyncClient() as client:
            r = await client.get(
                self.url,
                timeout=20.0,
                follow_redirects=True,
                headers={"User-Agent": "KGP-Campus-MCP/0.1 (educational)"},
            )
            r.raise_for_status()
            return r.text

    async def parse(self, raw: str) -> List[CampusEntity]:
        soup = BeautifulSoup(raw, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

        items = await self.extractor.extract(
            raw_text=text,
            schema_description=self.schema_description,
            example_json=self.example_json,
        )
        logger.info(f"[{self.tag}] Extracted {len(items)} items via LLM.")

        entities = []
        for item in items:
            e = self.to_campus_entity(item)   # ← uses ABC method
            if e:
                entities.append(e)
        return entities

    def to_campus_entity(self, item: Dict) -> CampusEntity | None:
        """ABC-compliant: convert one extracted item into a CampusEntity."""
        title = (
            item.get("name") or item.get("title")
            or item.get("event") or item.get("society") or ""
        ).strip()
        if not title:
            return None

        # Unique ID from UUID + title prefix (no index needed)
        uid = uuid.uuid4().hex[:8]
        safe_title = re.sub(r"[^a-zA-Z0-9]", "_", title[:30])
        safe_id = f"{self.tag}_{uid}_{safe_title}"[:80]

        desc_parts = []
        for k, v in item.items():
            if k in ("name", "title", "event", "society") or v is None:
                continue
            desc_parts.append(f"{k}: {v}")
        description = " | ".join(desc_parts)[:500]

        return CampusEntity(
            id=f"{self.tag}:{safe_id}",
            entity_type=self.entity_type,
            title=title[:200],
            description=description,
            source_url=self.url,
            metadata={"source_tag": self.tag, **item},
        )