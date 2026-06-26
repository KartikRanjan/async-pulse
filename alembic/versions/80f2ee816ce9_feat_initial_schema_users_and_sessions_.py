"""Feat: initial schema — users and sessions tables.

Revision ID: 80f2ee816ce9
Revises:
Create Date: 2026-06-21 04:20:00.555336

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "80f2ee816ce9"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_verification",
                "active",
                "suspended",
                "banned",
                name="userstatus",
                native_enum=False,
                length=50,
            ),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum(
                "user",
                "admin",
                "superuser",
                name="userrole",
                native_enum=False,
                length=50,
            ),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="async-pulse",
    )
    op.create_index(
        op.f("ix_async-pulse_users_email"),
        "users",
        ["email"],
        unique=True,
        schema="async-pulse",
    )
    op.create_index(
        op.f("ix_async-pulse_users_username"),
        "users",
        ["username"],
        unique=True,
        schema="async-pulse",
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("refresh_token_hash", sa.String(length=255), nullable=False),
        sa.Column("device_info", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_session_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("rotation_counter", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["previous_session_id"],
            ["async-pulse.sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["async-pulse.users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="async-pulse",
    )
    op.create_index(
        op.f("ix_async-pulse_sessions_user_id"),
        "sessions",
        ["user_id"],
        unique=False,
        schema="async-pulse",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_async-pulse_sessions_user_id"),
        table_name="sessions",
        schema="async-pulse",
    )
    op.drop_table("sessions", schema="async-pulse")
    op.drop_index(
        op.f("ix_async-pulse_users_username"),
        table_name="users",
        schema="async-pulse",
    )
    op.drop_index(
        op.f("ix_async-pulse_users_email"),
        table_name="users",
        schema="async-pulse",
    )
    op.drop_table("users", schema="async-pulse")
