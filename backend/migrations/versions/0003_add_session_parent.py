"""Add sessions.parent_session_id column (Revision Flow — link a revision to its parent).
Revision ID: 0003
Revises: 0002
Create Date: 2026-07-16 00:00:00.000000
"""
from __future__ import annotations
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    op.add_column("sessions", sa.Column("parent_session_id", sa.Uuid(), nullable=True))
def downgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_column("parent_session_id")
