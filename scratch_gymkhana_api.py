"""Explore the hidden Gymkhana JSON API endpoints."""
import asyncio
import json
from pathlib import Path

import httpx

BASE = "https://gymkhana.iitkgp.ac.in"
HEADERS = {"User-Agent": "KGP-Campus-MCP/0.1 (educational)"}

# Endpoints discovered via network interception
ENDPOINTS = [
    "/api/v1/categories",
    "/api/v1/posts?page=1&limit=12",
    "/api/v1/posts?page=1&limit=100",
    "/api/v1/posts?category=technology&page=1&limit=50",
    "/api/v1/posts?category=societies&page=1&limit=50",
]


async def probe(path: str):
    url = BASE + path
    print(f"\n{'='*70}\nGET {url}\n{'='*70}")
    async with httpx.AsyncClient(headers=HEADERS) as client:
        try:
            r = await client.get(url, timeout=15.0, follow_redirects=True)
            print(f"Status: {r.status_code}")
            print(f"Content-Type: {r.headers.get('content-type')}")
            if "json" in r.headers.get("content-type", ""):
                data = r.json()
                # Truncate for readability
                preview = json.dumps(data, indent=2, ensure_ascii=False)
                print(f"JSON preview (first 2000 chars):\n{preview[:2000]}")
                # Structure summary
                if isinstance(data, dict):
                    print(f"\nTop-level keys: {list(data.keys())}")
                    for k, v in data.items():
                        if isinstance(v, list):
                            print(f"  {k}: list of {len(v)}")
                            if v and isinstance(v[0], dict):
                                print(f"    Item keys: {list(v[0].keys())}")
                        elif isinstance(v, dict):
                            print(f"  {k}: dict with keys {list(v.keys())}")
            else:
                print(f"Text preview: {r.text[:500]}")
        except Exception as e:
            print(f"❌ Error: {e}")


async def main():
    print("Probing Gymkhana API endpoints...")
    for path in ENDPOINTS:
        await probe(path)

    # Save full results
    out = Path("gymkhana_api_exploration.txt")
    # (Just notes; no need to save everything)


if __name__ == "__main__":
    asyncio.run(main())