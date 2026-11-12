import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt

CLIENT_STATUSES = ("active", "paused")


class ClientOrganisation(CreatedAt, Base):
    """
    A client of the AR team, such as a dental group (Roles & Access specification, section 2). Its client
    accounts see only its own practices, and only the reports the portal team approved for it.
    """

    __tablename__ = "client_organisations"
    __table_args__ = (CheckConstraint(f"status IN {CLIENT_STATUSES}", name="status_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    notes: Mapped[str] = mapped_column(Text, server_default="")
    # Off by default: client reports leave out patient names and subscriber IDs.
    patient_detail: Mapped[bool] = mapped_column(Boolean, server_default="false")
    # Off by default: only the portal team adds client users, unless delegated to the client admin.
    users_delegated: Mapped[bool] = mapped_column(Boolean, server_default="false")


class ClientOrgPractice(Base):
    """The practices a client organisation owns, and so the only practices its accounts can reach."""

    __tablename__ = "client_org_practices"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_organisations.id", ondelete="CASCADE"), primary_key=True
    )
    practice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practices.id", ondelete="CASCADE"), primary_key=True
    )


class ClientOrgReport(Base):
    """A report the portal team approved for this client (the client report catalogue)."""

    __tablename__ = "client_org_reports"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_organisations.id", ondelete="CASCADE"), primary_key=True
    )
    report_key: Mapped[str] = mapped_column(Text, primary_key=True)
