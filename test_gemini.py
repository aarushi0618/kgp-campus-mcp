import asyncio
from cloud_webhook.extractor import extract_deadline_from_email

async def main():
    text = "Mass Transfer Assignment 3 is due on October 31st at 11:59 PM."
    print("Testing Gemini...")
    result = await extract_deadline_from_email(text)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())