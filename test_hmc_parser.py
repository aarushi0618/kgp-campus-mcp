"""Quick test for the HMC parser (Day 2)."""
import asyncio
from bs4 import BeautifulSoup

from kgp_mcp.adapters.location_adapter import LocationAdapter


async def main():
    adapter = LocationAdapter(url="https://hmc.iitkgp.ac.in/web/warden/")
    raw = await adapter.fetch()
    soup = BeautifulSoup(raw, "html.parser")
    halls = adapter._extract_halls_from_soup(soup)

    print(f"\n{'='*70}")
    print(f"Total halls parsed: {len(halls)}")
    print(f"{'='*70}\n")

    for h in halls:
        print(f"🏛  {h['name']}")
        print(f"   Warden:     {h['warden']}")
        print(f"   Department: {h['warden_department']}")
        print(f"   Assistants: {h.get('assistant_wardens')}")
        print()


if __name__ == "__main__":
    asyncio.run(main())