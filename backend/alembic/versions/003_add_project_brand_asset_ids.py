"""Add watermark_asset_id and background_music_asset_id to projects

Revision ID: 003
Revises: 002
Create Date: 2026-04-26 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("watermark_asset_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("background_music_asset_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_watermark_asset_id",
        "projects",
        "assets",
        ["watermark_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_projects_background_music_asset_id",
        "projects",
        "assets",
        ["background_music_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_projects_background_music_asset_id", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_watermark_asset_id", "projects", type_="foreignkey")
    op.drop_column("projects", "background_music_asset_id")
    op.drop_column("projects", "watermark_asset_id")
