"""Simulation test for all tools running from C:\\ with error log check."""
import asyncio
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Change working directory to C:\ at the top of the script
os.chdir("C:\\")
print(f"Current Working Directory: {os.getcwd()}")

from kgp_mcp.server import (  # noqa: E402
    search_courses,
    search_faculty,
    get_erp_timetable,
    search_locations,
    find_gymkhana_events,
    find_societies,
    get_technology_committee,
    search_all,
)


def _check_no_crash(tool_name: str, entities: list):
    for e in entities:
        if getattr(e, "title", "") == "Tool Error":
            raise RuntimeError(f"Tool {tool_name} crashed: {e.description}")


async def main():
    print("\n--- Testing search_courses ---")
    courses = await search_courses("Machine")
    _check_no_crash("search_courses", courses)
    print(f"search_courses count: {len(courses)} (first: {courses[0].title})")

    print("\n--- Testing search_faculty ---")
    faculty = await search_faculty(department="CS")
    _check_no_crash("search_faculty", faculty)
    print(f"search_faculty count: {len(faculty)} (first: {faculty[0].title})")

    print("\n--- Testing get_erp_timetable ---")
    erp = await get_erp_timetable(subject_code="CH21202")
    _check_no_crash("get_erp_timetable", erp)
    print(f"get_erp_timetable count: {len(erp)} (first: {erp[0].title})")

    print("\n--- Testing search_locations ---")
    locs = await search_locations("Nehru")
    _check_no_crash("search_locations", locs)
    print(f"search_locations count: {len(locs)} (first: {locs[0].title})")

    print("\n--- Testing find_gymkhana_events ---")
    events = await find_gymkhana_events()
    _check_no_crash("find_gymkhana_events", events)
    print(f"find_gymkhana_events count: {len(events)} (first: {events[0].title})")

    print("\n--- Testing find_societies ---")
    socs = await find_societies(category="Technology")
    _check_no_crash("find_societies", socs)
    print(f"find_societies count: {len(socs)} (first: {socs[0].title})")

    print("\n--- Testing get_technology_committee ---")
    tech_comm = await get_technology_committee()
    _check_no_crash("get_technology_committee", tech_comm)
    print(f"get_technology_committee count: {len(tech_comm)} (first: {tech_comm[0].title})")

    print("\n--- Testing search_all ---")
    all_res = await search_all("tech")
    if all_res.get("errors"):
        raise RuntimeError(f"search_all returned errors: {all_res.get('errors')}")
    print(f"search_all sources: {list(all_res.get('results', {}).keys())}")
    for k, v in all_res.get("results", {}).items():
        print(f"  {k}: {len(v)} entities")

    print("\n✅ All tools verified successfully from C:\\ without crashes!")


if __name__ == "__main__":
    asyncio.run(main())
