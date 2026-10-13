from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users & conversations
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    name = Column(String, nullable=False)
    program = Column(String)  # e.g. "B.Tech ECE"
    year = Column(String)  # e.g. "4th semester"
    bio = Column(Text)
    interests = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")
    outreach = relationship("Outreach", back_populates="user", cascade="all, delete-orphan")


class Chat(Base):
    __tablename__ = "chats"

    id = Column(String, primary_key=True)  # uuid4 hex
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False, default="New chat")
    # Rolling summary of every message with id <= summarized_upto.
    summary = Column(Text, nullable=False, default="")
    summarized_upto = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, index=True)

    user = relationship("User", back_populates="chats")
    messages = relationship(
        "Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String, ForeignKey("chats.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    sources = Column(JSON, nullable=False, default=list)  # [{title, url}]
    created_at = Column(DateTime(timezone=True), default=utcnow)

    chat = relationship("Chat", back_populates="messages")


class Outreach(Base):
    """One card per (student, professor) on the outreach tracker, holding the latest draft."""

    __tablename__ = "outreach"
    __table_args__ = (UniqueConstraint("user_id", "faculty_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # No FK to faculty: the crawler may drop and re-create faculty rows; name/email are copied here.
    faculty_id = Column(Integer, nullable=False)
    professor_name = Column(String, nullable=False)
    professor_email = Column(String)
    purpose = Column(String)
    subject = Column(String, nullable=False, default="")  # working draft
    body = Column(Text, nullable=False, default="")
    sent = Column(JSON, nullable=False, default=list)  # [{subject, body, sent_on}] archived on "mark sent"
    status = Column(String, nullable=False, default="drafted")  # see routers/outreach.py STATUSES
    notes = Column(Text, nullable=False, default="")
    sent_on = Column(Date)
    follow_up_on = Column(Date)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = relationship("User", back_populates="outreach")


# ---------------------------------------------------------------------------
# Scraped website content (source of truth for the vector index)
# ---------------------------------------------------------------------------


class Page(Base):
    __tablename__ = "pages"

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False, index=True)
    title = Column(String)
    category = Column(String, index=True)
    text = Column(Text)  # cleaned, section-structured text
    content_hash = Column(String)
    active = Column(Boolean, nullable=False, default=True)
    first_seen = Column(DateTime(timezone=True), default=utcnow)
    fetched_at = Column(DateTime(timezone=True))
    changed_at = Column(DateTime(timezone=True))

    chunks = relationship("Chunk", back_populates="page", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(String, primary_key=True)  # "<page_id>:<ord>"
    page_id = Column(Integer, ForeignKey("pages.id"), nullable=False, index=True)
    ord = Column(Integer, nullable=False)
    heading = Column(String)
    text = Column(Text, nullable=False)

    page = relationship("Page", back_populates="chunks")


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), default=utcnow)
    finished_at = Column(DateTime(timezone=True))
    status = Column(String, default="running")  # running | ok | failed
    pages_fetched = Column(Integer, default=0)
    pages_changed = Column(Integer, default=0)
    pages_removed = Column(Integer, default=0)
    error = Column(Text)


# ---------------------------------------------------------------------------
# Structured records extracted from specific pages (exact-answer tools)
# ---------------------------------------------------------------------------


class Faculty(Base):
    """Department faculty; the numeric IITR profile URL id is the PK."""

    __tablename__ = "faculty"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    designation = Column(String)
    email = Column(String)
    phone = Column(String)
    website = Column(String)
    interests = Column(Text)
    profile_url = Column(String)
    image_url = Column(String)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    faculty_raw = Column(String)  # verbatim PI text from the source table
    faculty_id = Column(Integer, ForeignKey("faculty.id"), index=True)
    title = Column(Text, nullable=False)
    agency = Column(Text)
    co_pi = Column(Text)
    year = Column(String, index=True)

    faculty = relationship("Faculty")


class Startup(Base):
    __tablename__ = "startups"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    founder_raw = Column(String)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), index=True)
    website = Column(String)
    description = Column(Text)


class Opportunity(Base):
    """Job / fellowship adverts from IITR career pages."""

    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)  # advert link (usually a PDF)
    kind = Column(String)  # "Project Job" | "Post-Doctoral Fellowship"
    title = Column(Text, nullable=False)
    department = Column(String)
    is_ece = Column(Boolean, nullable=False, default=False, index=True)
    posted_on = Column(String)
    deadline = Column(String)
    details = Column(Text)  # extracted advert text (ECE adverts only)
    active = Column(Boolean, nullable=False, default=True)
    first_seen = Column(DateTime(timezone=True), default=utcnow)
