"""Imports every table so Alembic and SQLAlchemy see the complete schema. Add new modules here."""

from app.core.orm import Base
from app.modules.audit.models import AuditEvent
from app.modules.auth.models import UserSession
from app.modules.claims.models import Claim, ClaimNote
from app.modules.lists.models import OptionListItem
from app.modules.practices.models import Practice, Team, TeamMember, UserPractice
from app.modules.roles.models import Permission, Role, RolePermission
from app.modules.uploads.models import Upload, UploadError
from app.modules.users.models import User

__all__ = [
    "AuditEvent",
    "Base",
    "Claim",
    "ClaimNote",
    "OptionListItem",
    "Permission",
    "Practice",
    "Role",
    "RolePermission",
    "Team",
    "TeamMember",
    "User",
    "UserPractice",
    "Upload",
    "UploadError",
    "UserSession",
]
