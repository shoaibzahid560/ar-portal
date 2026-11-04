"""Notifications (M5): the in-app notification centre, and who receives oversight notifications.

- notifications: one message per person, with a link; no patient details in titles or bodies
- notifications.oversight: receive a notification for every upload, assignment, file download, user and
  permission change, and refused sign-in (Management and System Administrator; editable in Settings)

Revision ID: 0004
Revises: 0003
Created: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("recipient_user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("link", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("dedupe_key", sa.Text(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["ar.users.id"],
            name=op.f("fk_notifications_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_user_id"],
            ["ar.users.id"],
            name=op.f("fk_notifications_recipient_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_notifications_dedupe_key")),
        schema="ar",
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_user_id", "created_at"],
        unique=False,
        schema="ar",
    )
    op.execute("ALTER TABLE ar.notifications ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        DO $$
        DECLARE api_role text;
        BEGIN
            FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                    EXECUTE format('REVOKE ALL ON ar.notifications FROM %I', api_role);
                END IF;
            END LOOP;
        END
        $$
        """
    )
    op.execute(
        "INSERT INTO ar.permissions (key, module, description) VALUES "
        "('notifications.oversight', 'notifications', "
        "'Be notified of every upload, assignment, download, user and permission change')"
    )
    op.execute(
        "INSERT INTO ar.role_permissions (role_id, permission_key) "
        "SELECT id, 'notifications.oversight' FROM ar.roles WHERE key IN ('system_admin', 'management')"
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_created", table_name="notifications", schema="ar")
    op.drop_table("notifications", schema="ar")
    op.execute("DELETE FROM ar.permissions WHERE key = 'notifications.oversight'")
