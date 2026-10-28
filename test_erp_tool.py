import asyncio
from kgp_mcp.server import get_erp_timetable

async def main():
    print("Testing get_erp_timetable...")
    try:
        # Simulate exactly what Claude does
        res = await get_erp_timetable(subject_code="CH21202")
        print(f"✅ Found {len(res)} results.")
        for r in res:
            print(f"Subject: {r.title} | Description: {r.description}")
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())