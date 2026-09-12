import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import SessionFactory
from app.db.models.user import User
from app.core.security import hash_password
from app.db.models.enums import UserRole
from sqlalchemy import select

ADMIN_EMAIL = "admin@example.gov"
ADMIN_NAME = "Demo Admin"
ADMIN_PASSWORD = "TraceFall2026!"

async def ensure_admin():
    async with SessionFactory() as session:
        existing = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
        if existing:
            print(f"Admin user {ADMIN_EMAIL} already exists.")
            return
        user = User(
            email=ADMIN_EMAIL,
            full_name=ADMIN_NAME,
            password_hash=hash_password(ADMIN_PASSWORD),
            role=UserRole.ADMIN,
        )
        session.add(user)
        await session.commit()
        print(f"Created admin user {ADMIN_EMAIL}.")

if __name__ == "__main__":
    asyncio.run(ensure_admin())
