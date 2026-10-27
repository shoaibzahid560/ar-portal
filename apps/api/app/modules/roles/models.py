from sqlalchemy import ForeignKey, Identity, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm import Base, CreatedAt


class Role(CreatedAt, Base):
    """One of the six roles from the project brief. Seeded by migration; each user has exactly one."""

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
