import asyncio
from playwright.async_api import async_playwright

async def main():
    url = "https://gymkhana.iitkgp.ac.in/societies"
    print(f"Loading {url}...")
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(5000) # Wait 5 seconds for JS
        
        # 1. Print the title (to check if we're on the right page)
        title = await page.title()
        print(f"Page Title: {title}")
        
        # 2. Count all links
        links = await page.eval_on_selector_all("a", "els => els.map(e => e.getAttribute('href'))")
        print(f"\nTotal <a> tags found: {len(links)}")
        
        # 3. Print the first 20 links to see their format
        print("\nFirst 20 links (href):")
        for link in links[:20]:
            print(f"  - {link}")
            
        # 4. Print a snippet of the visible text
        text = await page.eval_on_selector("body", "el => el.innerText")
        print(f"\nBody text preview (first 500 chars):\n{text[:500]}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())