"""Claim lifecycle (Roles & Access specification, sections 3-4; Phase D).

- claims.work_state: open, pending_completion (marked complete, waiting for a reviewer) or closed
- claims.priority: low, normal, high or urgent
- claims.returned and the latest step (who, when, why); every step is also in the audit log
- claims.close: approve completion, return for correction, continue follow-up, close and reopen
  (Portal Owner, Organization Admin, Operations Manager, Practice Manager / AR Lead)
- claims.prioritize: set claim priority (the same roles, plus AR Team Lead)

Revision ID: 0008
Revises: 0007
Created: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MANAGERS = ("system_admin", "org_admin", "ar_manager", "ar_lead")
PERMISSIONS = [
    ("claims.close", "Approve completion, return for correction, close and reopen claims", MANAGERS),
    ("claims.prioritize", "Set claim priority", (*MANAGERS, "team_lead")),
]


def upgrade() -> None:
    op.add_column(
        "claims", sa.Column("work_state", sa.Text(), server_default="open", nullable=False), schema="ar"
    )
    op.add_column(
        "claims", sa.Column("priority", sa.Text(), server_default="normal", nullable=False), schema="ar"
    )
    op.add_column(
        "claims", sa.Column("returned", sa.Boolean(), server_default="false", nullable=False), schema="ar"
    )
    op.add_column("claims", sa.Column("completion_requested_by", sa.Uuid(), nullable=True), schema="ar")
    op.add_column("claims", sa.Column("state_changed_by", sa.Uuid(), nullable=True), schema="ar")
    op.add_column(
        "claims", sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True), schema="ar"
    )
    op.add_column("claims", sa.Column("state_reason", sa.Text(), nullable=True), schema="ar")
    op.create_index(op.f("ix_claims_work_state"), "claims", ["work_state"], unique=False, schema="ar")
    op.create_foreign_key(
        op.f("fk_claims_state_changed_by_users"),
        "claims",
        "users",
        ["state_changed_by"],
        ["id"],
        source_schema="ar",
        referent_schema="ar",
    )
    op.create_foreign_key(
        op.f("fk_claims_completion_requested_by_users"),
        "claims",
        "users",
        ["completion_requested_by"],
        ["id"],
        source_schema="ar",
        referent_schema="ar",
    )
    op.create_check_constraint(
        "ck_claims_work_state_valid",
        "claims",
        "work_state IN ('open', 'pending_completion', 'closed')",
        schema="ar",
    )
    op.create_check_constraint(
        "ck_claims_priority_valid", "claims", "priority IN ('low', 'normal', 'high', 'urgent')", schema="ar"
    )
    for key, description, roles in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO ar.permissions (key, module, description) VALUES (:k, 'claims', :d)"
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
    op.execute("DELETE FROM ar.permissions WHERE key IN ('claims.close', 'claims.prioritize')")
    op.drop_constraint("ck_claims_priority_valid", "claims", schema="ar", type_="check")
    op.drop_constraint("ck_claims_work_state_valid", "claims", schema="ar", type_="check")
    op.drop_constraint(
        op.f("fk_claims_completion_requested_by_users"), "claims", schema="ar", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_claims_state_changed_by_users"), "claims", schema="ar", type_="foreignkey")
    op.drop_index(op.f("ix_claims_work_state"), table_name="claims", schema="ar")
    op.drop_column("claims", "state_reason", schema="ar")
    op.drop_column("claims", "state_changed_at", schema="ar")
    op.drop_column("claims", "state_changed_by", schema="ar")
    op.drop_column("claims", "completion_requested_by", schema="ar")
    op.drop_column("claims", "returned", schema="ar")
    op.drop_column("claims", "priority", schema="ar")
    op.drop_column("claims", "work_state", schema="ar")
