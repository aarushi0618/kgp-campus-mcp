"""Manual test: fetch and print Gymkhana data."""
import asyncio
import pytest

@pytest.mark.asyncio
async def test_api():
    from kgp_mcp.adapters.gymkhana_api_adapter import GymkhanaAPIAdapter

    print("\n" + "=" * 70)
    print("TEST 1: Events API (no LLM, fast)")
    print("=" * 70)
    a = GymkhanaAPIAdapter(is_event=True, limit=50)
    events = await a.get_entities()
    print(f"✅ Fetched {len(events)} events\n")
    for e in events[:5]:
        print(f"  🎉 {e.title[:80]}")
        print(f"     Society:  {e.metadata.get('society')}")
        print(f"     Date:     {e.metadata.get('event_date')}")
        print(f"     Category: {e.metadata.get('category')}\n")

@pytest.mark.asyncio
async def test_llm():
    from kgp_mcp.config import GYMKHANA_LLM_SECTIONS
    from kgp_mcp.adapters.gymkhana_adapter import GymkhanaHTMLAdapter

    print("\n" + "=" * 70)
    print("TEST 2: Societies (LLM-based)")
    print("=" * 70)
    cfg = GYMKHANA_LLM_SECTIONS["societies"]
    a = GymkhanaHTMLAdapter(**{**cfg, "tag": "societies"})
    entities = await a.get_entities()
    print(f"✅ Extracted {len(entities)} societies\n")
    for e in entities[:5]:
        print(f"  🏛  {e.title}")
        print(f"     {e.description[:100]}\n")

@pytest.mark.asyncio
async def main():
    await test_api()
    # Uncomment after setting GEMINI_API_KEY:
    # await test_llm()


if __name__ == "__main__":
    asyncio.run(main())