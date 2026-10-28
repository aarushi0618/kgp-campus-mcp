"""Test direct tools from C:\\ to simulate Claude Desktop's environment."""
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Change the working directory to C:\ to simulate Claude Desktop's environment
os.chdir("C:\\")
print(f"Current Working Directory: {os.getcwd()}")

from kgp_mcp.server import (  # noqa: E402
    find_societies,
    find_gymkhana_events,
    get_erp_timetable,
)


async def main():
    print("\n--- Calling find_societies(category='Technology') ---")
    socs = await find_societies(category="Technology")
    print(f"find_societies length: {len(socs)}")

    print("\n--- Calling find_gymkhana_events() ---")
    events = await find_gymkhana_events()
    print(f"find_gymkhana_events length: {len(events)}")

    print("\n--- Calling get_erp_timetable(subject_code='CH21202') ---")
    erp = await get_erp_timetable(subject_code="CH21202")
    print(f"get_erp_timetable length: {len(erp)}")


if __name__ == "__main__":
    asyncio.run(main())
