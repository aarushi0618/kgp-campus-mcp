"""Gymkhana API Adapter: uses /api/v1/posts JSON endpoint directly.

No LLM. Fast, free, structured.
"""
import logging
import uuid
from typing import List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)

GYMKHANA_API = "https://gymkhana.iitkgp.ac.in/api/v1"


class GymkhanaAPIAdapter(SourceAdapter):
    """Adapter for Gymkhana JSON API posts (events, notices)."""

    DEFAULT_TTL = 3600  # 1 hour

    def __init__(
        self,
        is_event: Optional[bool] = None,
        category: Optional[str] = None,
        limit: int = 50,
    ):
        self.is_event = is_event
        self.category = category
        self.limit = limit
        self._source_url = f"{GYMKHANA_API}/posts"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def fetch(self) -> dict:
        params = {"page": 1, "limit": self.limit}
        if self.is_event is not None:
            params["is_event"] = str(self.is_event).lower()
        if self.category:
            params["category"] = self.category

        logger.info(f"[GymkhanaAPI] GET {self._source_url} params={params}")
        async with httpx.AsyncClient() as client:
            r = await client.get(
                self._source_url,
                params=params,
                timeout=15.0,
                headers={"User-Agent": "KGP-Campus-MCP/0.1 (educational)"},
            )
            r.raise_for_status()
            return r.json()

    async def parse(self, raw: dict) -> List[CampusEntity]:
        posts = raw.get("posts", [])
        entities = []
        for post in posts:
            e = self.to_campus_entity(post)   # ← uses ABC method
            if e:
                entities.append(e)
        logger.info(f"[GymkhanaAPI] Parsed {len(entities)} items.")
        return entities

    def to_campus_entity(self, post: dict) -> Optional[CampusEntity]:
        """ABC-compliant: convert one post dict into a CampusEntity."""
        title = (post.get("title") or "").strip()
        if not title:
            return None

        is_event = post.get("is_event", False)
        entity_type = "event" if is_event else "notice"

        meta = {
            "society": post.get("society_name"),
            "society_slug": post.get("society_slug"),
            "society_logo": post.get("society_logo"),
            "category": post.get("category_name"),
            "event_category": post.get("event_category"),
            "event_date": post.get("event_date"),
            "event_mode": post.get("event_mode"),
            "reg_deadline": post.get("reg_deadline"),
            "apply_link": post.get("apply_link"),
            "contact_details": post.get("contact_details"),
            "is_featured": post.get("is_featured"),
            "created_at": post.get("created_at"),
            "image_url": post.get("image_url"),
        }
        meta = {k: v for k, v in meta.items() if v is not None}

        description = (post.get("description") or "")
        description = " ".join(description.split())[:2000]

        # Use UUID from post ID or fallback to a random one
        raw_id = str(post.get("id") or uuid.uuid4().hex)[:8]

        return CampusEntity(
            id=f"gymkhana:{raw_id}",
            entity_type=entity_type,
            title=title[:200],
            description=description,
            source_url="https://gymkhana.iitkgp.ac.in/events",
            metadata=meta,
        )