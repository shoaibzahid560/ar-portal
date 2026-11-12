"""Client reporting (Roles & Access specification, sections 2-5 and 7).

- client_organisations, with the practices they own and the reports approved for them
- users.client_org_id: client accounts belong to exactly one client organisation
- roles: Client Reporting Admin and Client Reporting User (a separate branch, outside the internal roles)
- clients.manage (portal team), client_reports.view and client_reports.download (client accounts),
  client_users.manage (client admins, effective only when the portal team delegates it)

Decisions (management): client staff sign in with Google, invitation only; patient names off by default per
client; client admins manage their own users only when delegated; first catalogue: AR statement, aging
summary, recovery summary.

Revision ID: 0010
Revises: 0009
Created: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES = [
    (
        "client_admin",
        "Client Reporting Admin",
        "A client's lead contact: approved reports for their organisation.",
    ),
    (
        "client_user",
        "Client Reporting User",
        "Client staff: approved reports for their assigned practices, read-only.",
    ),
]
PERMISSIONS = [
    (
        "clients.manage",
        "Manage client organisations, their practices, reports and accounts",
        ("system_admin", "org_admin"),
    ),
    (
        "client_reports.view",
        "Run the reports approved for your client organisation",
        ("client_admin", "client_user"),
    ),
    (
        "client_reports.download",
        "Download approved client reports (every download is logged)",
        ("client_admin", "client_user"),
    ),
    (
        "client_users.manage",
        "Manage your organisation's client users, when the portal team allows it",
        ("client_admin",),
    ),
]


def _lock_down(tables: list[str]) -> None:
    for table in tables:
        op.execute(f"ALTER TABLE ar.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA ar FROM %I', api_role);
                END IF;
            END LOOP;
        END
        $$
        """
    )


def upgrade() -> None:
    op.create_table(
        "client_organisations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="active", nullable=False),
        sa.Column("notes", sa.Text(), server_default="", nullable=False),
        sa.Column("patient_detail", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("users_delegated", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'paused')", name=op.f("ck_client_organisations_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_organisations")),
        sa.UniqueConstraint("name", name=op.f("uq_client_organisations_name")),
        schema="ar",
    )
    op.create_table(
        "client_org_practices",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["ar.client_organisations.id"],
            name=op.f("fk_client_org_practices_org_id_client_organisations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["ar.practices.id"],
            name=op.f("fk_client_org_practices_practice_id_practices"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("org_id", "practice_id", name=op.f("pk_client_org_practices")),
        schema="ar",
    )
    op.create_table(
        "client_org_reports",
        sa.Column("org_id", sa.Uuid(), nullable=False),
        sa.Column("report_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["ar.client_organisations.id"],
            name=op.f("fk_client_org_reports_org_id_client_organisations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("org_id", "report_key", name=op.f("pk_client_org_reports")),
        schema="ar",
    )
    op.add_column("users", sa.Column("client_org_id", sa.Uuid(), nullable=True), schema="ar")
    op.create_index(op.f("ix_users_client_org_id"), "users", ["client_org_id"], unique=False, schema="ar")
    op.create_foreign_key(
        op.f("fk_users_client_org_id_client_organisations"),
        "users",
        "client_organisations",
        ["client_org_id"],
        ["id"],
        source_schema="ar",
        referent_schema="ar",
        ondelete="RESTRICT",
    )
    _lock_down(["client_organisations", "client_org_practices", "client_org_reports"])
    for key, name, description in ROLES:
        op.execute(
            sa.text("INSERT INTO ar.roles (key, name, description) VALUES (:k, :n, :d)").bindparams(
                k=key, n=name, d=description
            )
        )
    for key, description, roles in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO ar.permissions (key, module, description) VALUES (:k, 'clients', :d)"
            ).bindparams(k=key, d=description)
        )
        role_list = ", ".join(f"'{r}'" for r in roles)
        op.execute(
            sa.text(
                f"INSERT INTO ar.role_permissions (role_id, permission_key) "
                f"SELECT id, :k FROM ar.roles WHERE key IN ({role_list})"
            ).bindparams(k=key)
        )


def downgrade() -> None:
    # Client accounts stay (the audit log refers to them), deactivated and with the least-privileged role.
    op.execute(
        "UPDATE ar.users SET status = 'deactivated', "
        "role_id = (SELECT id FROM ar.roles WHERE key = 'ar_associate') WHERE client_org_id IS NOT NULL"
    )
    keys = ", ".join(f"'{k}'" for k, _, _ in PERMISSIONS)
    op.execute(f"DELETE FROM ar.permissions WHERE key IN ({keys})")
    op.execute("DELETE FROM ar.roles WHERE key IN ('client_admin', 'client_user')")
    op.drop_constraint(
        op.f("fk_users_client_org_id_client_organisations"), "users", schema="ar", type_="foreignkey"
    )
    op.drop_index(op.f("ix_users_client_org_id"), table_name="users", schema="ar")
    op.drop_column("users", "client_org_id", schema="ar")
    op.drop_table("client_org_reports", schema="ar")
    op.drop_table("client_org_practices", schema="ar")
    op.drop_table("client_organisations", schema="ar")
