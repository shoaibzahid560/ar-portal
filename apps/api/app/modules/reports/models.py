import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt

EXPORT_FORMATS = ("csv", "xlsx", "pdf")


class ReportExport(CreatedAt, Base):
    """
    One generated report file (brief section 10): which report, the filters and practice scope it was run
    with, who generated it, the file, and every download. The filters hold no patient details, only choices.
    """

    __tablename__ = "report_exports"
    __table_args__ = (CheckConstraint(f"format IN {EXPORT_FORMATS}", name="format_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    number: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    report_key: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(Text)
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    scope: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    row_count: Mapped[int] = mapped_column(Integer, server_default="0")
    file_name: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    file_size: Mapped[int] = mapped_column(Integer, server_default="0")
    contains_phi: Mapped[bool] = mapped_column(server_default="false")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    download_count: Mapped[int] = mapped_column(Integer, server_default="0")
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSetting(Base):
    """A named group of settings stored as JSON, e.g. the report targets (management decision #7)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
