from __future__ import annotations

import structlog
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password, verify_password
from app.database import _get_async_session_factory
from app.models.user import User

logger = structlog.get_logger(__name__)


async def seed_admin_user() -> None:
    """Create the admin user if it doesn't exist, or update the password if it has changed."""
    async with _get_async_session_factory()() as db:
        result = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        existing = result.scalar_one_or_none()
        if existing:
            if not verify_password(settings.ADMIN_PASSWORD, existing.hashed_password):
                existing.hashed_password = hash_password(settings.ADMIN_PASSWORD)
                await db.commit()
                logger.info("admin_password_updated", email=settings.ADMIN_EMAIL)
            return
        admin = User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        await db.commit()
