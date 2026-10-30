import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt

UPLOAD_STATUSES = ("processing", "completed", "failed")


class Upload(CreatedAt, Base):
    """One uploaded AR sheet: who, when, which practice, the file, and what came of it."""

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


class UploadError(Base):
    """A problem on one row. Messages describe the problem without repeating the cell's value."""

    __tablename__ = "upload_errors"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    row_number: Mapped[int] = mapped_column(Integer)
    column_name: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
