"""Additional permission grants (Roles & Access specification, section 4; Phase B).

- permission_grants: one extra permission for one person, everywhere or in one practice, with reason,
  grantor, approver, dates, optional expiry and periodic review. Rows are never deleted.
- grants.manage: give and end grants; grants.approve: approve elevated grants (a second person).
  Both for the Portal Owner and the Organization Admin by default.

Revision ID: 0006
Revises: 0005
Created: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = [
    ("grants.manage", "Give and end additional permissions for individual people"),
    ("grants.approve", "Approve elevated additional permissions requested by someone else"),
]


def upgrade() -> None:
    op.create_table(
        "permission_grants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("permission_key", sa.Text(), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", sa.Uuid(), nullable=True),
        sa.Column("end_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'rejected', 'revoked')",
            name=op.f("ck_permission_grants_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["ar.users.id"], name=op.f("fk_permission_grants_approved_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["ended_by"], ["ar.users.id"], name=op.f("fk_permission_grants_ended_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["permission_key"],
            ["ar.permissions.key"],
            name=op.f("fk_permission_grants_permission_key_permissions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["ar.practices.id"],
            name=op.f("fk_permission_grants_practice_id_practices"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"], ["ar.users.id"], name=op.f("fk_permission_grants_requested_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"], ["ar.users.id"], name=op.f("fk_permission_grants_reviewed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["ar.users.id"], name=op.f("fk_permission_grants_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_permission_grants")),
        schema="ar",
    )
    op.create_index(
        op.f("ix_permission_grants_user_id"), "permission_grants", ["user_id"], unique=False, schema="ar"
    )
    op.execute("ALTER TABLE ar.permission_grants ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON ar.permission_grants FROM %I', api_role);
                END IF;
            END LOOP;
        END
        $$
        """
    )
    for key, description in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO ar.permissions (key, module, description) VALUES (:k, 'grants', :d)"
            ).bindparams(k=key, d=description)
        )
        op.execute(
            sa.text(
                "INSERT INTO ar.role_permissions (role_id, permission_key) "
                "SELECT id, :k FROM ar.roles WHERE key IN ('system_admin', 'org_admin')"
            ).bindparams(k=key)
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_permission_grants_user_id"), table_name="permission_grants", schema="ar")
    op.drop_table("permission_grants", schema="ar")
    op.execute("DELETE FROM ar.permissions WHERE key IN ('grants.manage', 'grants.approve')")
