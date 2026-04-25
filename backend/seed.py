#!/usr/bin/env python3
"""Seed the database with the initial admin user."""
from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings
from app.core.security import hash_password, verify_password
from app.database import _get_async_session_factory
from app.models.user import User
from sqlalchemy import select


async def main() -> None:
    async with _get_async_session_factory()() as db:
        result = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL))
        existing = result.scalar_one_or_none()
        if existing:
            if not verify_password(settings.ADMIN_PASSWORD, existing.hashed_password):
                existing.hashed_password = hash_password(settings.ADMIN_PASSWORD)
                await db.commit()
                print(f"Admin user '{settings.ADMIN_EMAIL}' password updated.")
            else:
                print(f"Admin user '{settings.ADMIN_EMAIL}' already exists.")
            return

        admin = User(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            is_active=True,
            is_admin=True,
        )
        db.add(admin)
        await db.commit()
        print(f"Admin user '{settings.ADMIN_EMAIL}' created.")


if __name__ == "__main__":
    asyncio.run(main())
