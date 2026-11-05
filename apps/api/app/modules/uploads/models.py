import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt

# processing: being read. preview: checked, nothing created yet. submitted: waiting for a second person.
# committed: claims created or updated. rejected / discarded: nothing created.
# reversed: committed, then undone. failed: the file couldn't be used.
UPLOAD_STATUSES = (
    "processing",
    "preview",
    "submitted",
    "committed",
    "rejected",
    "discarded",
    "reversed",
    "failed",
)
ROW_CLASSES = ("new", "duplicate", "changed", "repeat")
ROW_DECISIONS = ("create", "update", "skip")


class Upload(CreatedAt, Base):
    """
    One uploaded AR sheet (an import batch): who, when, which practice, the file, the preview counts, who
    submitted and who approved it, and what came of it.
    """

    __tablename__ = "uploads"
    __table_args__ = (CheckConstraint(f"status IN {UPLOAD_STATUSES}", name="status_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    practice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practices.id"), index=True)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    file_name: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer)
    checksum: Mapped[str] = mapped_column(Text, index=True)
    status: Mapped[str] = mapped_column(Text, server_default="processing")
    failure_reason: Mapped[str | None] = mapped_column(Text)
    total_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    created_claims: Mapped[int] = mapped_column(Integer, server_default="0")
    duplicate_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    error_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    review_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Preview counts (before anything is created)
    new_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    changed_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    repeat_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    # Outcome counts (after commit)
    updated_claims: Mapped[int] = mapped_column(Integer, server_default="0")
    skipped_rows: Mapped[int] = mapped_column(Integer, server_default="0")
    mapping_warning: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    reversed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reverse_reason: Mapped[str | None] = mapped_column(Text)


class UploadError(Base):
    """A problem on one row. Messages describe the problem without repeating the cell's value."""

    __tablename__ = "upload_errors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)


class UploadRow(Base):
    """
    One valid line of an upload, held for the preview until the batch is committed. Lines that need a
    person's decision (a possible change to an existing claim, or a line repeated in the file) record it here.
    The line's values are cleared if the batch is rejected or discarded.
    """

    __tablename__ = "upload_rows"
    __table_args__ = (
        CheckConstraint(f"classification IN {ROW_CLASSES}", name="classification_valid"),
        CheckConstraint(f"decision IS NULL OR decision IN {ROW_DECISIONS}", name="decision_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    classification: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(Text)
    # Existing claims this line matches: the same line (duplicate) or the same visit (changed).
    match_claim_ids: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    decision: Mapped[str | None] = mapped_column(Text)
    target_claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_claim_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("claims.id"))
    # The target claim's uploaded values before an update, so a reversal can restore them.
    previous: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
