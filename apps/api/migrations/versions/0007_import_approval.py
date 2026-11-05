"""Import preview and approval (Roles & Access specification, section 6; Phase C).

- upload_rows: each valid line of an upload, held for the preview with its classification (new, already in
  the system, possible change to an existing claim, repeated in the file) and the reviewer's decision
- claim_prints: lines decided to belong to an existing claim, so later sheets recognise them
- uploads: preview and outcome counts, who submitted, who approved or rejected, reversal details, and a
  file-name check against the practice; statuses preview, submitted, committed, rejected, discarded, reversed
  (existing completed uploads become committed)
- claims.withdrawn_at: claims taken out when the upload that created them is reversed
- practices.import_code: how the practice's AR sheets are named, for the file-name check
- uploads.commit (approve and commit a batch) and uploads.reverse (undo a committed batch)

Revision ID: 0007
Revises: 0006
Created: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_STATUSES = (
    "processing",
    "preview",
    "submitted",
    "committed",
    "rejected",
    "discarded",
    "reversed",
    "failed",
)
OLD_STATUSES = ("processing", "completed", "failed")
PERMISSIONS = [
    (
        "uploads.commit",
        "Approve and commit an upload someone else submitted",
        ("system_admin", "org_admin", "ar_manager", "ar_lead"),
    ),
    (
        "uploads.reverse",
        "Reverse a committed upload, when none of its claims has been worked",
        ("system_admin", "org_admin"),
    ),
]


def upgrade() -> None:
    op.create_table(
        "claim_prints",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["ar.claims.id"], name=op.f("fk_claim_prints_claim_id_claims"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"], ["ar.practices.id"], name=op.f("fk_claim_prints_practice_id_practices")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"], ["ar.uploads.id"], name=op.f("fk_claim_prints_upload_id_uploads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim_prints")),
        sa.UniqueConstraint(
            "practice_id", "fingerprint", name=op.f("uq_claim_prints_practice_id_fingerprint")
        ),
        schema="ar",
    )
    op.create_index(op.f("ix_claim_prints_claim_id"), "claim_prints", ["claim_id"], unique=False, schema="ar")
    op.create_index(
        op.f("ix_claim_prints_upload_id"), "claim_prints", ["upload_id"], unique=False, schema="ar"
    )
    op.create_table(
        "upload_rows",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("classification", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column(
            "match_claim_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("target_claim_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_claim_id", sa.Uuid(), nullable=True),
        sa.Column("previous", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "classification IN ('new', 'duplicate', 'changed', 'repeat')",
            name=op.f("ck_upload_rows_classification_valid"),
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('create', 'update', 'skip')",
            name=op.f("ck_upload_rows_decision_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["ar.users.id"], name=op.f("fk_upload_rows_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["result_claim_id"], ["ar.claims.id"], name=op.f("fk_upload_rows_result_claim_id_claims")
        ),
        sa.ForeignKeyConstraint(
            ["target_claim_id"], ["ar.claims.id"], name=op.f("fk_upload_rows_target_claim_id_claims")
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["ar.uploads.id"],
            name=op.f("fk_upload_rows_upload_id_uploads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_rows")),
        schema="ar",
    )
    op.create_index(op.f("ix_upload_rows_upload_id"), "upload_rows", ["upload_id"], unique=False, schema="ar")
    op.add_column("claims", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True), schema="ar")
    op.add_column("practices", sa.Column("import_code", sa.Text(), nullable=True), schema="ar")
    op.add_column(
        "uploads", sa.Column("new_rows", sa.Integer(), server_default="0", nullable=False), schema="ar"
    )
    op.add_column(
        "uploads", sa.Column("changed_rows", sa.Integer(), server_default="0", nullable=False), schema="ar"
    )
    op.add_column(
        "uploads", sa.Column("repeat_rows", sa.Integer(), server_default="0", nullable=False), schema="ar"
    )
    op.add_column(
        "uploads", sa.Column("updated_claims", sa.Integer(), server_default="0", nullable=False), schema="ar"
    )
    op.add_column(
        "uploads", sa.Column("skipped_rows", sa.Integer(), server_default="0", nullable=False), schema="ar"
    )
    op.add_column("uploads", sa.Column("mapping_warning", sa.Text(), nullable=True), schema="ar")
    op.add_column("uploads", sa.Column("submitted_by", sa.Uuid(), nullable=True), schema="ar")
    op.add_column(
        "uploads", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True), schema="ar"
    )
    op.add_column("uploads", sa.Column("decided_by", sa.Uuid(), nullable=True), schema="ar")
    op.add_column("uploads", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True), schema="ar")
    op.add_column("uploads", sa.Column("decision_reason", sa.Text(), nullable=True), schema="ar")
    op.add_column("uploads", sa.Column("reversed_by", sa.Uuid(), nullable=True), schema="ar")
    op.add_column("uploads", sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True), schema="ar")
    op.add_column("uploads", sa.Column("reverse_reason", sa.Text(), nullable=True), schema="ar")
    op.create_foreign_key(
        op.f("fk_uploads_submitted_by_users"),
        "uploads",
        "users",
        ["submitted_by"],
        ["id"],
        source_schema="ar",
        referent_schema="ar",
    )
    op.create_foreign_key(
        op.f("fk_uploads_reversed_by_users"),
        "uploads",
        "users",
        ["reversed_by"],
        ["id"],
        source_schema="ar",
        referent_schema="ar",
    )
    op.create_foreign_key(
        op.f("fk_uploads_decided_by_users"),
        "uploads",
        "users",
        ["decided_by"],
        ["id"],
        source_schema="ar",
        referent_schema="ar",
    )
    _statuses(NEW_STATUSES, rename=("completed", "committed"))
    _lock_down(["upload_rows", "claim_prints"])
    _permissions()


def downgrade() -> None:
    op.execute("DELETE FROM ar.permissions WHERE key IN ('uploads.commit', 'uploads.reverse')")
    _statuses(OLD_STATUSES, rename=("committed", "completed"), fallback="failed")
    op.drop_constraint(op.f("fk_uploads_decided_by_users"), "uploads", schema="ar", type_="foreignkey")
    op.drop_constraint(op.f("fk_uploads_reversed_by_users"), "uploads", schema="ar", type_="foreignkey")
    op.drop_constraint(op.f("fk_uploads_submitted_by_users"), "uploads", schema="ar", type_="foreignkey")
    op.drop_column("uploads", "reverse_reason", schema="ar")
    op.drop_column("uploads", "reversed_at", schema="ar")
    op.drop_column("uploads", "reversed_by", schema="ar")
    op.drop_column("uploads", "decision_reason", schema="ar")
    op.drop_column("uploads", "decided_at", schema="ar")
    op.drop_column("uploads", "decided_by", schema="ar")
    op.drop_column("uploads", "submitted_at", schema="ar")
    op.drop_column("uploads", "submitted_by", schema="ar")
    op.drop_column("uploads", "mapping_warning", schema="ar")
    op.drop_column("uploads", "skipped_rows", schema="ar")
    op.drop_column("uploads", "updated_claims", schema="ar")
    op.drop_column("uploads", "repeat_rows", schema="ar")
    op.drop_column("uploads", "changed_rows", schema="ar")
    op.drop_column("uploads", "new_rows", schema="ar")
    op.drop_column("practices", "import_code", schema="ar")
    op.drop_column("claims", "withdrawn_at", schema="ar")
    op.drop_index(op.f("ix_upload_rows_upload_id"), table_name="upload_rows", schema="ar")
    op.drop_table("upload_rows", schema="ar")
    op.drop_index(op.f("ix_claim_prints_upload_id"), table_name="claim_prints", schema="ar")
    op.drop_index(op.f("ix_claim_prints_claim_id"), table_name="claim_prints", schema="ar")
    op.drop_table("claim_prints", schema="ar")


def _statuses(allowed: tuple[str, ...], *, rename: tuple[str, str], fallback: str | None = None) -> None:
    op.execute("ALTER TABLE ar.uploads DROP CONSTRAINT IF EXISTS ck_uploads_status_valid")
    old, new = rename
    op.execute(
        sa.text("UPDATE ar.uploads SET status = :new WHERE status = :old").bindparams(old=old, new=new)
    )
    if fallback:
        values = ", ".join(f"'{v}'" for v in allowed)
        op.execute(
            sa.text(f"UPDATE ar.uploads SET status = :f WHERE status NOT IN ({values})").bindparams(
                f=fallback
            )
        )
    op.execute(f"ALTER TABLE ar.uploads ADD CONSTRAINT ck_uploads_status_valid CHECK (status IN {allowed})")


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


def _permissions() -> None:
    for key, description, roles in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO ar.permissions (key, module, description) VALUES (:k, 'uploads', :d)"
            ).bindparams(k=key, d=description)
        )
        role_list = ", ".join(f"'{r}'" for r in roles)
        op.execute(
            sa.text(
                f"INSERT INTO ar.role_permissions (role_id, permission_key) "
                f"SELECT id, :k FROM ar.roles WHERE key IN ({role_list})"
            ).bindparams(k=key)
        )
