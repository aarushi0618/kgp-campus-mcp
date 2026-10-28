import asyncio
import json
import os
from pathlib import Path
import sys
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT_DIR / "data" / "societies_dump.json"

KNOWN_CATEGORIES = {
    "technology": "Technology",
    "social & cultural": "Social & Cultural",
    "students' welfare": "Students' Welfare",
    "sports & games": "Sports & Games",
    "department": "Department",
    "indepedent": "Independent",
    "independent": "Independent",
    "cell": "Cell",
    "regional": "Regional",
    "welfare": "Students' Welfare",
}


def _extract_cards_from_html(html: str, existing: list[dict], default_category: str = "General") -> None:
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "")
        if href.startswith("/societies/") and href != "/societies":
            slug = href.split("/")[-1].strip()
            if not slug or any(s.get("slug") == slug for s in existing):
                continue

            card_text_lines = [
                line.strip()
                for line in a_tag.get_text("\n", strip=True).split("\n")
                if line.strip() and line.strip().lower() not in {"explore", "view details", "read more"}
            ]
            if not card_text_lines:
                continue

            first_lower = card_text_lines[0].lower()
            if len(card_text_lines) >= 2 and first_lower in KNOWN_CATEGORIES:
                category = KNOWN_CATEGORIES[first_lower]
                name = card_text_lines[1]
                description = " ".join(card_text_lines[2:]) if len(card_text_lines) > 2 else ""
            else:
                category = default_category
                name = card_text_lines[0]
                description = " ".join(card_text_lines[1:]) if len(card_text_lines) > 1 else ""

            existing.append({
                "name": name,
                "category": category,
                "description": description,
                "slug": slug,
            })


async def main():
    print("--- 🚀 Scraping Gymkhana Societies (with scrolling) ---")
    societies: list[dict] = []
    api_societies: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        await page.goto("https://gymkhana.iitkgp.ac.in/societies", wait_until="networkidle", timeout=30000)

        # Click the 'All' tab just in case it defaulted to another category
        try:
            await page.locator("button:has-text('All')").first.click(timeout=2000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Also capture structured societies from the backing API inside the page context
        try:
            api_data = await page.evaluate(
                """async () => {
                    const res = await fetch('/api/v1/societies?status=active&page=1&limit=200');
                    return await res.json();
                }"""
            )
            for item in api_data.get("societies", []):
                slug = str(item.get("slug") or "").strip()
                if slug:
                    raw_cat = str(item.get("category_name") or "General").strip()
                    norm_cat = KNOWN_CATEGORIES.get(raw_cat.lower(), raw_cat)
                    api_societies[slug] = {
                        "name": str(item.get("name") or "").strip(),
                        "category": norm_cat,
                        "description": str(item.get("description") or item.get("one_liner") or "").strip(),
                        "slug": slug,
                    }
        except Exception:
            pass

        # Scroll the page to the bottom 5 times with await page.wait_for_timeout(1500) across pages
        page_num = 1
        while True:
            for _ in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1500)

            html = await page.content()
            _extract_cards_from_html(html, societies)

            try:
                next_btn = page.locator("button:has-text('Next')").first
                if await next_btn.count() > 0 and await next_btn.is_enabled():
                    await next_btn.click(timeout=3000)
                    await page.wait_for_timeout(1500)
                    page_num += 1
                    if page_num > 10:
                        break
                else:
                    break
            except Exception:
                break

        await browser.close()

    merged_by_slug = {}
    for s in societies:
        slug = s.get("slug", "")
        api_entry = api_societies.get(slug, {})
        cat = s.get("category", "General")
        if cat == "General" and api_entry.get("category"):
            cat = api_entry["category"]
        merged_by_slug[slug] = {
            "name": api_entry.get("name") or s.get("name", "Unknown Society"),
            "category": cat,
            "description": api_entry.get("description") or s.get("description", ""),
            "slug": slug,
        }

    for slug, api_soc in api_societies.items():
        if slug not in merged_by_slug and api_soc.get("name"):
            merged_by_slug[slug] = api_soc

    final_societies = list(merged_by_slug.values())

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_societies, f, indent=2, ensure_ascii=False)

    print(f"✅ Successfully saved {len(final_societies)} societies to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
