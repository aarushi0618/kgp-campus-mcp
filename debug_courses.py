"""Academic Adapter: Scrapes IIT KGP courses using Playwright."""
import asyncio
import json
import logging
import os
import re
from typing import List

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)

DUMP_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "courses_dump.json")

class AcademicAdapter(SourceAdapter):
    """Scrapes courses across multiple departments using Playwright."""

    DEFAULT_TTL = 86400

    def __init__(self):
        self.base_url = "https://www.iitkgp.ac.in/department/{}/courses"
        self.departments = ["AE", "AG", "AR", "BT", "CH", "CE", "CS", "EE", "EC", "GG", "HS", "MA", "ME", "MT", "MI", "NA", "PH"]

    async def fetch(self) -> list[dict]:
        # 1. FAST PATH: Load from cache
        if os.path.exists(DUMP_FILE):
            logger.info(f"Loading courses from local cache: {DUMP_FILE}")
            with open(DUMP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)

        # 2. SLOW PATH: Scrape with Playwright
        logger.info("Fetching courses live via Playwright...")
        results = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                ignore_https_errors=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            for dept in self.departments:
                url = self.base_url.format(dept)
                logger.info(f"Fetching {url}...")
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    html = await page.content()
                    results.append({"dept": dept, "url": url, "html": html})
                except Exception as e:
                    logger.warning(f"Failed to fetch {dept}: {e}")
                    results.append({"dept": dept, "url": url, "html": ""})
                finally:
                    await page.close()
                    
            await browser.close()
            
        return results

    async def parse(self, raw: list[dict]) -> List[CampusEntity]:
        # Handle loading directly from JSON
        if raw and isinstance(raw[0], dict) and "entity_type" in raw[0]:
            return [CampusEntity(**item) for item in raw]

        entities = []
        for page in raw:
            if not page.get("html"):
                continue
                
            soup = BeautifulSoup(page["html"], "html.parser")
            dept = page["dept"]
            url = page["url"]
            
            # Strategy: Find all tables and extract course rows
            tables = soup.find_all("table")
            for table in tables:
                for row in table.find_all("tr"):
                    cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
                    # Match a valid course code in the first column
                    if len(cells) >= 2 and re.match(r"^[A-Z]{2}\d{5}$", cells[0]): 
                        entities.append(self.to_campus_entity({
                            "cells": cells, 
                            "dept": dept, 
                            "url": url
                        }))
                        
        logger.info(f"Parsed {len(entities)} courses.")
        return entities

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        cells = parsed["cells"]
        code = cells[0]
        title = cells[1] if len(cells) > 1 else "Unknown Title"
        
        return CampusEntity(
            id=f"course:{code.lower()}",
            entity_type="course",
            title=title,
            description=f"[{parsed['dept']}] {code} - {title}",
            source_url=parsed["url"],
            metadata={
                "course_code": code, 
                "department": parsed["dept"], 
                "raw_cells": cells
            }
        )