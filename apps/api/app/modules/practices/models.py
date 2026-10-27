import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt, Timestamps

PRACTICE_STATUSES = ("active", "paused")


class Practice(Timestamps, Base):
    """A dental practice whose AR the team works. Practice access limits what a user can see."""

    __tablename__ = "practices"
    __table_args__ = (CheckConstraint(f"status IN {PRACTICE_STATUSES}", name="status_valid"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="active")
    notes: Mapped[str] = mapped_column(Text, server_default="")


class Team(Timestamps, Base):
    """A group of employees led by a manager, optionally tied to one practice."""

    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("practice_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text)
    practice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("practices.id", ondelete="RESTRICT"))
    manager_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class UserPractice(CreatedAt, Base):
    """Practice scope: which practices a user can see."""

    __tablename__ = "user_practices"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    practice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("practices.id", ondelete="CASCADE"), primary_key=True, index=True
    )


class TeamMember(CreatedAt, Base):
    """Team scope: which teams a user belongs to."""

    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
