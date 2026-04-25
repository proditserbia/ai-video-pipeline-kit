from __future__ import annotations

import enum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TopicStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    used = "used"
    rejected = "rejected"


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    source: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    status: Mapped[TopicStatus] = mapped_column(
        sa.Enum(TopicStatus), default=TopicStatus.pending, nullable=False
    )
    keywords: Mapped[list | None] = mapped_column(sa.JSON, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )
