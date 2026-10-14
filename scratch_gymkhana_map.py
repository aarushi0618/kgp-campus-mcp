"""Complete Gymkhana site map using Playwright (async).

Handles React/Next.js client-side rendering by using a real browser.
Discovers all pages via:
  - Rendered DOM link extraction
  - Hover-triggered dropdown menus
  - A seed list of known routes (fallback)
Also reports tables, PDFs, images, and text previews per page.
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
BASE_URL = "https://gymkhana.iitkgp.ac.in"
MAX_PAGES = 80
NAV_TIMEOUT_MS = 25000
RENDER_WAIT_MS = 2500     # time to let JS render after networkidle

# Seed routes to always try (dropdown sub-pages that may not appear as <a>)
SEED_ROUTES = [
    "/",
    "/events",
    "/societies",
    "/societies/social-cultural",
    "/societies/sports",
    "/societies/technology",
    "/societies/welfare",
    "/hall-of-fame",
    "/halloffame",
    "/halloffame/awards",
    "/halloffame/gc",
    "/halloffame/gc-results",
    "/halloffame/inter-iit",
    "/halloffame/interiit",
    "/governance",
    "/governance/council",
    "/governance/elections",
    "/governance/nominations",
    "/council",
    "/elections",
    "/nominations",
    "/more",
    "/about",
    "/contact",
]

# ----------------------------------------------------------------------
# Helper: is this an internal Gymkhana URL we care about?
# ----------------------------------------------------------------------
def is_internal(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc:
        return False
    # Keep only gymkhana domain
    return "gymkhana.iitkgp.ac.in" in p.netloc


def normalize(url: str) -> str:
    p = urlparse(url)
    # strip fragment and query, normalize trailing slash
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}"


# ----------------------------------------------------------------------
# Extract all data from a rendered page
# ----------------------------------------------------------------------
async def extract_page_data(page: Page, url: str) -> Dict:
    """Extract links, tables, PDFs, images, and text preview from a live page."""
    data: Dict = {
        "url": url,
        "title": "",
        "links": [],
        "pdfs": [],
        "tables": 0,
        "lists": 0,
        "images": 0,
        "text_preview": "",
    }
    try:
        data["title"] = await page.title() or ""
    except Exception:
        pass

    # -------- Internal links --------
    try:
        hrefs = await page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => e.getAttribute('href')).filter(Boolean)"
        )
        seen: Set[str] = set()
        for href in hrefs:
            full = urljoin(url, href)
            if is_internal(full):
                norm = normalize(full)
                if norm not in seen:
                    seen.add(norm)
                    data["links"].append(norm)
    except Exception:
        pass

    # -------- PDFs (any href ending in .pdf) --------
    try:
        pdf_hrefs = await page.eval_on_selector_all(
            "a[href$='.pdf'], a[href*='.pdf']",
            "els => els.map(e => e.href)"
        )
        data["pdfs"] = sorted(set(pdf_hrefs))
    except Exception:
        pass

    # -------- Structural counts --------
    try:
        data["tables"] = await page.locator("table").count()
        data["lists"] = await page.locator("ul, ol").count()
        data["images"] = await page.locator("img").count()
    except Exception:
        pass

    # -------- Text preview --------
    try:
        body_text = await page.eval_on_selector(
            "body", "el => el.innerText"
        )
        body_text = re.sub(r"\s+", " ", body_text or "").strip()
        data["text_preview"] = body_text[:400]
    except Exception:
        pass

    return data


# ----------------------------------------------------------------------
# Try to trigger hover-based dropdown menus so hidden links render
# ----------------------------------------------------------------------
async def trigger_hover_menus(page: Page):
    """Hover over nav items to reveal dropdown sub-links."""
    try:
        nav_items = page.locator("nav a, nav li, header a, header li")
        count = await nav_items.count()
        limit = min(count, 20)
        for i in range(limit):
            try:
                item = nav_items.nth(i)
                if await item.is_visible():
                    await item.hover(timeout=1000)
                    await page.wait_for_timeout(300)
            except Exception:
                continue
    except Exception:
        pass


# ----------------------------------------------------------------------
# Visit a single URL and return its data
# ----------------------------------------------------------------------
async def visit(page: Page, url: str) -> Dict | None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
    except PWTimeout:
        print(f"   ⏱  Timeout: {url}")
        return None
    except Exception as e:
        print(f"   ⚠️  Navigation error for {url}: {e}")
        return None

    # Give JS time to hydrate/render
    try:
        await page.wait_for_load_state("networkidle", timeout=RENDER_WAIT_MS)
    except PWTimeout:
        # Not fatal; continue with what we have
        pass

    await page.wait_for_timeout(800)
    await trigger_hover_menus(page)
    await page.wait_for_timeout(300)

    return await extract_page_data(page, url)


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
async def main():
    print("=" * 80)
    print("GYMKHANA SITE MAP — Playwright (async, JS-aware)")
    print("=" * 80)

    visited: Set[str] = set()
    queue: List[str] = []

    # Seed queue with known routes
    for r in SEED_ROUTES:
        queue.append(normalize(urljoin(BASE_URL, r)))

    results: Dict[str, Dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="KGP-Campus-MCP/0.1 (educational; +https://iitkgp.ac.in)"
        )
        page = await context.new_page()

        # Start crawl
        while queue and len(visited) < MAX_PAGES:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            print(f"\n[{len(visited):2d}] {url}")
            info = await visit(page, url)
            if info is None:
                continue

            results[url] = info
            print(f"     Title:   {info['title'][:90]}")
            print(f"     Links:   {len(info['links'])}   Tables: {info['tables']}   "
                  f"Lists: {info['lists']}   Images: {info['images']}   PDFs: {len(info['pdfs'])}")
            print(f"     Preview: {info['text_preview'][:160]}...")

            # Enqueue new internal links
            added = 0
            for link in info["links"]:
                if link not in visited and link not in queue:
                    queue.append(link)
                    added += 1
            if added:
                print(f"     → Queued {added} new links.")

        await browser.close()

    # ----------------------------------------------------------------------
    # Final report
    # ----------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"TOTAL PAGES CRAWLED: {len(results)}")
    print("=" * 80)

    # Save full report to JSON
    out_path = Path("gymkhana_sitemap.json")
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n💾 Full report saved to: {out_path.resolve()}")

    # Human-readable summary
    print("\n--- SITEMAP SUMMARY ---")
    for url in sorted(results):
        info = results[url]
        print(f"\n📄 {url}")
        print(f"   Title:   {info['title'][:100]}")
        print(f"   Tables:  {info['tables']}   Lists: {info['lists']}   "
              f"Images: {info['images']}   PDFs: {len(info['pdfs'])}")
        if info["pdfs"]:
            for pdf in info["pdfs"][:3]:
                print(f"     📎 {pdf}")
            if len(info["pdfs"]) > 3:
                print(f"     ... and {len(info['pdfs']) - 3} more PDFs")

    # Aggregate PDFs
    all_pdfs = sorted({p for i in results.values() for p in i["pdfs"]})
    if all_pdfs:
        print("\n--- ALL PDF RESOURCES ---")
        for pdf in all_pdfs:
            print(f"  📎 {pdf}")

    print("\n" + "=" * 80)
    print("Done. Paste the output (or gymkhana_sitemap.json) here so we can design")
    print("the config-driven Gymkhana adapter for your MCP server.")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())