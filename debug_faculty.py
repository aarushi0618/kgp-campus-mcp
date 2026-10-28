import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def main():
    url = "https://www.iitkgp.ac.in/department/AE"
    print(f"Fetching {url} using Playwright...")
    
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()
        
        await page.goto(url, wait_until="networkidle", timeout=30000)
        html = await page.content()
        await browser.close()
        
    soup = BeautifulSoup(html, "html.parser")
    
    # Find the first element that contains "Research Area"
    # This is almost certainly the faculty card
    target = soup.find(string=lambda text: text and "Research Area" in text)
    
    if target:
        # Go up the DOM tree to find the parent container of the card
        parent = target.find_parent("div")
        if parent and parent.parent:
            parent = parent.parent
            
        print("\n--- FOUND FACULTY CARD HTML ---")
        print(parent.prettify()[:2000]) # Print first 2000 chars of the card HTML
    else:
        print("Could not find 'Research Area' in the HTML.")

if __name__ == "__main__":
    asyncio.run(main())