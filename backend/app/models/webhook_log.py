from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, index=True)
    source: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)
    received_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True
    )
