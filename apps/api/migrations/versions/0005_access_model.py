"""Access model from the Roles & Access specification (Phase A).

- user_roles: additional roles per user, for all their practices or for one practice
- the specification's roles: Organization Admin, AR Team Lead and Claim Importer are added; existing roles
  get the specification's names (keys stay the same, so nothing else changes)
- permissions that replace rules which used to be written into the code:
  scope.all_practices (sees every practice), claims.view_practice / claims.view_team / claims.view (which
  claims are visible), claims.assign (assign or reassign), claims.receive (can be assigned claims),
  users.manage_owners (manage Portal Owner accounts)
- default access per the specification; existing customisations are kept, and behaviour that existing
  users relied on is preserved (e.g. AR Leads who uploaded also get the Claim Importer role)

Revision ID: 0005
Revises: 0004
Created: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["ar.practices.id"],
            name=op.f("fk_user_roles_practice_id_practices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["ar.roles.id"], name=op.f("fk_user_roles_role_id_roles"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["ar.users.id"], name=op.f("fk_user_roles_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
        schema="ar",
    )
    op.create_index(op.f("ix_user_roles_user_id"), "user_roles", ["user_id"], unique=False, schema="ar")
    op.create_index(
        "uq_user_roles_everywhere",
        "user_roles",
        ["user_id", "role_id"],
        unique=True,
        schema="ar",
        postgresql_where=sa.text("practice_id IS NULL"),
    )
    op.create_index(
        "uq_user_roles_practice",
        "user_roles",
        ["user_id", "role_id", "practice_id"],
        unique=True,
        schema="ar",
        postgresql_where=sa.text("practice_id IS NOT NULL"),
    )
    _lock_down()
    _seed_access()


def downgrade() -> None:
    op.drop_index(
        "uq_user_roles_practice",
        table_name="user_roles",
        schema="ar",
        postgresql_where=sa.text("practice_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_user_roles_everywhere",
        table_name="user_roles",
        schema="ar",
        postgresql_where=sa.text("practice_id IS NULL"),
    )
    op.drop_index(op.f("ix_user_roles_user_id"), table_name="user_roles", schema="ar")
    op.drop_table("user_roles", schema="ar")
    _unseed_access()


NEW_ROLES = [
    (
        "org_admin",
        "Organization Admin",
        "Internal users, roles, practice access, configuration, imports, reports and audit. "
        "No owner-only settings.",
    ),
    (
        "team_lead",
        "AR Team Lead",
        "Their teams' claim queues; distributes and reassigns claims within scope.",
    ),
    (
        "claim_importer",
        "Claim Importer",
        "Uploads Dentrix files for authorized practices. No AR work or unrelated practice access.",
    ),
]

RENAMED = {
    "system_admin": (
        "Portal Owner / Super Admin",
        "All portal functions and practices, including owner-only settings.",
    ),
    "ar_manager": (
        "Operations Manager",
        "Dashboards and queues across assigned practices; assigns work; reviews activity.",
    ),
    "ar_lead": (
        "Practice Manager / AR Lead",
        "Manages assigned practices: queues, assignments, timelines, review items.",
    ),
    "auditor": (
        "Reporting Analyst / Auditor",
        "Read-only data, timelines and audit trail for the assigned scope.",
    ),
    "management": ("Management (company-wide view)", "Company-wide oversight; read-only by default."),
}
OLD_NAMES = {
    "system_admin": "System Administrator",
    "ar_manager": "AR Manager",
    "ar_lead": "AR Lead / Import Officer",
    "auditor": "Auditor / Read-only Reviewer",
    "management": "Management / Admin",
}

NEW_PERMISSIONS = [
    ("scope.all_practices", "scope", "Access every practice, without being assigned to each one"),
    ("users.manage_owners", "users", "Manage Portal Owner / Super Admin accounts (owner-only)"),
    ("claims.view_practice", "claims", "See every claim in the practices you work in"),
    ("claims.view_team", "claims", "See your teams' claims, and unassigned claims in their practices"),
    ("claims.assign", "claims", "Assign and reassign claims you can see"),
    ("claims.receive", "claims", "Can be assigned claims"),
]

NEW_ROLE_DEFAULTS = {
    "org_admin": [
        "dashboard.view",
        "scope.all_practices",
        "users.view",
        "users.manage",
        "practices.view",
        "practices.manage",
        "teams.manage",
        "settings.manage",
        "lists.manage",
        "audit.view",
        "notifications.oversight",
        "uploads.view",
        "uploads.create",
        "claims.view_practice",
        "claims.work",
        "claims.assign",
        "claims.review",
    ],
    "team_lead": [
        "dashboard.view",
        "users.view",
        "practices.view",
        "claims.view_team",
        "claims.work",
        "claims.assign",
        "claims.receive",
    ],
    "claim_importer": ["dashboard.view", "practices.view", "uploads.view", "uploads.create"],
}

# Added to existing roles. Existing customisations stay; nothing a role could do before is lost,
# except Practice Manager / AR Lead uploading, which moves to the Claim Importer role (see below).
EXISTING_ROLE_ADDITIONS = {
    "ar_manager": ["claims.view_practice", "claims.assign", "claims.receive", "teams.manage", "audit.view"],
    "ar_lead": ["claims.view_practice", "claims.assign", "claims.receive", "teams.manage"],
    "ar_associate": ["claims.assign", "claims.receive"],
    "auditor": ["uploads.view"],
    "management": ["scope.all_practices"],
}


def _lock_down() -> None:
    op.execute("ALTER TABLE ar.user_roles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON ar.user_roles FROM %I', api_role);
                END IF;
            END LOOP;
        END
        $$
        """
    )


