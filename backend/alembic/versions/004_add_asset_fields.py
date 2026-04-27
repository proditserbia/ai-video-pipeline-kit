"""Add name, asset_type, file_size, user_id to assets

Revision ID: 004
Revises: 003
Create Date: 2026-04-27 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_assets_user_id",
        "assets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_assets_user_id", "assets", ["user_id"])
    op.add_column("assets", sa.Column("name", sa.String(512), nullable=True))
    op.add_column("assets", sa.Column("asset_type", sa.String(32), nullable=True))
    op.add_column("assets", sa.Column("file_size", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("assets", "file_size")
    op.drop_column("assets", "asset_type")
    op.drop_column("assets", "name")
    op.drop_index("ix_assets_user_id", table_name="assets")
    op.drop_constraint("fk_assets_user_id", "assets", type_="foreignkey")
    op.drop_column("assets", "user_id")
