"""Master verification for Day 2 (Oct 6)."""
import asyncio
from bs4 import BeautifulSoup

def check(name, cond, detail=""):
    print(f"{'✅ PASS' if cond else '❌ FAIL'} | {name}")
    if detail:
        print(f"       {detail}")

async def main():
    print("=" * 70)
    print("VERIFICATION: Day 2 — Location Adapter + OSM Client")
    print("=" * 70)

        # Layer 1: OSM Client (now local JSON)
    print("\n[LAYER 1] Coordinates Client (Local JSON)")
    try:
        from kgp_mcp.infrastructure.osm_client import OSMClient
        client = OSMClient()
        coords = await client.get_coordinates_map()
        check("osm_client.py loads JSON", len(coords) > 0,
              f"Loaded {len(coords)} halls from JSON")
        if coords:
            sample = list(coords.items())[0]
            print(f"       Sample: {sample[0]} -> {sample[1]}")
    except Exception as e:
        check("Coordinates client", False, str(e))

    # Layer 2: Location Adapter parsing
    print("\n[LAYER 2] Location Adapter parsing")
    try:
        from kgp_mcp.adapters.location_adapter import LocationAdapter
        adapter = LocationAdapter(url="test", osm_client=None)
        check("location_adapter.py imports", True)

        html = """
        <h3>Nehru Hall of Residence</h3>
        <div><a>Prof. Test Warden</a><p>Engineering</p><p>WARDEN</p></div>
        """
        halls = adapter._extract_halls(BeautifulSoup(html, "html.parser"))
        check("Extracts hall + warden", len(halls) == 1 and halls[0]["warden"] == "Prof. Test Warden",
              f"Got: {halls}")
    except Exception as e:
        check("Location adapter", False, str(e))

    # Layer 3: Server registration
    print("\n[LAYER 3] Server tool registration")
    try:
        from kgp_mcp.server import mcp
        tools = await mcp.list_tools()
        names = [t.name for t in tools]
        check("search_locations registered", "search_locations" in names,
              f"Registered: {names}")
    except Exception as e:
        check("Server", False, str(e))

    print("\n" + "=" * 70)

if __name__ == "__main__":
    asyncio.run(main())