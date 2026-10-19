import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google import genai

async def main():
    # Check if the API key is available in the environment
    if "GEMINI_API_KEY" not in os.environ:
        print("❌ Error: GEMINI_API_KEY environment variable is not set.")
        return

    # Define how to run your MCP server
    # This matches the quickstart in your README.md
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "src/kgp_mcp/server.py"],
    )

    print("🚀 Starting MCP server and connecting to Gemini...")

    # Start the MCP client and session
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Initialize the Gemini client
            client = genai.Client()

            # Ask Gemini a question that requires your tools
            # Based on your verify_day1.py, you have a 'get_academic_calendar' tool
            prompt = "Can you check the academic calendar for any events in December 2026?"
            print(f"\n📤 Sending prompt to Gemini: '{prompt}'")

            response = await client.aio.models.generate_content(
                model="gemini-3.8-flash", 
                contents=prompt,
                # Use a plain dict for the config instead of GenerateContentConfig
                config={
                    "tools": [session],
                    # You can add other config parameters here as keys, e.g.:
                    # "temperature": 0.0
                },
            )

            print("\n📥 Gemini's Response:")
            print("-" * 50)
            print(response.text)
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(main())