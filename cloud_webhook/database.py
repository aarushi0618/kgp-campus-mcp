"""Database layer for the KGP Campus WhatsApp & Academic Deadlines Webhook service.

Provides async connection handling, SQLModel entity definitions
(WhatsAppEvent and AcademicDeadline), table initialization, and persistence helpers.
Gracefully falls back to local SQLite (webhook.db) when DATABASE_URL is not set
or when running in a local environment without SQLModel installed.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Optional
import uuid

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

_THIS_DIR = Path(__file__).resolve().parent
load_dotenv(_THIS_DIR / ".env")
load_dotenv(_THIS_DIR.parent / ".env")

LOCAL_SQLITE_PATH = _THIS_DIR / "webhook.db"
raw_db_url = os.getenv("DATABASE_URL", "").strip()

if not raw_db_url:
    DATABASE_URL = f"sqlite+aiosqlite:///{LOCAL_SQLITE_PATH.as_posix()}"
elif raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif raw_db_url.startswith("postgresql://"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = raw_db_url

# Supabase / Neon compatibility: asyncpg uses ?ssl=require rather than ?sslmode=require
if "sslmode=require" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("sslmode=require", "ssl=require")

try:
    from sqlmodel import SQLModel, Field
    from sqlmodel.ext.asyncio.session import AsyncSession
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    HAS_SQLMODEL = True
except ImportError:
    HAS_SQLMODEL = False

if HAS_SQLMODEL:
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

else:
    @dataclass
    class WhatsAppEvent:  # type: ignore[no-redef]
        group_name: str
        raw_message: str
        event_title: Optional[str] = None
        event_date: Optional[str] = None
        event_time: Optional[str] = None
        venue: Optional[str] = None
        description: Optional[str] = None
        id: uuid.UUID = field(default_factory=uuid.uuid4)
        extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @dataclass
    class AcademicDeadline:  # type: ignore[no-redef]
        user_id: str
        title: str
        due_date: str
        due_time: str = "23:59"
        course_code: Optional[str] = None
        urgency_weight: float = 1.0
        raw_email: str = ""
        id: uuid.UUID = field(default_factory=uuid.uuid4)
        created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _init_sqlite_fallback() -> None:
    """Ensure local SQLite webhook.db tables exist."""
    with sqlite3.connect(LOCAL_SQLITE_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS whatsapp_events (
                id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                raw_message TEXT NOT NULL,
                event_title TEXT,
                event_date TEXT,
                event_time TEXT,
                venue TEXT,
                description TEXT,
                extracted_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS academic_deadlines (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                course_code TEXT,
                title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                due_time TEXT NOT NULL,
                urgency_weight REAL NOT NULL,
                raw_email TEXT NOT NULL,
                created_at TEXT
            )
        """)
        conn.commit()


async def init_db() -> None:
    """Initialize database tables asynchronously (or via local SQLite fallback)."""
    if HAS_SQLMODEL and not DATABASE_URL.startswith("sqlite"):
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    else:
        _init_sqlite_fallback()


async def save_event(
    group_name: str,
    raw_message: str,
    extracted_data: dict,
) -> WhatsAppEvent:
    """Insert a new WhatsApp event record into the database."""
    if HAS_SQLMODEL and not DATABASE_URL.startswith("sqlite"):
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

    _init_sqlite_fallback()
    event = WhatsAppEvent(
        group_name=group_name,
        raw_message=raw_message,
        event_title=extracted_data.get("event_title"),
        event_date=extracted_data.get("event_date"),
        event_time=extracted_data.get("event_time"),
        venue=extracted_data.get("venue"),
        description=extracted_data.get("description"),
    )
    with sqlite3.connect(LOCAL_SQLITE_PATH) as conn:
        conn.execute(
            """
            INSERT INTO whatsapp_events (
                id, group_name, raw_message, event_title, event_date, event_time, venue, description, extracted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.id),
                event.group_name,
                event.raw_message,
                event.event_title,
                event.event_date,
                event.event_time,
                event.venue,
                event.description,
                event.extracted_at.isoformat(),
            ),
        )
        conn.commit()
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

    if HAS_SQLMODEL and not DATABASE_URL.startswith("sqlite"):
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

    _init_sqlite_fallback()
    deadline = AcademicDeadline(
        user_id=user_id.strip().upper(),
        course_code=extracted_data.get("course_code"),
        title=str(extracted_data.get("title") or "Academic Deadline").strip(),
        due_date=str(extracted_data.get("due_date") or "").strip(),
        due_time=str(extracted_data.get("due_time") or "23:59").strip(),
        urgency_weight=urgency,
        raw_email=raw_email,
    )
    with sqlite3.connect(LOCAL_SQLITE_PATH) as conn:
        conn.execute(
            """
            INSERT INTO academic_deadlines (
                id, user_id, course_code, title, due_date, due_time, urgency_weight, raw_email, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(deadline.id),
                deadline.user_id,
                deadline.course_code,
                deadline.title,
                deadline.due_date,
                deadline.due_time,
                deadline.urgency_weight,
                deadline.raw_email,
                deadline.created_at.isoformat(),
            ),
        )
        conn.commit()
    return deadline
