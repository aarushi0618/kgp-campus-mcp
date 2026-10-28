"""Academic Adapter: Loads IIT KGP courses from local JSON dumps or scrapes using Playwright."""
import json
import logging
import os
from pathlib import Path
import re
from typing import List
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from kgp_mcp.adapters.base import SourceAdapter
from kgp_mcp.models.campus_entity import CampusEntity

logger = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
DUMP_FILE = str(DATA_DIR / "courses_dump.json")
ERP_FALLBACK_FILE = str(DATA_DIR / "erp_timetable_data.json")


class AcademicAdapter(SourceAdapter):
    DEFAULT_TTL = 86400

    def __init__(self):
        self.base_url = "https://www.iitkgp.ac.in/department/{}/courses"
        self.departments = ["AE", "AG", "AR", "BT", "CH", "CE", "CS", "EE", "EC", "GG", "HS", "MA", "ME", "MT", "MI", "NA", "PH"]

    async def fetch(self) -> list[dict]:
        if os.path.exists(DUMP_FILE):
            try:
                with open(DUMP_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data:
                        return data
            except Exception as e:
                logger.warning(f"Failed to read {DUMP_FILE}: {e}")

        # Fast offline fallback: derive academic courses from erp_timetable_data.json if courses_dump.json is empty
        if os.path.exists(ERP_FALLBACK_FILE):
            try:
                with open(ERP_FALLBACK_FILE, "r", encoding="utf-8") as f:
                    erp_data = json.load(f)
                timetables = erp_data.get("department_timetables", [])
                if timetables:
                    courses = []
                    for item in timetables:
                        code = (item.get("subject_code") or "").strip()
                        name = (item.get("subject_name") or "").strip().title()
                        dept = (item.get("department") or code[:2] or "").strip()
                        if code and name:
                            courses.append({
                                "id": f"course:{code.lower()}",
                                "entity_type": "course",
                                "title": name[:200],
                                "description": f"[{dept}] {code} - {name[:200]}",
                                "source_url": f"https://www.iitkgp.ac.in/department/{dept}/courses",
                                "metadata": {
                                    "course_code": code,
                                    "department": dept,
                                    "credits": item.get("credits", ""),
                                    "professors": item.get("professors", ""),
                                },
                            })
                    if courses:
                        return courses
            except Exception as e:
                logger.warning(f"Failed to read ERP fallback for courses: {e}")

        results = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(ignore_https_errors=True)

            for dept in self.departments:
                url = self.base_url.format(dept)
                logger.info(f"Fetching {url}...")
                page = await context.new_page()
                try:
                    await page.goto(url, wait_until="networkidle", timeout=30000)
                    html = await page.content()
                    results.append({"dept": dept, "url": url, "html": html})
                except Exception:
                    results.append({"dept": dept, "url": url, "html": ""})
                finally:
                    await page.close()
            await browser.close()
        return results

    async def parse(self, raw: list[dict]) -> List[CampusEntity]:
        if raw and isinstance(raw[0], dict) and "entity_type" in raw[0]:
            return [CampusEntity(**item) for item in raw]

        entities = []
        for page in raw:
            if not page.get("html"):
                continue

            soup = BeautifulSoup(page["html"], "html.parser")
            dept = page["dept"]
            url = page["url"]

            text = soup.get_text("\n", strip=True)
            lines = text.split("\n")

            for i, line in enumerate(lines):
                match = re.search(r"\b([A-Z]{2}\d{5})\b", line)
                if match:
                    code = match.group(1)
                    title = line.replace(code, "").strip()
                    if not title and i + 1 < len(lines):
                        title = lines[i + 1]
                    if not title:
                        title = "Unknown Title"

                    entities.append(CampusEntity(
                        id=f"course:{code.lower()}",
                        entity_type="course",
                        title=title[:200],
                        description=f"[{dept}] {code} - {title[:200]}",
                        source_url=url,
                        metadata={"course_code": code, "department": dept},
                    ))

        return list({e.id: e for e in entities}.values())

    def to_campus_entity(self, parsed: dict) -> CampusEntity:
        return CampusEntity(**parsed)