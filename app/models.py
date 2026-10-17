"""
SQLAlchemy ORM models for every table in the Study Rescue database.

All tables have `id` (integer primary key) and `created_at`.
Every table holding user data has `user_id` with a foreign key to `users`.
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Date,
    Boolean, ForeignKey, Index, func,
)
from sqlalchemy.orm import relationship
from app.db import Base


# ── Users ────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    import_batches = relationship("ImportBatch", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    extraction_runs = relationship("ExtractionRun", back_populates="user", cascade="all, delete-orphan")
    candidates = relationship("Candidate", back_populates="user", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")


# ── User Settings ────────────────────────────────────────────────────

class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    free_hours_per_day = Column(Float, nullable=False, default=3.0)
    free_days = Column(String(100), nullable=False, default="Mon,Tue,Wed,Thu,Fri,Sat,Sun")
    overrun_min_samples = Column(Integer, nullable=False, default=5)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="settings")


# ── Import Batches ───────────────────────────────────────────────────

class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    message_count = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="parsed")  # parsed | extracting | done | failed
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="import_batches")
    messages = relationship("Message", back_populates="batch", cascade="all, delete-orphan")
    extraction_runs = relationship("ExtractionRun", back_populates="batch", cascade="all, delete-orphan")


# ── Messages ─────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    sent_at = Column(DateTime, nullable=True)
    sender_alias = Column(String(50), nullable=True)
    text = Column(Text, nullable=False)
    line_no = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    batch = relationship("ImportBatch", back_populates="messages")
    user = relationship("User", back_populates="messages")
    candidates = relationship("Candidate", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_messages_user_id", "user_id"),
        Index("ix_messages_batch_id", "batch_id"),
    )


# ── Extraction Runs ─────────────────────────────────────────────────

class ExtractionRun(Base):
    __tablename__ = "extraction_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(100), nullable=True)
    prompt_version = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="ok")  # ok | failed
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    batch = relationship("ImportBatch", back_populates="extraction_runs")
    user = relationship("User", back_populates="extraction_runs")
    candidates = relationship("Candidate", back_populates="run", cascade="all, delete-orphan")


# ── Candidates ───────────────────────────────────────────────────────

class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    run_id = Column(Integer, ForeignKey("extraction_runs.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(20), nullable=False)       # assignment | exam | submission | other
    title = Column(String(200), nullable=False)
    subject = Column(String(100), nullable=True)
    deadline_text = Column(String(200), nullable=True)
    deadline_date = Column(Date, nullable=True)
    deadline_flag = Column(String(20), nullable=False, default="ok")  # ok | ambiguous | unresolved
    estimated_hours = Column(Float, nullable=True)
    certainty = Column(String(20), nullable=False, default="unclear")  # definite | probable | unclear
    quote = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")  # pending | confirmed | dismissed
    suppressed_reason = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="candidates")
    message = relationship("Message", back_populates="candidates")
    run = relationship("ExtractionRun", back_populates="candidates")
    task = relationship("Task", back_populates="candidate", uselist=False)

    __table_args__ = (
        Index("ix_candidates_user_id", "user_id"),
        Index("ix_candidates_user_status", "user_id", "status"),
    )


# ── Tasks ────────────────────────────────────────────────────────────

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(Integer, ForeignKey("candidates.id", ondelete="SET NULL"), nullable=True)
    source = Column(String(20), nullable=False, default="manual")  # extracted | manual
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    subject = Column(String(100), nullable=True)
    kind = Column(String(20), nullable=True)
    deadline = Column(Date, nullable=True)
    estimated_hours = Column(Float, nullable=True)
    actual_hours = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | in_progress | completed | cancelled
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="tasks")
    candidate = relationship("Candidate", back_populates="task")
    history = relationship("TaskHistory", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tasks_user_id", "user_id"),
        Index("ix_tasks_user_status", "user_id", "status"),
        Index("ix_tasks_user_deadline", "user_id", "deadline"),
    )


# ── Task History ─────────────────────────────────────────────────────

class TaskHistory(Base):
    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event = Column(String(30), nullable=False)  # created | updated | started | completed | cancelled | deadline_changed
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    task = relationship("Task", back_populates="history")
