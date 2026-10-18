"""
Batch service – Pure business logic for managing message import batches.

Every function operates strictly in the scope of a specific user_id.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, distinct, func

from app.models import ImportBatch, Message
from app.ingest.whatsapp_parser import ParsedMessage


def create_batch(
    db: Session,
    user_id: int,
    source_name: str,
    messages: list[ParsedMessage],
) -> ImportBatch:
    """
    Creates an import_batches record and associated messages records.
    Every message row is stamped with user_id and batch_id.
    """
    batch = ImportBatch(
        user_id=user_id,
        source_name=source_name.strip() if source_name else "Pasted Text",
        message_count=len(messages),
        status="parsed",
    )
    db.add(batch)
    db.flush()

    for m in messages:
        msg = Message(
            batch_id=batch.id,
            user_id=user_id,
            sent_at=m.sent_at,
            sender_alias=m.sender_alias,
            text=m.text,
            line_no=m.line_no,
        )
        db.add(msg)

    db.commit()
    db.refresh(batch)
    return batch


def list_batches(db: Session, user_id: int) -> list[ImportBatch]:
    """Retrieves all batches imported by this user, newest first."""
    stmt = (
        select(ImportBatch)
        .where(ImportBatch.user_id == user_id)
        .order_by(ImportBatch.id.desc())
    )
    return list(db.scalars(stmt).all())


def get_batch(db: Session, user_id: int, batch_id: int) -> ImportBatch | None:
    """
    Retrieves a single batch strictly filtered by user_id.
    Returns None if the batch does not exist or belongs to another user.
    """
    stmt = select(ImportBatch).where(
        ImportBatch.id == batch_id,
        ImportBatch.user_id == user_id,
    )
    return db.scalar(stmt)


def get_batch_messages(
    db: Session,
    user_id: int,
    batch_id: int,
    limit: int | None = None,
) -> list[Message]:
    """Retrieves messages for a batch strictly filtered by user_id."""
    stmt = (
        select(Message)
        .where(Message.batch_id == batch_id, Message.user_id == user_id)
        .order_by(Message.line_no.asc(), Message.id.asc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt).all())


def get_batch_summary(db: Session, user_id: int, batch_id: int) -> dict | None:
    """Computes metadata and metrics for an imported batch."""
    batch = get_batch(db, user_id, batch_id)
    if not batch:
        return None

    # Count distinct senders
    senders_stmt = select(func.count(distinct(Message.sender_alias))).where(
        Message.batch_id == batch_id, Message.user_id == user_id
    )
    sender_count = db.scalar(senders_stmt) or 0

    # Date range
    min_date_stmt = select(func.min(Message.sent_at)).where(
        Message.batch_id == batch_id, Message.user_id == user_id
    )
    max_date_stmt = select(func.max(Message.sent_at)).where(
        Message.batch_id == batch_id, Message.user_id == user_id
    )
    earliest_date = db.scalar(min_date_stmt)
    latest_date = db.scalar(max_date_stmt)

    preview_messages = get_batch_messages(db, user_id, batch_id, limit=10)

    return {
        "batch": batch,
        "message_count": batch.message_count,
        "sender_count": sender_count,
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "preview_messages": preview_messages,
    }


def delete_batch(db: Session, user_id: int, batch_id: int) -> bool:
    """Deletes an import batch and all its associated messages (via cascade)."""
    batch = get_batch(db, user_id, batch_id)
    if not batch:
        return False

    db.delete(batch)
    db.commit()
    return True
