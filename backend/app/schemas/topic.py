from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.models.topic import TopicStatus


class TopicBase(BaseModel):
    title: str
    description: str | None = None
    source: str | None = None
    score: float | None = None
    keywords: list[str] | None = None


class TopicCreate(TopicBase):
    pass


class TopicUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TopicStatus | None = None
    score: float | None = None
    keywords: list[str] | None = None


class TopicResponse(TopicBase):
    id: int
    status: TopicStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class TopicListResponse(BaseModel):
    items: list[TopicResponse]
    total: int
    page: int
    size: int
    pages: int = 1


class TopicDiscoverRequest(BaseModel):
    keyword: str | None = None
    sources: list[str] | None = None
    limit: int = 10
