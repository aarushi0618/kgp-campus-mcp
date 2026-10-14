"""Bulletproof test for coordinates loading — no network, no retries."""
import asyncio
import json
import sys
from pathlib import Path

# Show progress at each step
print("STEP 1: Starting test...", flush=True)

# Find the JSON file
json_path = Path(__file__).parent / "data" / "hall_coordinates.json"
print(f"STEP 2: Looking for JSON at: {json_path}", flush=True)
print(f"STEP 3: JSON exists? {json_path.exists()}", flush=True)

if not json_path.exists():
    print(f"\n❌ ERROR: File not found at {json_path}")
    print(f"   Current directory: {Path.cwd()}")
    print(f"   Files here: {list(Path.cwd().iterdir())}")
    sys.exit(1)

# Read the JSON directly
with open(json_path, "r", encoding="utf-8") as f:
    raw = json.load(f)

halls = raw.get("halls", [])
print(f"\n✅ STEP 4: Loaded {len(halls)} halls from JSON.", flush=True)
print(f"   Source: {raw.get('source', 'N/A')}")
print(f"   Last updated: {raw.get('last_updated', 'N/A')}\n", flush=True)

for h in halls[:5]:
    print(f"   {h['name']}: ({h['latitude']}, {h['longitude']})")
print(f"   ... ({len(halls) - 5} more)\n", flush=True)

# Now test the OSMClient class
print("STEP 5: Testing OSMClient class...", flush=True)


async def test_client():
    from kgp_mcp.infrastructure.osm_client import OSMClient
    client = OSMClient()
    coords = await client.get_coordinates_map()
    print(f"✅ STEP 6: OSMClient returned {len(coords)} coordinates.", flush=True)
    return coords


coords = asyncio.run(test_client())
print(f"\n🎉 ALL STEPS PASSED. Total halls with coordinates: {len(coords)}")