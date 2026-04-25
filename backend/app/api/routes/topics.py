from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import check_feature, get_current_user, get_db
from app.models.topic import Topic, TopicStatus
from app.models.user import User
from app.schemas.topic import TopicDiscoverRequest, TopicListResponse, TopicResponse

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=TopicListResponse)
async def list_topics(
    status: TopicStatus | None = None,
    page: int = 1,
    size: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TopicListResponse:
    query = select(Topic)
    count_query = select(func.count(Topic.id))
    if status:
        query = query.where(Topic.status == status)
        count_query = count_query.where(Topic.status == status)

    total = (await db.execute(count_query)).scalar_one()
    result = await db.execute(query.offset((page - 1) * size).limit(size))
    topics = result.scalars().all()

    return TopicListResponse(
        items=[TopicResponse.model_validate(t) for t in topics],
        total=total,
        page=page,
        size=size,
        pages=max(1, -(-total // size)),
    )


@router.post(
    "/discover",
    response_model=list[TopicResponse],
    dependencies=[Depends(check_feature("trends"))],
)
async def discover_topics(
    body: TopicDiscoverRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TopicResponse]:
    """Trigger trend discovery and persist results."""
    created: list[Topic] = []
    try:
        from worker.modules.trends.google_trends import GoogleTrendsProvider
        from worker.modules.trends.rss_provider import RSSProvider

        providers: list = []
        sources = body.sources or ["google", "rss"]
        if "google" in sources:
            providers.append(GoogleTrendsProvider())
        if "rss" in sources:
            providers.append(RSSProvider())

        for provider in providers:
            try:
                results = provider.fetch(keyword=body.keyword, limit=body.limit)
                for item in results:
                    topic = Topic(
                        title=item.title,
                        description=item.description,
                        source=item.source,
                        score=item.score,
                        keywords=item.keywords,
                    )
                    db.add(topic)
                    created.append(topic)
            except Exception:
                pass

    except ImportError:
        pass

    if created:
        await db.commit()
        for t in created:
            await db.refresh(t)

    return [TopicResponse.model_validate(t) for t in created]


@router.put("/{topic_id}/approve", response_model=TopicResponse)
@router.post("/{topic_id}/approve", response_model=TopicResponse, include_in_schema=False)
async def approve_topic(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TopicResponse:
    topic = await _get_or_404(topic_id, db)
    topic.status = TopicStatus.approved
    await db.commit()
    await db.refresh(topic)
    return TopicResponse.model_validate(topic)


@router.put("/{topic_id}/reject", response_model=TopicResponse)
@router.post("/{topic_id}/reject", response_model=TopicResponse, include_in_schema=False)
async def reject_topic(
    topic_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TopicResponse:
    topic = await _get_or_404(topic_id, db)
    topic.status = TopicStatus.rejected
    await db.commit()
    await db.refresh(topic)
    return TopicResponse.model_validate(topic)


async def _get_or_404(topic_id: int, db: AsyncSession) -> Topic:
    result = await db.execute(select(Topic).where(Topic.id == topic_id))
    topic = result.scalar_one_or_none()
    if not topic:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
    return topic
