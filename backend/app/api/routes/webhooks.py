from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import check_feature, get_current_user
from app.models.user import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_webhook_log: list[dict[str, Any]] = []


class WebhookStatusResponse(BaseModel):
    received: int
    last_received_at: str | None


@router.post(
    "/n8n",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(check_feature("n8n"))],
)
async def receive_n8n_webhook(request: Request) -> dict[str, str]:
    """Receive a webhook payload from n8n."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    _webhook_log.append(entry)
    logger.info("n8n_webhook_received", payload_keys=list(payload.keys()))

    return {"status": "received"}


@router.get("/status", response_model=WebhookStatusResponse)
async def webhook_status(
    current_user: User = Depends(get_current_user),
) -> WebhookStatusResponse:
    last = _webhook_log[-1]["received_at"] if _webhook_log else None
    return WebhookStatusResponse(received=len(_webhook_log), last_received_at=last)
