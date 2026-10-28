import asyncio
import json
import sys
from pathlib import Path
from kgp_mcp.adapters.academic_adapter import AcademicAdapter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT_DIR / "data" / "courses_dump.json"


async def main():
    print("Scraping/generating courses data...")
    adapter = AcademicAdapter()
    entities = await adapter.get_entities()

    data = [e.model_dump(mode="json") for e in entities]

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved {len(data)} courses to {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
