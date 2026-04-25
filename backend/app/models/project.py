from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    brand_settings: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    watermark_path: Mapped[str | None] = mapped_column(sa.String(512), nullable=True)
    fonts: Mapped[list | None] = mapped_column(sa.JSON, nullable=True)
    colors: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    default_output_format: Mapped[str] = mapped_column(sa.String(16), default="mp4", nullable=False)
    enabled_platforms: Mapped[list | None] = mapped_column(sa.JSON, nullable=True)
    default_caption_style: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    default_voice: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    storage_settings: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
