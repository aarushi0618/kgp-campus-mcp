"""Event extraction engine using Google Gemini GenAI SDK.

Analyzes raw WhatsApp messages to extract structured event information.
"""
import json
import logging
import os
import re
from typing import Any
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("cloud_webhook.extractor")

EXTRACTION_PROMPT = """You are an expert event information extraction engine for IIT Kharagpur campus groups.
Extract event details from the following incoming WhatsApp announcement:

WhatsApp Message:
\"\"\"{message_text}\"\"\"

Return a strict, valid JSON object with the following schema:
{{
  "event_title": "Title of the event, workshop, competition, or meeting (string, or null if no event is described)",
  "event_date": "Date in YYYY-MM-DD format (string, or null if unknown or unspecified)",
  "event_time": "Time in HH:MM format (24-hour or standard time, or null if unknown)",
  "venue": "Location, classroom, hall, auditorium, or online link (string, or null if unknown)",
  "description": "Concise 1-2 sentence description summarizing the event (string, or null)"
}}

Guidelines:
1. If the message does not announce or describe an actual event, set "event_title" to null.
2. Output ONLY the raw JSON object. Do not enclose in markdown code fences or add explanatory text.
"""


def _clean_json_str(raw: str) -> str:
    """Remove markdown formatting or backticks around JSON output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _normalize_extracted(data: dict[str, Any]) -> dict[str, Any]:
    """Ensure null/None strings are properly cast to None and keys match schema."""
    cleaned: dict[str, Any] = {}
    keys = ["event_title", "event_date", "event_time", "venue", "description"]
    for k in keys:
        val = data.get(k)
        if val is None or val == "null" or str(val).strip().lower() in ("null", "none", "n/a"):
            cleaned[k] = None
        else:
            cleaned[k] = str(val).strip()
    return cleaned


async def extract_event_details(text: str) -> dict[str, Any]:
    """Extract event details from a WhatsApp message using Google Gemini.

    Returns a dict with keys:
        - event_title (str or None)
        - event_date (str or None)
        - event_time (str or None)
        - venue (str or None)
        - description (str or None)

    Returns empty dict {} if Gemini fails or the message cannot be parsed.
    """
    if not text or not text.strip():
        return {}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. Skipping event extraction.")
        return {}

    try:
        from google import genai
        from google.genai import types

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        client = genai.Client(api_key=api_key)

        prompt = EXTRACTION_PROMPT.format(message_text=text.strip())

        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        response_text = response.text if response and response.text else ""
        if not response_text:
            logger.warning("Gemini returned an empty response.")
            return {}

        cleaned_text = _clean_json_str(response_text)
        parsed = json.loads(cleaned_text)

        if isinstance(parsed, dict):
            normalized = _normalize_extracted(parsed)
            logger.info("Successfully extracted event: %s", normalized.get("event_title"))
            return normalized

        logger.warning("Gemini returned non-dictionary JSON: %s", parsed)
        return {}

    except Exception as e:
        logger.error("Error during event extraction: %s", e, exc_info=True)
        return {}
