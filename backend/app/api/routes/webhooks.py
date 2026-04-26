from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_feature, get_current_user, get_db
from app.models.user import User
from app.models.webhook_log import WebhookLog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class WebhookStatusResponse(BaseModel):
    received: int
    last_received_at: str | None


class WebhookLogEntry(BaseModel):
    id: int
    source: str
    payload: dict[str, Any] | None
    received_at: datetime

    model_config = {"from_attributes": True}


class WebhookLogListResponse(BaseModel):
    items: list[WebhookLogEntry]
    total: int
    page: int
    size: int
    pages: int


@router.post(
    "/n8n",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_feature("n8n"))],
)
async def receive_n8n_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Receive a webhook payload from n8n and persist it to the database."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    log_entry = WebhookLog(source="n8n", payload=payload)
    db.add(log_entry)
    await db.commit()
    logger.info("n8n_webhook_received", payload_keys=list(payload.keys()))

    return {"status": "received"}


@router.get("/status", response_model=WebhookStatusResponse)
async def webhook_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookStatusResponse:
    total_result = await db.execute(select(func.count(WebhookLog.id)))
    total = total_result.scalar_one()

    last_result = await db.execute(
        select(WebhookLog.received_at).order_by(WebhookLog.received_at.desc()).limit(1)
    )
    last_row = last_result.scalar_one_or_none()
    last_received_at = last_row.isoformat() if last_row else None

    return WebhookStatusResponse(received=total, last_received_at=last_received_at)


@router.get("/logs", response_model=WebhookLogListResponse)
async def list_webhook_logs(
    source: str | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebhookLogListResponse:
    """Return paginated webhook log entries, newest first."""
    query = select(WebhookLog)
    count_query = select(func.count(WebhookLog.id))

    if source:
        query = query.where(WebhookLog.source == source)
        count_query = count_query.where(WebhookLog.source == source)

    total = (await db.execute(count_query)).scalar_one()
    rows_result = await db.execute(
        query.order_by(WebhookLog.received_at.desc()).offset((page - 1) * size).limit(size)
    )
    entries = rows_result.scalars().all()

    return WebhookLogListResponse(
        items=[WebhookLogEntry.model_validate(e) for e in entries],
        total=total,
        page=page,
        size=size,
        pages=max(1, -(-total // size)),
    )

