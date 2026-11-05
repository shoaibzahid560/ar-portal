import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt

GRANT_STATUSES = ("pending", "active", "rejected", "revoked")


class PermissionGrant(CreatedAt, Base):
    """
    One extra permission for one person, on top of their roles (specification, section 4): for one practice,
    or for all their practices. Records who asked, why, who approved, and when it ends. Rows are never
    deleted; ending a grant sets its status, so the history stays complete.
    """

    __tablename__ = "permission_grants"
    __table_args__ = (CheckConstraint(f"status IN {GRANT_STATUSES}", name="status_valid"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    permission_key: Mapped[str] = mapped_column(ForeignKey("permissions.key", ondelete="CASCADE"))
    practice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("practices.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    end_reason: Mapped[str | None] = mapped_column(Text)
