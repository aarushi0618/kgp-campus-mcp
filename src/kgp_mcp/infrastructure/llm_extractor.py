"""LLM-based structured extractor using Google Gemini.

Used for messy, JS-rendered pages where rule-based parsing is impractical.
Falls back gracefully if the API key is missing.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Find .env file in project root if present
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


def _load_env_file():
    if not ENV_FILE.exists():
        return
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        logger.warning(f"Failed to read .env file: {e}")


_load_env_file()


class LLMExtractor:
    """Convert unstructured text into structured JSON using Gemini."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.8-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model
        self.client = genai.Client(api_key=self.api_key) if self.api_key else None
        if not self.client:
            logger.warning("GEMINI_API_KEY not set; LLM extraction disabled.")

    async def extract(
        self,
        raw_text: str,
        schema_description: str,
        example_json: str,
        max_chars: int = 20000,
    ) -> List[Dict[str, Any]]:
        """Extract a JSON array of items from raw text."""
        if not self.client:
            return []

        prompt = f"""You are a data extraction assistant. Read the text below and extract structured data.

TASK: {schema_description}

Each item in the returned JSON array must match this structure:
{example_json}

CRITICAL RULES:
- Return ONLY the JSON array, nothing else.
- No markdown fences. No explanations.
- If nothing found, return [].
- Do not invent data. Only extract what's present.

TEXT:
\"\"\"
{raw_text[:max_chars]}
\"\"\"
"""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            data = json.loads(response.text)
            return data if isinstance(data, list) else []

        except Exception:
            logger.exception("LLM extraction failed")
            return []
