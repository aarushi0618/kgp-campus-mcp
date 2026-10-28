"""Bulletproof simulation of Claude Desktop running the MCP server from C:\\."""
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Change the working directory to C:\ at the start of the script
os.chdir("C:\\")
print(f"Current Working Directory: {os.getcwd()}")

# Import server after changing working directory
from kgp_mcp.server import (  # noqa: E402
    search_all,
    find_societies,
    search_courses,
    get_erp_timetable,
    find_gymkhana_events,
)


async def main():
    print("\n--- Running search_all('CH21202') from C:\\ ---")
    res = await search_all("CH21202")
    print(f"search_all keys: {list(res.get('results', {}).keys())}")
    for source, items in res.get("results", {}).items():
        print(f"  {source}: {len(items)} items")
    print(f"search_all errors: {res.get('errors', [])}")

    print("\n--- Running find_societies(category='Technology') from C:\\ ---")
    socs = await find_societies(category="Technology")
    print(f"find_societies (Technology) count: {len(socs)}")
    if socs:
        print(f"  Sample: {socs[0].title} ({socs[0].metadata.get('category')})")

    print("\n--- Running search_courses('Chemical') from C:\\ ---")
    courses = await search_courses("Chemical")
    print(f"search_courses count: {len(courses)}")

    print("\n--- Running get_erp_timetable(subject_code='CH21202') from C:\\ ---")
    erp = await get_erp_timetable(subject_code="CH21202")
    print(f"get_erp_timetable count: {len(erp)}")

    print("\n--- Running find_gymkhana_events() from C:\\ ---")
    events = await find_gymkhana_events()
    print(f"find_gymkhana_events count: {len(events)}")

    print("\n✅ test_claude_sim.py finished successfully with 0 errors!")


if __name__ == "__main__":
    asyncio.run(main())
