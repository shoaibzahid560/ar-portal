"""Reports and exports (M6).

- report_exports: every generated report file, with its filters, practice scope, requester and downloads
- app_settings: named settings; seeded with the report targets (management decision #7)
- reports.view: run reports and see report dashboards within scope
- reports.export: download reports as CSV, Excel or PDF
- reports.staff: staff productivity reports (an elevated permission when given as a grant)

Revision ID: 0009
Revises: 0008
Created: 2026-11-06
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

READERS = ("system_admin", "org_admin", "management", "ar_manager", "ar_lead", "auditor")
PERMISSIONS = [
    ("reports.view", "Run reports and see report dashboards within your scope", (*READERS, "team_lead")),
    ("reports.export", "Download reports as CSV, Excel or PDF (every download is logged)", READERS),
    (
        "reports.staff",
        "See staff productivity reports",
        ("system_admin", "org_admin", "management", "ar_manager"),
    ),
]
DEFAULT_TARGETS = {
    "claims_worked_per_day": 25,
    "first_pass_quality_pct": 90,
    "overdue_followups_per_person": 10,
    "aging_over_90_pct": 20,
    "export_retention_days": 7,
}


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
        "app_settings",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["ar.users.id"], name=op.f("fk_app_settings_updated_by_users")
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
        schema="ar",
    )
    op.create_table(
        "report_exports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("number", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("report_key", sa.Text(), nullable=False),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column(
            "filters",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), server_default="0", nullable=False),
        sa.Column("contains_phi", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("download_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("format IN ('csv', 'xlsx', 'pdf')", name=op.f("ck_report_exports_format_valid")),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["ar.users.id"], name=op.f("fk_report_exports_requested_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_exports")),
        sa.UniqueConstraint("number", name=op.f("uq_report_exports_number")),
        schema="ar",
    )
    op.create_index(
        op.f("ix_report_exports_requested_by"), "report_exports", ["requested_by"], unique=False, schema="ar"
    )
    _lock_down(["report_exports", "app_settings"])
    op.execute(
        sa.text(
            "INSERT INTO ar.app_settings (key, value) VALUES ('report_targets', CAST(:v AS jsonb))"
        ).bindparams(v=json.dumps(DEFAULT_TARGETS))
    )
    for key, description, roles in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO ar.permissions (key, module, description) VALUES (:k, 'reports', :d)"
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
    op.execute("DELETE FROM ar.permissions WHERE key IN ('reports.view', 'reports.export', 'reports.staff')")
    op.drop_index(op.f("ix_report_exports_requested_by"), table_name="report_exports", schema="ar")
    op.drop_table("report_exports", schema="ar")
    op.drop_table("app_settings", schema="ar")
