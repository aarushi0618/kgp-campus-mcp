"""Scratch script to test the Faculty Adapter."""
import asyncio
from kgp_mcp.adapters.faculty_Adapter import FacultyAdapter

async def main():
    print("Fetching faculty data... this may take 15-20 seconds.")
    adapter = FacultyAdapter()
    
    entities = await adapter.get_entities()
    
    print(f"\n✅ Found {len(entities)} faculty members across all departments:\n")
    for e in entities[:5]: # Print first 5
        print(f"👨‍🏫 {e.title}")
        print(f"   Dept: {e.metadata.get('department_name')} ({e.metadata.get('department_code')})")
        print(f"   Email: {e.metadata.get('email')}")
        print(f"   Research: {e.metadata.get('research_area')}")
        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())