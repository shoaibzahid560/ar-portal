import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt


class Notification(CreatedAt, Base):
    """
    One message for one person, with a link to the record it's about. Titles name claims and uploads by
    number only, never by patient, so a notification can be read over someone's shoulder.
    """

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Prevents the same reminder twice (e.g. one "follow-up due" per claim and date).
    dedupe_key: Mapped[str | None] = mapped_column(Text, unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
