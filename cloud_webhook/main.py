"""Standalone 24/7 FastAPI Cloud Webhook Server for KGP Campus Intelligence.

Receives:
1. Incoming WhatsApp notifications via POST /webhook/whatsapp
2. Incoming academic emails via POST /api/email

Extracts structured campus events and academic deadlines using Google Gemini,
and persists them into PostgreSQL/Supabase (or local SQLite).
"""
from contextlib import asynccontextmanager
import logging
import sys
from fastapi import FastAPI
from pydantic import BaseModel, Field

from database import init_db, save_event, save_deadline
from extractor import extract_event_details, extract_deadline_from_email

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
    description="Webhook listener for automated WhatsApp campus event & academic email deadline extraction",
    version="1.1.0",
    lifespan=lifespan,
)


class WebhookPayload(BaseModel):
    """Payload sent by MacroDroid HTTP POST request for WhatsApp notifications."""

    group_name: str = Field(..., description="WhatsApp group or chat name")
    message: str = Field(..., description="Notification body / message text")


class EmailPayload(BaseModel):
    """Payload sent for academic email deadline extraction."""

    user_id: str = Field(..., description="Student Roll Number (e.g. 25CH10025)")
    email_text: str = Field(..., description="Raw email body / subject text")


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


@app.post("/api/email")
async def receive_academic_email(payload: EmailPayload):
    """Endpoint to receive student emails, extract academic deadlines via Gemini,
    and persist them to the AcademicDeadline table in Supabase/PostgreSQL.

    CRITICAL FAIL-SAFE: Wrapped entirely in try/except and always returns 200 OK.
    """
    try:
        logger.info("Received email for user [%s]: %s", payload.user_id, payload.email_text[:100])

        # Step 1: Extract academic deadline details via Gemini
        extracted = await extract_deadline_from_email(payload.email_text)

        # Step 2: If is_academic is true, save to the AcademicDeadline table
        is_academic = bool(extracted.get("is_academic")) if extracted else False
        if is_academic and extracted.get("title"):
            logger.info(
                "Academic deadline detected: '%s' (urgency=%s). Saving to database...",
                extracted.get("title"),
                extracted.get("urgency_weight"),
            )
            saved_record = await save_deadline(
                user_id=payload.user_id,
                raw_email=payload.email_text,
                extracted_data=extracted,
            )
            logger.info("Saved deadline ID: %s", saved_record.id)
            return {
                "status": "success",
                "is_academic": True,
                "deadline_id": str(saved_record.id),
                "title": saved_record.title,
                "urgency_weight": saved_record.urgency_weight,
            }
        else:
            logger.info("Email is not an academic deadline.")
            return {"status": "success", "is_academic": False, "deadline_id": None}

    except Exception as e:
        # Always return 200 OK so upstream forwarders/MacroDroid do not retry
        logger.error("Error processing email deadline: %s", e, exc_info=True)
        return {"status": "success", "error": "Internal processing caught safely"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
