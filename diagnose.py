import asyncio
import traceback
from kgp_mcp.server import get_erp_timetable, search_faculty

async def main():
    print("--- Testing ERP Tool ---")
    try:
        res = await get_erp_timetable(subject_code="CH21205")
        print(f"✅ ERP Success: Found {len(res)} results.")
    except Exception as e:
        print("❌ ERP FAILED WITH ERROR:")
        traceback.print_exc()

    print("\n--- Testing Faculty Tool ---")
    try:
        res = await search_faculty(department="AE")
        print(f"✅ Faculty Success: Found {len(res)} results.")
    except Exception as e:
        print("❌ Faculty FAILED WITH ERROR:")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())