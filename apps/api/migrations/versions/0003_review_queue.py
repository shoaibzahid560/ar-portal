"""Review queue: lines merged into an earlier claim, and the permission to resolve review items.

- claims.merged_into_id: a line a reviewer decided is the same claim as an earlier one
- claims.review: resolve lines that need review (System Administrator, AR Manager, AR Lead)

Revision ID: 0003
Revises: 0002
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ar"
PERMISSION = ("claims.review", "claims", "Resolve lines that need review (same claim or separate)")
ROLES = ("system_admin", "ar_manager", "ar_lead")


def upgrade() -> None:
    op.add_column("claims", sa.Column("merged_into_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.create_index(
        op.f("ix_claims_merged_into_id"), "claims", ["merged_into_id"], unique=False, schema=SCHEMA
    )
    op.create_foreign_key(
        op.f("fk_claims_merged_into_id_claims"),
        "claims",
        "claims",
        ["merged_into_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    key, module, description = PERMISSION
    op.execute(
        sa.text(
            f"INSERT INTO {SCHEMA}.permissions (key, module, description) VALUES (:k, :m, :d)"
        ).bindparams(k=key, m=module, d=description)
    )
    roles = ", ".join(f"'{r}'" for r in ROLES)
    op.execute(
        f"INSERT INTO {SCHEMA}.role_permissions (role_id, permission_key) "
        f"SELECT id, '{key}' FROM {SCHEMA}.roles WHERE key IN ({roles})"
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM {SCHEMA}.permissions WHERE key = '{PERMISSION[0]}'")
    op.drop_constraint(op.f("fk_claims_merged_into_id_claims"), "claims", schema=SCHEMA, type_="foreignkey")
    op.drop_index(op.f("ix_claims_merged_into_id"), table_name="claims", schema=SCHEMA)
    op.drop_column("claims", "merged_into_id", schema=SCHEMA)
