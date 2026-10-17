"""
Database engine, session factory and base class.
Uses a single SQLite file as specified in config.DATABASE_URL.
"""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import DATABASE_URL

# Ensure the data/ directory exists for the SQLite file
_db_path = DATABASE_URL.replace("sqlite:///", "")
Path(_db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # required for SQLite
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session and closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all tables defined in models.py (imported for side effects)."""
    import app.models  # noqa: F401 – registers models with Base.metadata
    Base.metadata.create_all(bind=engine)
