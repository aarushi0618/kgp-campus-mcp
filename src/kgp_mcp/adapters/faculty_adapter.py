"""Faculty Adapter: Scrapes ALL departments and caches to a JSON file for speed."""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import List

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)

# Path to save the FINAL parsed data
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DUMP_FILE = str(ROOT_DIR / "data" / "faculty_parsed_cache.json")

class FacultyAdapter(SourceAdapter):
    DEFAULT_TTL = 86400

    def __init__(self):
        self.seed_url = "https://www.iitkgp.ac.in/department/AE"
        self.departments = {}

    async def get_entities(self) -> List[CampusEntity]:
        """Override the base method to load parsed models directly from disk."""
        # 1. FAST PATH: Load fully parsed CampusEntity objects instantly
        if os.path.exists(DUMP_FILE):
            logger.info(f"Loading parsed faculty from cache: {DUMP_FILE}")
            with open(DUMP_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [CampusEntity(**item) for item in data]

        # 2. SLOW PATH: Scrape and parse
        logger.info("No local cache found. Scraping all departments (takes ~40s)...")
        raw = await self.fetch()
        entities = await self.parse(raw)
        
        # 3. Save the parsed Pydantic models to disk
        os.makedirs(os.path.dirname(DUMP_FILE), exist_ok=True)
        with open(DUMP_FILE, "w", encoding="utf-8") as f:
            json.dump([e.model_dump(mode="json") for e in entities], f)
        logger.info(f"Saved {len(entities)} parsed faculty to {DUMP_FILE}")
        
        return entities

    async def fetch(self) -> list[dict]:
        """Scrape the raw HTML (only runs if cache is missing)."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)
            
            self.departments = await self._discover_departments(context)
            results = []
            dept_items = list(self.departments.items())
            batch_size = 4
            
            for i in range(0, len(dept_items), batch_size):
                batch = dept_items[i:i+batch_size]
                tasks = [self._fetch_dept(context, code, name) for code, name in batch]
                results.extend(await asyncio.gather(*tasks))
                await asyncio.sleep(0.5) 

            await browser.close()
            return results

    async def _discover_departments(self, context) -> dict:
        page = await context.new_page()
        depts = {}
        try:
            await page.goto(self.seed_url, wait_until="domcontentloaded", timeout=30000)
            links = await page.eval_on_selector_all(
                "a[href*='/department/']",
                "els => els.map(e => ({href: e.getAttribute('href'), text: e.innerText.trim()}))"
            )
            for link in links:
                match = re.search(r"/department/([A-Z]{2})", link["href"])
                if match and link["text"]:
                    depts[match.group(1)] = link["text"]
        except Exception:
            pass
        finally:
            await page.close()
            
        fallback = {"AE": "Aerospace Engineering", "CS": "Computer Science", "ME": "Mechanical", "EE": "Electrical"}
        for k, v in fallback.items():
            if k not in depts: depts[k] = v
        return depts

    async def _fetch_dept(self, context, dept_code: str, dept_name: str) -> dict:
        url = f"https://www.iitkgp.ac.in/department/{dept_code}"
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                await page.wait_for_selector("select#show_people_former_staff", timeout=5000)
                await page.select_option("select#show_people_former_staff", "faculty")
                await page.wait_for_timeout(4000) 
            except Exception:
                pass 
            html = await page.content()
            return {"dept_code": dept_code, "dept_name": dept_name, "url": url, "html": html}
        except Exception:
            return {"dept_code": dept_code, "dept_name": dept_name, "url": url, "html": ""}
        finally:
            await page.close()

    async def parse(self, raw: list[dict]) -> List[CampusEntity]:
        """Parse raw HTML into Pydantic models."""
        entities = []
        for page in raw:
            if not page["html"]: continue
            soup = BeautifulSoup(page["html"], "html.parser")
            dept_code = page["dept_code"]
            dept_name = page["dept_name"]
            url = page["url"]
            
            for div in soup.find_all("div"):
                text = div.get_text("\n", strip=True)
                if "@" in text and len(text) < 1000:
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    if not lines: continue
                    name = lines[0]
                    if name.lower() in ["faculty", "faculty members", "people", "view profile", "email"]: continue
                    if "message from" in name.lower() or "head of the" in name.lower(): continue
                        
                    email = "Not found"
                    research_area = "Not specified"
                    designation = "Faculty"
                    has_prof_title = False
                    
                    for i, line in enumerate(lines):
                        if "@" in line and " " not in line:
                            email = line
                        elif "Professor" in line or "Head" in line:
                            designation = line
                            has_prof_title = True
                        elif "Research Area" in line:
                            match = re.search(r"Research Area\(s\)\s*:\s*(.*)", line, re.IGNORECASE)
                            if match and match.group(1).strip():
                                research_area = match.group(1).strip()
                            elif i + 1 < len(lines):
                                research_area = lines[i+1].strip()
                    
                    if any(prefix in email.lower() for prefix in ["head@", "dean@", "chairperson@", "office@", "hod@"]): continue
                    if not has_prof_title and "Prof" not in text and "Dr" not in text: continue
                    if any(e.metadata.get("email") == email for e in entities): continue

                    entities.append(self.to_campus_entity({
                        "name": name, "email": email, "designation": designation,
                        "research_area": research_area, "dept_code": dept_code, 
                        "dept_name": dept_name, "url": url
                    }))
        return entities

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        safe_name = re.sub(r'[^a-zA-Z0-9]', '_', parsed['name'].lower())
        return CampusEntity(
            id=f"faculty:{safe_name}_{parsed['dept_code']}",
            entity_type="faculty",
            title=parsed["name"],
            description=f"Email: {parsed['email']} | Research: {parsed['research_area']}",
            source_url=parsed["url"],
            metadata={
                "department_code": parsed["dept_code"],
                "department_name": parsed["dept_name"],
                "email": parsed["email"],
                "designation": parsed["designation"],
                "research_area": parsed["research_area"]
            }
        )