def _grant(role_key: str, permission: str) -> None:
    op.execute(
        sa.text(
            "INSERT INTO ar.role_permissions (role_id, permission_key) "
            "SELECT id, :p FROM ar.roles WHERE key = :r ON CONFLICT DO NOTHING"
        ).bindparams(r=role_key, p=permission)
    )


def _seed_access() -> None:
    for key, name, description in NEW_ROLES:
        op.execute(
            sa.text("INSERT INTO ar.roles (key, name, description) VALUES (:k, :n, :d)").bindparams(
                k=key, n=name, d=description
            )
        )
    for key, (name, description) in RENAMED.items():
        op.execute(
            sa.text("UPDATE ar.roles SET name = :n, description = :d WHERE key = :k").bindparams(
                k=key, n=name, d=description
            )
        )
    for key, module, description in NEW_PERMISSIONS:
        op.execute(
            sa.text("INSERT INTO ar.permissions (key, module, description) VALUES (:k, :m, :d)").bindparams(
                k=key, m=module, d=description
            )
        )
    op.execute(
        "UPDATE ar.permissions SET description = 'See claims assigned to you' WHERE key = 'claims.view'"
    )
    op.execute(
        "UPDATE ar.permissions SET description = 'Work claims: statuses, amounts, dates, notes, EOB' "
        "WHERE key = 'claims.work'"
    )

    # The Portal Owner keeps every permission.
    op.execute(
        "INSERT INTO ar.role_permissions (role_id, permission_key) "
        "SELECT r.id, p.key FROM ar.roles r, ar.permissions p "
        "WHERE r.key = 'system_admin' ON CONFLICT DO NOTHING"
    )
    # ...except being assigned claims: the Portal Owner isn't offered in "Assigned to" lists.
    op.execute(
        "DELETE FROM ar.role_permissions WHERE permission_key = 'claims.receive' "
        "AND role_id = (SELECT id FROM ar.roles WHERE key = 'system_admin')"
    )
    for role_key, permissions in {**NEW_ROLE_DEFAULTS, **EXISTING_ROLE_ADDITIONS}.items():
        for permission in permissions:
            _grant(role_key, permission)

    # Keep what existing roles could do, now expressed with the new permissions.
    op.execute(
        "INSERT INTO ar.role_permissions (role_id, permission_key) "
        "SELECT rp.role_id, 'claims.view_practice' "
        "FROM ar.role_permissions rp JOIN ar.roles r ON r.id = rp.role_id "
        "WHERE rp.permission_key = 'claims.view' AND r.key <> 'ar_associate' ON CONFLICT DO NOTHING"
    )
    op.execute(
        "INSERT INTO ar.role_permissions (role_id, permission_key) "
        "SELECT role_id, 'claims.assign' FROM ar.role_permissions WHERE permission_key = 'claims.work' "
        "ON CONFLICT DO NOTHING"
    )

    # Uploading moves from Practice Manager / AR Lead to Claim Importer (specification, section 3).
    # People who are AR Leads today keep uploading: they also get the Claim Importer role.
    op.execute(
        "INSERT INTO ar.user_roles (user_id, role_id) "
        "SELECT u.id, ci.id FROM ar.users u JOIN ar.roles r ON r.id = u.role_id, ar.roles ci "
        "WHERE r.key = 'ar_lead' AND ci.key = 'claim_importer'"
    )
    op.execute(
        "DELETE FROM ar.role_permissions WHERE permission_key = 'uploads.create' "
        "AND role_id = (SELECT id FROM ar.roles WHERE key = 'ar_lead')"
    )


def _unseed_access() -> None:
    _grant("ar_lead", "uploads.create")
    keys = ", ".join(f"'{k}'" for k, _, _ in NEW_PERMISSIONS)
    op.execute(f"DELETE FROM ar.permissions WHERE key IN ({keys})")
    roles = ", ".join(f"'{k}'" for k, _, _ in NEW_ROLES)
    # People whose primary role is going away get the least-privileged role, AR Associate.
    op.execute(
        f"UPDATE ar.users SET role_id = (SELECT id FROM ar.roles WHERE key = 'ar_associate') "
        f"WHERE role_id IN (SELECT id FROM ar.roles WHERE key IN ({roles}))"
    )
    op.execute(f"DELETE FROM ar.roles WHERE key IN ({roles})")
    for key, name in OLD_NAMES.items():
        op.execute(sa.text("UPDATE ar.roles SET name = :n WHERE key = :k").bindparams(k=key, n=name))
