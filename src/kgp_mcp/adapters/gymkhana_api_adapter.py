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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True)
    async def fetch(self) -> dict:
        all_posts = []
        page = 1
        total_pages = 1

        async with httpx.AsyncClient() as client:
            while page <= total_pages:
                params = {"page": page, "limit": 100}
                if self.is_event is not None:
                    params["is_event"] = str(self.is_event).lower()
                if self.category:
                    params["category"] = self.category

                r = await client.get(
                    self._source_url, params=params, timeout=15.0,
                    headers={"User-Agent": "KGP-Campus-MCP/0.1"},
                )
                r.raise_for_status()
                data = r.json()
                all_posts.extend(data.get("posts", []))

                pagination = data.get("pagination", {})
                total_pages = pagination.get("totalPages", 1)
                page += 1

        return {"posts": all_posts}

    async def parse(self, raw: dict) -> List[CampusEntity]:
        posts = raw.get("posts", [])
        entities = []
        for post in posts:
            try:
                e = self.to_campus_entity(post)
                if e:
                    entities.append(e)
            except Exception as err:
                logger.warning(f"[GymkhanaAPI] Skipping malformed post: {err}")
        logger.info(f"[GymkhanaAPI] Parsed {len(entities)} items.")
        return entities

    def to_campus_entity(self, post: dict) -> Optional[CampusEntity]:
        """ABC-compliant: convert one post dict into a CampusEntity without strict datetime parsing."""
        if not isinstance(post, dict):
            return None

        title = str(post.get("title") or "").strip()
        if not title:
            return None

        is_event = bool(post.get("is_event", False))
        if self.is_event is not None and is_event != self.is_event:
            return None

        entity_type = "event" if is_event else "notice"

        # Safe string fallback for dates (never calls datetime.fromisoformat)
        raw_event_date = post.get("event_date")
        raw_created_at = post.get("created_at")
        event_date_str = str(raw_event_date or raw_created_at or "").strip()

        meta = {
            "society": post.get("society_name"),
            "society_slug": post.get("society_slug"),
            "society_logo": post.get("society_logo"),
            "category": post.get("category_name"),
            "event_category": post.get("event_category"),
            "event_date": event_date_str,
            "event_mode": post.get("event_mode"),
            "reg_deadline": post.get("reg_deadline"),
            "apply_link": post.get("apply_link"),
            "contact_details": post.get("contact_details"),
            "is_featured": post.get("is_featured"),
            "created_at": post.get("created_at"),
            "image_url": post.get("image_url"),
        }
        meta = {k: v for k, v in meta.items() if v is not None}

        description = str(post.get("description") or "")
        description = " ".join(description.split())[:2000]

        raw_id = str(post.get("id") or uuid.uuid4().hex)[:8]

        return CampusEntity(
            id=f"gymkhana:{raw_id}",
            entity_type=entity_type,
            title=title[:200],
            description=description,
            source_url="https://gymkhana.iitkgp.ac.in/events",
            metadata=meta,
        )
