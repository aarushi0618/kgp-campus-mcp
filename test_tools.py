"""Rigorous environment-independent test simulating how Claude Desktop invokes MCP tools from C:\\."""
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Simulate Claude Desktop launching the server from C:\
os.chdir("C:\\")
print(f"Current Working Directory: {os.getcwd()}")

from kgp_mcp.server import (  # noqa: E402
    mcp,
    find_societies,
    find_gymkhana_events,
    get_erp_timetable,
)


async def main():
    # 1. Direct Python function calls
    socs_tech = await find_societies(category="Technology")
    events = await find_gymkhana_events()
    erp = await get_erp_timetable(subject_code="CH21202")

    print(f"find_societies(category='Technology'): {len(socs_tech)}")
    print(f"find_gymkhana_events(): {len(events)}")
    print(f"get_erp_timetable(subject_code='CH21202'): {len(erp)}")

    # 2. MCP protocol-level calls (including explicit None arguments sent by Claude Desktop)
    await mcp.call_tool("find_societies", {"query": None, "category": "Technology"})
    await mcp.call_tool("find_gymkhana_events", {"query": None, "category": None})
    await mcp.call_tool("get_erp_timetable", {"department": None, "subject_code": "CH21202"})
    print("SUCCESS: MCP protocol-level tool calls (with explicit None args) succeeded without ValidationError!")


if __name__ == "__main__":
    asyncio.run(main())
