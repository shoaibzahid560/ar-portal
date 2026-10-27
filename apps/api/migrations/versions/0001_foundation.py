"""Foundation: users, roles, permissions, practices, teams, sessions, audit log.

Also seeds the six roles and the platform permissions, and adds three protections:
- every table lives in the `ar` schema, which Supabase's Data API does not publish;
- Row Level Security is on for every table, and Supabase's API roles get no access to the schema;
- audit_events is append-only: a trigger rejects UPDATE, DELETE and TRUNCATE.

Revision ID: 0001
Revises:
Created: 2026-10-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ar"

TABLES = [
    "roles",
    "permissions",
    "role_permissions",
    "users",
    "practices",
    "teams",
    "user_practices",
    "team_members",
    "sessions",
    "audit_events",
]

ROLES = [
    ("system_admin", "System Administrator", "Configures users, roles, permissions, practices and settings."),
    ("management", "Management", "Company-wide reports, uploads, assignments and audit. No configuration."),
    ("ar_manager", "AR Manager", "Reviews work queues and assigns claims within their teams and practices."),
    ("ar_lead", "AR Lead / Import Officer", "Uploads Dentrix reports and resolves import issues."),
    ("ar_associate", "AR Associate", "Works their own assigned claims only."),
    ("auditor", "Auditor", "Read-only access to explicitly scoped timelines, logs and reports."),
]

PERMISSIONS = [
    ("dashboard.view", "dashboard", "See the dashboard"),
    ("users.view", "users", "See employees within scope"),
    ("users.manage", "users", "Create, edit and deactivate employees"),
    ("practices.view", "practices", "See practices and teams within scope"),
    ("practices.manage", "practices", "Create and edit practices"),
    ("teams.manage", "practices", "Create and edit teams"),
    ("roles.manage", "roles", "Edit the role and permission matrix"),
    ("audit.view", "audit", "See the audit log"),
    ("settings.manage", "settings", "Change system settings"),
]

# Starting matrix from the build guideline (section 11.3). Editable later by a System Administrator.
ROLE_PERMISSIONS = {
    "system_admin": [key for key, _, _ in PERMISSIONS],
    "management": ["dashboard.view", "users.view", "practices.view", "audit.view"],
    "ar_manager": ["dashboard.view", "users.view", "practices.view"],
    "ar_lead": ["dashboard.view", "practices.view"],
    "ar_associate": ["dashboard.view"],
    "auditor": ["dashboard.view", "practices.view", "audit.view"],
}


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _updated_at() -> sa.Column:
    return sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "roles",
        sa.Column("id", sa.SmallInteger(), sa.Identity(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_roles")),
        sa.UniqueConstraint("key", name=op.f("uq_roles_key")),
        schema=SCHEMA,
    )
    op.create_table(
        "permissions",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("module", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_permissions")),
        schema=SCHEMA,
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.Column("permission_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["role_id"],
            [f"{SCHEMA}.roles.id"],
            name=op.f("fk_role_permissions_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["permission_key"],
            [f"{SCHEMA}.permissions.key"],
            name=op.f("fk_role_permissions_permission_key_permissions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("role_id", "permission_key", name=op.f("pk_role_permissions")),
        schema=SCHEMA,
    )
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("employee_code", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("role_id", sa.SmallInteger(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'deactivated')", name=op.f("ck_users_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], [f"{SCHEMA}.roles.id"], name=op.f("fk_users_role_id_roles"), ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("employee_code", name=op.f("uq_users_employee_code")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_users_role_id"), "users", ["role_id"], schema=SCHEMA)

    op.create_table(
        "practices",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        _created_at(),
        _updated_at(),
        sa.CheckConstraint("status IN ('active', 'paused')", name=op.f("ck_practices_status_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_practices")),
        sa.UniqueConstraint("name", name=op.f("uq_practices_name")),
        schema=SCHEMA,
    )
    op.create_table(
        "teams",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=True),
        sa.Column("manager_user_id", sa.Uuid(), nullable=True),
        _created_at(),
        _updated_at(),
        sa.ForeignKeyConstraint(
            ["manager_user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_teams_manager_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            [f"{SCHEMA}.practices.id"],
            name=op.f("fk_teams_practice_id_practices"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
        sa.UniqueConstraint("practice_id", "name", name=op.f("uq_teams_practice_id_name")),
        schema=SCHEMA,
    )
    op.create_table(
        "user_practices",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            [f"{SCHEMA}.practices.id"],
            name=op.f("fk_user_practices_practice_id_practices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_user_practices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "practice_id", name=op.f("pk_user_practices")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_user_practices_practice_id"), "user_practices", ["practice_id"], schema=SCHEMA)

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["team_id"],
            [f"{SCHEMA}.teams.id"],
            name=op.f("fk_team_members_team_id_teams"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{SCHEMA}.users.id"],
            name=op.f("fk_team_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("team_id", "user_id", name=op.f("pk_team_members")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_team_members_user_id"), "team_members", ["user_id"], schema=SCHEMA)

    op.create_table(
        "sessions",
        _uuid_pk(),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], name=op.f("fk_sessions_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessions_token_hash")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], schema=SCHEMA)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], [f"{SCHEMA}.users.id"], name=op.f("fk_audit_events_actor_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"], [f"{SCHEMA}.practices.id"], name=op.f("fk_audit_events_practice_id_practices")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_audit_events_occurred_at"), "audit_events", ["occurred_at"], schema=SCHEMA)
    op.create_index(op.f("ix_audit_events_actor_user_id"), "audit_events", ["actor_user_id"], schema=SCHEMA)
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"], schema=SCHEMA)

    _seed_roles_and_permissions()
    _make_audit_log_append_only()
    _lock_down_schema()


def _seed_roles_and_permissions() -> None:
    roles = sa.table("roles", sa.column("key"), sa.column("name"), sa.column("description"), schema=SCHEMA)
    permissions = sa.table(
        "permissions", sa.column("key"), sa.column("module"), sa.column("description"), schema=SCHEMA
    )
    op.bulk_insert(roles, [{"key": k, "name": n, "description": d} for k, n, d in ROLES])
    op.bulk_insert(permissions, [{"key": k, "module": m, "description": d} for k, m, d in PERMISSIONS])

    pairs = ", ".join(f"('{role}', '{perm}')" for role, perms in ROLE_PERMISSIONS.items() for perm in perms)
    op.execute(
        f"""
        INSERT INTO {SCHEMA}.role_permissions (role_id, permission_key)
        SELECT r.id, v.permission_key
        FROM (VALUES {pairs}) AS v(role_key, permission_key)
        JOIN {SCHEMA}.roles r ON r.key = v.role_key
        """
    )


def _make_audit_log_append_only() -> None:
    op.execute(
        f"""
        CREATE FUNCTION {SCHEMA}.reject_audit_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only: % is not allowed', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER audit_events_no_update_or_delete
        BEFORE UPDATE OR DELETE ON {SCHEMA}.audit_events
        FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.reject_audit_change()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON {SCHEMA}.audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION {SCHEMA}.reject_audit_change()
        """
    )


def _lock_down_schema() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
    # Supabase's Data API roles. They do not exist in a plain PostgreSQL (tests, CI), hence the check.
    op.execute(
        f"""
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON SCHEMA {SCHEMA} FROM %I', api_role);
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM %I', api_role);
                END IF;
            END LOOP;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS audit_events_no_truncate ON {SCHEMA}.audit_events")
    op.execute(f"DROP TRIGGER IF EXISTS audit_events_no_update_or_delete ON {SCHEMA}.audit_events")
    op.execute(f"DROP FUNCTION IF EXISTS {SCHEMA}.reject_audit_change()")
    for table in reversed(TABLES):
        op.drop_table(table, schema=SCHEMA)
