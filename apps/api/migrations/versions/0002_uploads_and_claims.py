"""Uploads and claims (M1): uploaded AR sheets, row errors, claims, claim notes, dropdown lists.

Seeds the four dropdowns exactly as they appear in the AR sheet, and the M1 permissions:
- uploads.view / uploads.create: see uploads; upload AR sheets for practices in scope
- claims.view: see claims (associates see only claims assigned to them)
- claims.work: fill in the work fields, add notes, attach EOBs, change who a claim is assigned to
- lists.manage: edit the dropdown lists in Settings

Revision ID: 0002
Revises: 0001
Created: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ar"
NEW_TABLES = ["option_list_items", "uploads", "upload_errors", "claims", "claim_notes"]

# Exactly as in the AR sheet's dropdowns, in the same order and spelling. Editable later in Settings.
LISTS = {
    "claim_status": [
        "Approved to pay",
        "Claim not found",
        "Claim Status",
        "Denied",
        "In- Process",
        "Paid",
        "Adjusted",
        "Pending",
        "Partially Paid",
        "Claim re-submitted",
        "Patient Responsblity",
        "Problem",
        "Paid Under Capitation",
    ],
    "pay_status": ["Paid to Patient", "Paid to Practice"],
    "check_status": ["Check Deposited", "Not issued yet", "Reissued Check", "Check Not Cashed"],
    "action_taken": [
        "Called Insurance",
        "Follow Up",
        "Patient Contacted",
        "Payment Posted",
        "Claim re-submitted",
        "Already Posted",
        "Payment post on hold",
        "Need to write-off",
        "Provider Query",
        "Writed-off",
    ],
}

PERMISSIONS = [
    ("uploads.view", "uploads", "See uploads and their results"),
    ("uploads.create", "uploads", "Upload AR sheets for practices in scope"),
    ("claims.view", "claims", "See claims (associates: only their own)"),
    ("claims.work", "claims", "Work claims: statuses, amounts, dates, notes, EOB, assignment"),
    ("lists.manage", "settings", "Edit the dropdown lists"),
]

ROLE_PERMISSIONS = {
    "system_admin": ["uploads.view", "uploads.create", "claims.view", "claims.work", "lists.manage"],
    "management": ["uploads.view", "claims.view"],
    "ar_manager": ["uploads.view", "claims.view", "claims.work"],
    "ar_lead": ["uploads.view", "uploads.create", "claims.view", "claims.work"],
    "ar_associate": ["claims.view", "claims.work"],
    "auditor": ["claims.view"],
}


def upgrade() -> None:
    op.create_table(
        "option_list_items",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("list_key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "list_key IN ('claim_status', 'pay_status', 'check_status', 'action_taken')",
            name=op.f("ck_option_list_items_list_key_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_option_list_items")),
        sa.UniqueConstraint("list_key", "value", name=op.f("uq_option_list_items_list_key_value")),
        schema="ar",
    )
    op.create_table(
        "uploads",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("number", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="processing", nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_claims", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'failed')", name=op.f("ck_uploads_status_valid")
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"], ["ar.practices.id"], name=op.f("fk_uploads_practice_id_practices")
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["ar.users.id"], name=op.f("fk_uploads_uploaded_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploads")),
        sa.UniqueConstraint("number", name=op.f("uq_uploads_number")),
        schema="ar",
    )
    op.create_index(op.f("ix_uploads_checksum"), "uploads", ["checksum"], unique=False, schema="ar")
    op.create_index(op.f("ix_uploads_practice_id"), "uploads", ["practice_id"], unique=False, schema="ar")
    op.create_table(
        "claims",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("number", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("practice_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("patient_name", sa.Text(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("subscriber_id", sa.Text(), nullable=False),
        sa.Column("patient_dob", sa.Date(), nullable=True),
        sa.Column("insurance_carrier", sa.Text(), nullable=False),
        sa.Column("subscriber_name", sa.Text(), nullable=True),
        sa.Column("subscriber_dob", sa.Date(), nullable=True),
        sa.Column("billed", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("allowed_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("recovered_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("patient_responsibility", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("claim_status", sa.Text(), nullable=True),
        sa.Column("pay_status", sa.Text(), nullable=True),
        sa.Column("check_status", sa.Text(), nullable=True),
        sa.Column("cashed_date", sa.Date(), nullable=True),
        sa.Column("action_taken", sa.Text(), nullable=True),
        sa.Column("payment_posted_date", sa.Date(), nullable=True),
        sa.Column("followup_date", sa.Date(), nullable=True),
        sa.Column("assigned_user_id", sa.Uuid(), nullable=True),
        sa.Column("eob_storage_key", sa.Text(), nullable=True),
        sa.Column("eob_file_name", sa.Text(), nullable=True),
        sa.Column("eob_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_user_id"], ["ar.users.id"], name=op.f("fk_claims_assigned_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["practice_id"], ["ar.practices.id"], name=op.f("fk_claims_practice_id_practices")
        ),
        sa.ForeignKeyConstraint(["upload_id"], ["ar.uploads.id"], name=op.f("fk_claims_upload_id_uploads")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claims")),
        sa.UniqueConstraint("number", name=op.f("uq_claims_number")),
        sa.UniqueConstraint("practice_id", "fingerprint", name=op.f("uq_claims_practice_id_fingerprint")),
        schema="ar",
    )
    op.create_index(
        op.f("ix_claims_assigned_user_id"), "claims", ["assigned_user_id"], unique=False, schema="ar"
    )
    op.create_index(op.f("ix_claims_followup_date"), "claims", ["followup_date"], unique=False, schema="ar")
    op.create_index(op.f("ix_claims_practice_id"), "claims", ["practice_id"], unique=False, schema="ar")
    op.create_index(op.f("ix_claims_service_date"), "claims", ["service_date"], unique=False, schema="ar")
    op.create_index(op.f("ix_claims_upload_id"), "claims", ["upload_id"], unique=False, schema="ar")
    op.create_table(
        "upload_errors",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["ar.uploads.id"],
            name=op.f("fk_upload_errors_upload_id_uploads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_errors")),
        schema="ar",
    )
    op.create_index(
        op.f("ix_upload_errors_upload_id"), "upload_errors", ["upload_id"], unique=False, schema="ar"
    )
    op.create_table(
        "claim_notes",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("author_user_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["author_user_id"], ["ar.users.id"], name=op.f("fk_claim_notes_author_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["ar.claims.id"], name=op.f("fk_claim_notes_claim_id_claims"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_claim_notes")),
        schema="ar",
    )
    op.create_index(op.f("ix_claim_notes_claim_id"), "claim_notes", ["claim_id"], unique=False, schema="ar")

    _seed_lists()
    _seed_permissions()
    _lock_down(NEW_TABLES)


def downgrade() -> None:
    op.drop_index(op.f("ix_claim_notes_claim_id"), table_name="claim_notes", schema="ar")
    op.drop_table("claim_notes", schema="ar")
    op.drop_index(op.f("ix_upload_errors_upload_id"), table_name="upload_errors", schema="ar")
    op.drop_table("upload_errors", schema="ar")
    op.drop_index(op.f("ix_claims_upload_id"), table_name="claims", schema="ar")
    op.drop_index(op.f("ix_claims_service_date"), table_name="claims", schema="ar")
    op.drop_index(op.f("ix_claims_practice_id"), table_name="claims", schema="ar")
    op.drop_index(op.f("ix_claims_followup_date"), table_name="claims", schema="ar")
    op.drop_index(op.f("ix_claims_assigned_user_id"), table_name="claims", schema="ar")
    op.drop_table("claims", schema="ar")
    op.drop_index(op.f("ix_uploads_practice_id"), table_name="uploads", schema="ar")
    op.drop_index(op.f("ix_uploads_checksum"), table_name="uploads", schema="ar")
    op.drop_table("uploads", schema="ar")
    op.drop_table("option_list_items", schema="ar")
    _remove_permissions()


def _seed_lists() -> None:
    items = sa.table(
        "option_list_items", sa.column("list_key"), sa.column("value"), sa.column("sort_order"), schema=SCHEMA
    )
    op.bulk_insert(
        items,
        [
            {"list_key": key, "value": value, "sort_order": position}
            for key, values in LISTS.items()
            for position, value in enumerate(values)
        ],
    )


def _seed_permissions() -> None:
    permissions = sa.table(
        "permissions", sa.column("key"), sa.column("module"), sa.column("description"), schema=SCHEMA
    )
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


def _lock_down(tables: list[str]) -> None:
    for table in tables:
        op.execute(f"ALTER TABLE {SCHEMA}.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA {SCHEMA} FROM %I', api_role);
                END IF;
            END LOOP;
        END
        $$
        """
    )


def _remove_permissions() -> None:
    keys = ", ".join(f"'{key}'" for key, _, _ in PERMISSIONS)
    op.execute(f"DELETE FROM {SCHEMA}.permissions WHERE key IN ({keys})")
