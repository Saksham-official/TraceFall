"""Test fixtures.

Environment is set before any app import, because settings are cached and the database
engine is created at import time.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-outside-tests-0123456789")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://tracefall:tracefall@127.0.0.1:5432/tracefall_test"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:6379/15")
os.environ["ENVIRONMENT"] = "development"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.models.enums import UserRole  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import SessionFactory, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.orchestrator import queue  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Reference data is created by migration and shared by every test.
PRESERVED_TABLES = {"alembic_version", "chains", "assets"}


@pytest.fixture(scope="session", autouse=True)
def migrate() -> None:
    """Front-loaded schema: all migrations exist from Phase 2, so no later phase
    generates one concurrently and forks the chain."""
    subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        check=True,
        capture_output=True,
    )


@pytest.fixture
async def clean_database() -> AsyncIterator[None]:
    """Requested by the session and client fixtures, so pure unit tests never touch the
    database at all."""
    async with engine.begin() as conn:
        rows = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        targets = [t for (t,) in rows if t not in PRESERVED_TABLES]
        # TRUNCATE is statement-level, so it bypasses the append-only row triggers.
        await conn.execute(text(f"TRUNCATE {', '.join(targets)} RESTART IDENTITY CASCADE"))
    await queue.get_client().flushdb()
    yield


@pytest.fixture
async def session(clean_database: None) -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as s:
        yield s


@pytest.fixture
async def client(clean_database: None) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


async def make_user(
    session: AsyncSession,
    email: str,
    role: UserRole = UserRole.INVESTIGATOR,
    password: str = "correct-horse-battery",  # noqa: S107
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=email.split("@")[0],
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login(client: AsyncClient, email: str, password: str = "correct-horse-battery") -> str:  # noqa: S107
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
