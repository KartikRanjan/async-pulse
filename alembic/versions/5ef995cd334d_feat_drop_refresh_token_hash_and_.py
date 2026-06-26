"""feat: drop refresh_token_hash and rotation_counter from sessions.

Removes two columns that are redundant in the signed-JWT + jti design:

- refresh_token_hash: a valid refresh token can only be built with the
  signing secret, so hash-matching adds no practical defence beyond what
  the JWT signature already provides. The jti lookup + revoked_at state
  covers every realistic attack path.

- rotation_counter: purely observational; nothing in the auth flow gates
  on it. Dead write overhead with no consumer.

Revision ID: 5ef995cd334d
Revises: 80f2ee816ce9
Create Date: 2026-06-27 01:58:47.618269

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ef995cd334d"
down_revision: str | Sequence[str] | None = "80f2ee816ce9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "async-pulse"
_TABLE = "sessions"


def upgrade() -> None:
    """Drop refresh_token_hash and rotation_counter from the sessions table."""
    op.drop_column(_TABLE, "refresh_token_hash", schema=_SCHEMA)
    op.drop_column(_TABLE, "rotation_counter", schema=_SCHEMA)


def downgrade() -> None:
    """Restore refresh_token_hash and rotation_counter (empty/default values)."""
    op.add_column(
        _TABLE,
        sa.Column("rotation_counter", sa.Integer(), nullable=False, server_default="0"),
        schema=_SCHEMA,
    )
    op.add_column(
        _TABLE,
        sa.Column("refresh_token_hash", sa.String(length=255), nullable=False, server_default=""),
        schema=_SCHEMA,
    )
