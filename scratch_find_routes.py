"""Find hidden SPA routes by intercepting navigation + clicking nav items."""
import asyncio
import json
import re
from pathlib import Path
from typing import Set

from playwright.async_api import async_playwright

BASE = "https://gymkhana.iitkgp.ac.in"

# Extended candidate routes to probe directly
CANDIDATE_ROUTES = [
    # Hall of Fame variants
    "/hall-of-fame", "/halloffame", "/hall_of_fame",
    "/halloffame/awards", "/halloffame/gc", "/halloffame/gc-results",
    "/halloffame/interiit", "/halloffame/inter-iit",
    "/awards", "/gc", "/gc-results", "/interiit", "/inter-iit",
    "/achievements", "/honours",
    # Governance variants
    "/governance", "/governance/council", "/governance/elections",
    "/governance/nominations", "/council", "/elections", "/nominations",
    "/council-members", "/office-bearers",
]


async def probe_route(page, url: str) -> dict:
    """Load a URL and return its status (works/404)."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        status = response.status if response else 0
        await page.wait_for_timeout(800)
        title = await page.title()
        body = (await page.eval_on_selector("body", "el => el.innerText"))[:200]
        is_404 = "404" in title or "404" in body or "OOPS" in body.upper()
        return {"url": url, "status": status, "title": title, "is_404": is_404}
    except Exception as e:
        return {"url": url, "status": "error", "title": str(e)[:100], "is_404": True}


async def main():
    print("=" * 80)
    print("GYMKHANA ROUTE FINDER — Intercept SPA navigation")
    print("=" * 80)

    discovered: Set[str] = set()
    working_routes: dict = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # Intercept ALL requests
        def on_request(request):
            url = request.url
            if "gymkhana.iitkgp.ac.in" not in url:
                return
            if url.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".svg",
                             ".woff", ".woff2", ".ico", ".webp", ".gif")):
                return
            # Strip query strings for cleaner URLs
            clean = url.split("?")[0].split("#")[0]
            discovered.add(clean)

        page.on("request", on_request)

        # Also intercept network responses (JSON APIs)
        async def on_response(response):
            url = response.url
            if "gymkhana.iitkgp.ac.in" in url and any(
                kw in url.lower() for kw in ("api", "json", "data/", "hall", "gov", "award", "gc", "inter")
            ):
                print(f"  📡 API/RESPONSE: {url}")

        page.on("response", on_response)

        # Load home
        print("\n[1] Loading home page...")
        await page.goto(BASE, wait_until="networkidle", timeout=30000)

        # Get all nav text
        nav_texts = await page.eval_on_selector_all(
            "nav a, nav li, header a, header li, header nav *",
            "els => els.map(e => e.innerText.trim()).filter(t => t && t.length < 40)"
        )
        nav_texts = list(set(nav_texts))
        print(f"\n[2] Nav items discovered: {len(nav_texts)}")
        for t in nav_texts[:30]:
            print(f"    • {t}")

        # Click every nav item
        print("\n[3] Clicking through nav items to trigger routes...")
        for nav_text in nav_texts:
            if not nav_text or len(nav_text) > 40:
                continue
            try:
                # Try as text
                locator = page.locator(f"text={nav_text}").first
                if await locator.count() > 0 and await locator.is_visible():
                    await locator.hover(timeout=1500)
                    await page.wait_for_timeout(300)
                    try:
                        await locator.click(timeout=1000, no_wait_after=True)
                        await page.wait_for_timeout(500)
                    except Exception:
                        pass
                    # Go back to home
                    await page.goto(BASE, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(400)
            except Exception:
                continue

        # Direct probe of candidate routes
        print("\n[4] Probing candidate routes directly...")
        for route in CANDIDATE_ROUTES:
            url = BASE + route
            result = await probe_route(page, url)
            status_icon = "✅" if not result["is_404"] else "❌"
            print(f"  {status_icon} {route:40s} -> {result['title'][:60]}")
            if not result["is_404"]:
                working_routes[url] = result
                discovered.add(url)

        await browser.close()

    # Report
    print("\n" + "=" * 80)
    print("ALL DISCOVERED URLs (from network traffic):")
    print("=" * 80)
    for url in sorted(discovered):
        print(f"  {url}")

    print("\n" + "=" * 80)
    print("WORKING CANDIDATE ROUTES:")
    print("=" * 80)
    for url, info in working_routes.items():
        print(f"  ✅ {url}")
        print(f"       Title: {info['title']}")

    # Save
    out = Path("gymkhana_routes.json")
    out.write_text(
        json.dumps({
            "discovered": sorted(discovered),
            "working_routes": working_routes,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\n💾 Saved to: {out.resolve()}")
    print("\n📋 Paste the output above so we can update the config.")


if __name__ == "__main__":
    asyncio.run(main())