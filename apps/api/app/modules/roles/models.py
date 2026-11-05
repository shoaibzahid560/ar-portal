import uuid

from sqlalchemy import BigInteger, ForeignKey, Identity, Index, SmallInteger, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt


class Role(CreatedAt, Base):
    """
    A role from the Roles & Access specification. Seeded by migration. Each user has one primary role
    (users.role_id) and may hold additional roles, for all their practices or for one practice.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(SmallInteger, Identity(), primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")


class Permission(Base):
    """A single action, namespaced by module (users.manage, claims.assign, ...)."""

    __tablename__ = "permissions"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    module: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)


class RolePermission(Base):
    """The configurable permission matrix: which role may do which action."""

    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_key: Mapped[str] = mapped_column(
        ForeignKey("permissions.key", ondelete="CASCADE"), primary_key=True
    )


class UserRole(CreatedAt, Base):
    """
    An additional role for a user, on top of their primary role. With a practice, it applies in that
    practice only (e.g. AR Associate everywhere, but Practice Manager / AR Lead in Practice A); without one,
    it applies in all the practices the user is assigned to.
    """

    __tablename__ = "user_roles"
    __table_args__ = (
        Index(
            "uq_user_roles_everywhere",
            "user_id",
            "role_id",
            unique=True,
            postgresql_where=text("practice_id IS NULL"),
        ),
        Index(
            "uq_user_roles_practice",
            "user_id",
            "role_id",
            "practice_id",
            unique=True,
            postgresql_where=text("practice_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    practice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("practices.id", ondelete="CASCADE"))
