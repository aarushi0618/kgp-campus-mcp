"""Standalone 24/7 FastAPI Cloud Webhook Server for KGP Campus Intelligence.

Receives incoming WhatsApp notifications via HTTP POST from MacroDroid,
extracts structured campus events using Google Gemini, and records them
into PostgreSQL/SQLite.
"""
from contextlib import asynccontextmanager
import logging
import sys
from fastapi import FastAPI
from pydantic import BaseModel, Field

from database import init_db, save_event
from extractor import extract_event_details

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("cloud_webhook")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: initializes database tables upon startup."""
    try:
        logger.info("Initializing database tables...")
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize database on startup: %s", e, exc_info=True)
    yield
    logger.info("Shutting down webhook service.")


app = FastAPI(
    title="KGP Campus Intelligence Webhook",
    description="Webhook listener for automated WhatsApp campus event extraction",
    version="1.0.0",
    lifespan=lifespan,
)


class WebhookPayload(BaseModel):
    """Payload sent by MacroDroid HTTP POST request."""

    group_name: str = Field(..., description="WhatsApp group or chat name")
    message: str = Field(..., description="Notification body / message text")


@app.get("/")
async def health_check():
    """Health check endpoint for Render/Railway container monitoring."""
    return {"status": "healthy"}


@app.post("/webhook/whatsapp")
async def receive_whatsapp_notification(payload: WebhookPayload):
    """Webhook endpoint to receive, parse, and persist WhatsApp event notifications.

    CRITICAL FAIL-SAFE: Wrapped entirely in try/except.
    Always returns HTTP 200 {"status": "success"} to prevent client/MacroDroid retries.
    """
    try:
        logger.info("Received WhatsApp notification from [%s]: %s", payload.group_name, payload.message[:100])

        # Step 1: Extract structured event details via Gemini
        extracted = await extract_event_details(payload.message)

        # Step 2: If a valid event title is detected, persist it
        event_title = extracted.get("event_title") if extracted else None
        if event_title:
            logger.info("Valid event detected: '%s'. Saving to database...", event_title)
            saved_record = await save_event(
                group_name=payload.group_name,
                raw_message=payload.message,
                extracted_data=extracted,
            )
            logger.info("Saved event ID: %s", saved_record.id)
            return {"status": "success", "event_id": str(saved_record.id), "title": event_title}
        else:
            logger.info("No actionable event detected in message.")
            return {"status": "success", "event_id": None, "message": "No event found"}

    except Exception as e:
        # Log failure with full traceback, but ALWAYS return 200 OK {"status": "success"}
        logger.error("Error processing webhook notification: %s", e, exc_info=True)
        return {"status": "success", "error": "Internal processing caught safely"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
