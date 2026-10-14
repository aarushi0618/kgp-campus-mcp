"""Explore HMC warden page HTML structure."""
import httpx
from bs4 import BeautifulSoup
import asyncio

URL = "https://hmc.iitkgp.ac.in/web/warden/"

async def explore():
    async with httpx.AsyncClient() as client:
        r = await client.get(URL, timeout=15.0, follow_redirects=True)
        r.raise_for_status()
        html = r.text
        print(f"Downloaded {len(html)} bytes.\n")

    soup = BeautifulSoup(html, 'html.parser')

    # Find headings that contain "Hall"
    print("--- Headings containing 'Hall' ---")
    for h in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5']):
        text = h.get_text(strip=True)
        if 'Hall' in text:
            print(f"  <{h.name}> class={h.get('class')}: {text}")

    # Find elements containing "WARDEN"
    print("\n--- Elements containing 'WARDEN' ---")
    for el in soup.find_all(string=lambda t: t and 'WARDEN' in t):
        parent = el.parent
        print(f"  Parent tag: <{parent.name}> class={parent.get('class')}")
        print(f"  Text: {parent.get_text(strip=True)[:200]}")
        print(f"  ---")
        # Only show first 3
        if soup.find_all(string=lambda t: t and 'WARDEN' in t).index(el) >= 2:
            break

    # Find all links to professors
    print("\n--- Links containing 'Prof' ---")
    for a in soup.find_all('a', string=lambda t: t and 'Prof' in t)[:5]:
        print(f"  {a.get_text(strip=True)} -> {a.get('href')}")

    # Print a sample section of HTML for structure
    print("\n--- Sample: first 2000 chars of body ---")
    body = soup.find('body')
    if body:
        print(body.get_text()[:1500])

if __name__ == "__main__":
    asyncio.run(explore())