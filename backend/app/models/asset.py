from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[int | None] = mapped_column(
        sa.Integer, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    filename: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(sa.String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    asset_type: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    file_size: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    source: Mapped[str] = mapped_column(sa.String(64), default="local", nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", sa.JSON, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
