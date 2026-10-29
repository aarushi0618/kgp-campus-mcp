"""Temporary script to list all Gemini models available to the configured API key."""
import os
from pathlib import Path
from google import genai

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
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(ROOT_DIR / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("ERROR: GEMINI_API_KEY not found in .env")
    raise SystemExit(1)

client = genai.Client(api_key=api_key)
for m in client.models.list():
    methods = getattr(m, "supported_methods", None) or getattr(m, "supported_actions", None)
    print(m.name, methods)
