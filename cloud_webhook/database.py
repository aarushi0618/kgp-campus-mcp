"""Database layer for the KGP Campus WhatsApp & Academic Deadlines Webhook service.

Provides async connection handling, SQLModel entity definitions
(WhatsAppEvent and AcademicDeadline), table initialization, and persistence helpers.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from dotenv import load_dotenv
from sqlmodel import SQLModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

load_dotenv()

# Resolve database URL
raw_db_url = os.getenv("DATABASE_URL", "").strip()

if not raw_db_url:
    DATABASE_URL = "sqlite+aiosqlite:///./webhook.db"
elif raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif raw_db_url.startswith("postgresql://"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = raw_db_url

# Supabase / Neon compatibility: asyncpg uses ?ssl=require rather than ?sslmode=require
if "sslmode=require" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("sslmode=require", "ssl=require")

# SQLite requires different connect_args than PostgreSQL
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=connect_args,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class WhatsAppEvent(SQLModel, table=True):
    """Stores incoming WhatsApp announcements and their extracted event metadata."""

    __tablename__ = "whatsapp_events"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique event ID",
    )
    group_name: str = Field(
        index=True,
        description="Name of the WhatsApp group or chat source",
    )
    raw_message: str = Field(
        description="Original text message received from notification",
    )
    event_title: Optional[str] = Field(
        default=None,
        index=True,
        description="Extracted title of the event",
    )
    event_date: Optional[str] = Field(
        default=None,
        index=True,
        description="Extracted date of event (YYYY-MM-DD)",
    )
    event_time: Optional[str] = Field(
        default=None,
        description="Extracted time of event (HH:MM)",
    )
    venue: Optional[str] = Field(
        default=None,
        description="Extracted location/venue/link",
    )
    description: Optional[str] = Field(
        default=None,
        description="Short summary of the event",
    )
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of extraction",
    )


class AcademicDeadline(SQLModel, table=True):
    """Stores academic deadlines extracted from incoming student emails."""

    __tablename__ = "academic_deadlines"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique deadline ID",
    )
    user_id: str = Field(
        index=True,
        description="Student Roll Number (e.g. 25CH10025)",
    )
    course_code: Optional[str] = Field(
        default=None,
        index=True,
        description="Course code (e.g. CH21205) if applicable",
    )
    title: str = Field(
        description="Title of the exam, assignment, lab, or quiz",
    )
    due_date: str = Field(
        index=True,
        description="Due date in YYYY-MM-DD format",
    )
    due_time: str = Field(
        default="23:59",
        description="Due time in HH:MM format",
    )
    urgency_weight: float = Field(
        default=1.0,
        description="Baseline urgency weight (Exam=5.0, Assignment/Lab=4.0, Quiz=3.5, General=1.0)",
    )
    raw_email: str = Field(
        description="Raw email text from which the deadline was extracted",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when record was created",
    )


async def init_db() -> None:
    """Initialize database tables asynchronously."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def save_event(
    group_name: str,
    raw_message: str,
    extracted_data: dict,
) -> WhatsAppEvent:
    """Insert a new WhatsApp event record into the database."""
    async with async_session_factory() as session:
        event = WhatsAppEvent(
            group_name=group_name,
            raw_message=raw_message,
            event_title=extracted_data.get("event_title"),
            event_date=extracted_data.get("event_date"),
            event_time=extracted_data.get("event_time"),
            venue=extracted_data.get("venue"),
            description=extracted_data.get("description"),
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        return event


async def save_deadline(
    user_id: str,
    raw_email: str,
    extracted_data: dict,
) -> AcademicDeadline:
    """Insert a new AcademicDeadline record into the database."""
    try:
        urgency = float(extracted_data.get("urgency_weight") or 1.0)
    except (ValueError, TypeError):
        urgency = 1.0

    async with async_session_factory() as session:
        deadline = AcademicDeadline(
            user_id=user_id.strip().upper(),
            course_code=extracted_data.get("course_code"),
            title=str(extracted_data.get("title") or "Academic Deadline").strip(),
            due_date=str(extracted_data.get("due_date") or "").strip(),
            due_time=str(extracted_data.get("due_time") or "23:59").strip(),
            urgency_weight=urgency,
            raw_email=raw_email,
        )
        session.add(deadline)
        await session.commit()
        await session.refresh(deadline)
        return deadline
