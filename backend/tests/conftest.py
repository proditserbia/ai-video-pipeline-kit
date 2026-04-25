from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Import models to register them with Base metadata before table creation
import app.models.user  # noqa: F401
import app.models.project  # noqa: F401
import app.models.job  # noqa: F401
import app.models.topic  # noqa: F401
import app.models.asset  # noqa: F401
from app.database import Base

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def session_factory(engine):
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(session_factory):
    from app.main import app
    from app.api.deps import get_db

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_token(session_factory):
    """Create admin user and return JWT token."""
    from sqlalchemy import select
    from app.core.security import hash_password, create_access_token
    from app.models.user import User

    async with session_factory() as db:
        result = await db.execute(select(User).where(User.email == "test@example.com"))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                email="test@example.com",
                hashed_password=hash_password("testpass"),
                is_active=True,
                is_admin=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return create_access_token(subject=user.id)
