"""Event & Academic Deadline extraction engine using Google Gemini GenAI SDK.

Includes multi-model automatic fallback across available Flash/Lite/Pro models
to handle 404 NOT_FOUND and 503 UNAVAILABLE errors on the free tier.
"""
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(dotenv_path=None):
        p = Path(dotenv_path) if dotenv_path else Path(".env")
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# Load .env from cloud_webhook/.env and project root .env
_THIS_DIR = Path(__file__).resolve().parent
load_dotenv(_THIS_DIR / ".env")
load_dotenv(_THIS_DIR.parent / ".env")

logger = logging.getLogger("cloud_webhook.extractor")

# Verified working models from client.models.list() supporting generateContent on the free tier
FALLBACK_MODELS = [
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.8-flash",
    "models/gemini-3.5-flash",
    "models/gemini-3.6-flash",
    "models/gemini-3.7-flash",
    "models/gemini-flash-lite-latest",
    "models/gemini-flash-latest",
]

EXTRACTION_PROMPT = """You are an expert event information extraction engine for IIT Kharagpur campus groups.
Current Date Context: {today_context}

Extract event details from the following incoming WhatsApp announcement:

WhatsApp Message:
\"\"\"{message_text}\"\"\"

Return a strict, valid JSON object with the following schema:
{{
  "event_title": "Title of the event, workshop, competition, or meeting (string, or null if no event is described)",
  "event_date": "Date in YYYY-MM-DD format resolved relative to Current Date Context (string, or null if unknown)",
  "event_time": "Time in HH:MM 24-hour format, e.g. '17:00' for 5 PM (string, or null if unknown)",
  "venue": "Location, classroom, hall, auditorium, or online link (string, or null if unknown)",
  "description": "Concise 1-2 sentence description summarizing the event (string, or null)"
}}

Guidelines:
1. If the message does not announce or describe an actual event, set "event_title" to null.
2. Output ONLY the raw JSON object. Do not enclose in markdown code fences or add explanatory text.
"""

DEADLINE_EXTRACTION_PROMPT = """Extract the academic deadline. Calculate a baseline urgency_weight: Exam=5.0, Assignment/Lab=4.0, Quiz=3.5, General=1.0. Return strict JSON: {{is_academic, title, due_date, due_time, course_code, urgency_weight}}

Current Date Context: {today_context}

Email Text:
\"\"\"{email_text}\"\"\"

Schema Specification:
{{
  "is_academic": true or false (boolean indicating if the email contains an academic deadline, exam, quiz, assignment, or lab submission),
  "title": "Short title of the deadline (string, or null if not academic)",
  "due_date": "YYYY-MM-DD format resolved relative to Current Date Context (string, or null if unknown)",
  "due_time": "HH:MM in 24-hour format, e.g. '23:59' for 11:59 PM (string, or null)",
  "course_code": "Course code like 'CH21202' or 'CH21205' if mentioned, else null",
  "urgency_weight": 5.0 for Exam, 4.0 for Assignment/Lab, 3.5 for Quiz, 1.0 for General (float)
}}

Output ONLY the raw JSON object without markdown formatting.
"""


def _get_candidate_models() -> list[str]:
    """Return ordered list of models to try, skipping retired 1.5/2.5 models."""
    candidates: list[str] = []
    env_model = os.getenv("GEMINI_MODEL", "").strip()
    if env_model and "1.5" not in env_model and "2.5" not in env_model:
        normalized_env = env_model if env_model.startswith("models/") else f"models/{env_model}"
        candidates.append(normalized_env)
    for m in FALLBACK_MODELS:
        if m not in candidates:
            candidates.append(m)
    return candidates


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
        if val is None or val == "null" or str(val).strip().lower() in ("null", "none", "n/a", ""):
            cleaned[k] = None
        else:
            cleaned[k] = str(val).strip()
    return cleaned


def _normalize_deadline(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize extracted academic deadline dictionary fields."""
    raw_is_academic = data.get("is_academic")
    if isinstance(raw_is_academic, bool):
        is_academic = raw_is_academic
    elif isinstance(raw_is_academic, str):
        is_academic = raw_is_academic.strip().lower() in ("true", "1", "yes")
    else:
        is_academic = bool(raw_is_academic)

    def _clean_str(val: Any, default: Any = None) -> Any:
        if val is None or str(val).strip().lower() in ("null", "none", "n/a", ""):
            return default
        return str(val).strip()

    try:
        urgency = float(data.get("urgency_weight") if data.get("urgency_weight") is not None else 1.0)
    except (ValueError, TypeError):
        urgency = 1.0

    return {
        "is_academic": is_academic,
        "title": _clean_str(data.get("title")),
        "due_date": _clean_str(data.get("due_date")),
        "due_time": _clean_str(data.get("due_time"), default="23:59"),
        "course_code": _clean_str(data.get("course_code")),
        "urgency_weight": urgency,
    }


async def extract_event_details(text: str) -> dict[str, Any]:
    """Extract event details from a WhatsApp message using Google Gemini with multi-model fallback."""
    if not text or not text.strip():
        return {}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. Skipping event extraction.")
        return {}

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    today_context = datetime.now().strftime("%Y-%m-%d (%A)")
    prompt = EXTRACTION_PROMPT.format(
        today_context=today_context,
        message_text=text.strip(),
    )

    for model_name in _get_candidate_models():
        try:
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
                logger.warning("Model %s returned empty response, trying next...", model_name)
                continue

            cleaned_text = _clean_json_str(response_text)
            parsed = json.loads(cleaned_text)
            if isinstance(parsed, dict):
                normalized = _normalize_extracted(parsed)
                logger.info(
                    "Successfully extracted event using %s: %s",
                    model_name,
                    normalized.get("event_title"),
                )
                return normalized
        except Exception as e:
            logger.warning(
                "Model %s failed during event extraction (%s). Trying next fallback model...",
                model_name,
                e,
            )
            continue

    logger.error("All Gemini fallback models failed for event extraction.")
    return {}


async def extract_deadline_from_email(text: str) -> dict[str, Any]:
    """Extract academic deadline details from an email using Google Gemini with multi-model fallback."""
    if not text or not text.strip():
        return {}

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set. Skipping deadline extraction.")
        return {}

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    today_context = datetime.now().strftime("%Y-%m-%d (%A)")
    prompt = DEADLINE_EXTRACTION_PROMPT.format(
        today_context=today_context,
        email_text=text.strip(),
    )

    for model_name in _get_candidate_models():
        try:
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
                logger.warning("Model %s returned empty response for email, trying next...", model_name)
                continue

            cleaned_text = _clean_json_str(response_text)
            parsed = json.loads(cleaned_text)
            if isinstance(parsed, dict):
                normalized = _normalize_deadline(parsed)
                logger.info(
                    "Successfully extracted deadline using %s (is_academic=%s, title=%s, urgency=%s)",
                    model_name,
                    normalized.get("is_academic"),
                    normalized.get("title"),
                    normalized.get("urgency_weight"),
                )
                return normalized
        except Exception as e:
            logger.warning(
                "Model %s failed during deadline extraction (%s). Trying next fallback model...",
                model_name,
                e,
            )
            continue

    logger.error("All Gemini fallback models failed for email deadline extraction.")
    return {}
