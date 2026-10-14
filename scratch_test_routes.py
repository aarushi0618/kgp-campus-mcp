"""Test the newly discovered hidden routes."""
import asyncio
import httpx

BASE = "https://gymkhana.iitkgp.ac.in"
HEADERS = {"User-Agent": "KGP-Campus-MCP/0.1"}

ROUTES = [
    "/awards",
    "/results/gc",
    "/results/interiit",
    "/letter-to-you",
    "/contacts",
    "/faq",
]

async def main():
    async with httpx.AsyncClient(headers=HEADERS) as client:
        for route in ROUTES:
            try:
                r = await client.get(BASE + route, timeout=15.0, follow_redirects=True)
                # Check if page has content (not 404)
                has_content = "OOPS" not in r.text[:5000].upper() and "404" not in r.text[:5000]
                marker = "✅" if has_content else "❌"
                print(f"{marker} {route:30s} status={r.status_code} size={len(r.text)}")
            except Exception as e:
                print(f"❌ {route:30s} error={e}")

if __name__ == "__main__":
    asyncio.run(main())