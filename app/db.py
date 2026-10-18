"""
Database engine, session factory and base class.
Uses a single SQLite file as specified in config.DATABASE_URL.
"""

from pathlib import Path
from sqlalchemy import create_engine, event
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


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite ignores foreign keys unless switched on for every connection
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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
    # Ensure any added columns exist in sqlite tables (e.g. is_joke_or_hypothetical in candidates)
    with engine.connect() as conn:
        try:
            cols = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(candidates)").fetchall()]
            if cols and "is_joke_or_hypothetical" not in cols:
                conn.exec_driver_sql("ALTER TABLE candidates ADD COLUMN is_joke_or_hypothetical BOOLEAN NOT NULL DEFAULT 0")
                conn.commit()
        except Exception:
            pass