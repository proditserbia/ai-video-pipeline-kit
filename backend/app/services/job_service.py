from __future__ import annotations

from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password
from app.database import _get_async_session_factory
from app.models.user import User


async def seed_admin_user() -> None:
    """Create the admin user if it doesn't exist."""
    async with _get_async_session_factory()() as db:
        result = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        existing = result.scalar_one_or_none()
        if existing:
            return
        admin = User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        await db.commit()
