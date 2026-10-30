import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt, Timestamps

Money = Numeric(12, 2)


class Claim(Timestamps, Base):
    """
    One line of the AR sheet. The first block comes from the upload and is read-only in the portal;
    the second block holds the sheet's work columns, filled in by whoever works the claim.
    """

    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("practice_id", "fingerprint"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    practice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practices.id"), index=True)
    upload_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uploads.id"), index=True)
    # Identifies an uploaded line, so uploading the same line again doesn't create a second claim.
    fingerprint: Mapped[str] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, server_default="false")
    review_reason: Mapped[str | None] = mapped_column(Text)

    # From the upload
    patient_name: Mapped[str] = mapped_column(Text)
    service_date: Mapped[date] = mapped_column(Date, index=True)
    subscriber_id: Mapped[str] = mapped_column(Text)
    patient_dob: Mapped[date | None] = mapped_column(Date)
    insurance_carrier: Mapped[str] = mapped_column(Text)
    subscriber_name: Mapped[str | None] = mapped_column(Text)
    subscriber_dob: Mapped[date | None] = mapped_column(Date)
    billed: Mapped[Decimal] = mapped_column(Money)

    # The sheet's work columns
    allowed_amount: Mapped[Decimal | None] = mapped_column(Money)
    recovered_amount: Mapped[Decimal | None] = mapped_column(Money)
    patient_responsibility: Mapped[Decimal | None] = mapped_column(Money)
    claim_status: Mapped[str | None] = mapped_column(Text)
    pay_status: Mapped[str | None] = mapped_column(Text)
    check_status: Mapped[str | None] = mapped_column(Text)
    cashed_date: Mapped[date | None] = mapped_column(Date)
    action_taken: Mapped[str | None] = mapped_column(Text)
    payment_posted_date: Mapped[date | None] = mapped_column(Date)
    followup_date: Mapped[date | None] = mapped_column(Date, index=True)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    eob_storage_key: Mapped[str | None] = mapped_column(Text)
    eob_file_name: Mapped[str | None] = mapped_column(Text)
    eob_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClaimNote(CreatedAt, Base):
    """A note on a claim. Notes are added, never edited, so the history stays complete."""

    __tablename__ = "claim_notes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
