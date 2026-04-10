"""Shared test fixtures."""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/continuous_tune_test"
)
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/1"
os.environ["CELERY_RESULT_BACKEND"] = (
    "db+postgresql+psycopg://postgres:postgres@localhost:5432/continuous_tune_test"
)

from src.api.auth import hash_api_key, require_api_key
from src.api.main import app
from src.database import get_db
from src.models.base import ApiKey


# --- Mock DB session ---


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


# --- Authenticated client ---

TEST_API_KEY = "ct_test-key-for-unit-tests"
TEST_API_KEY_HASH = hash_api_key(TEST_API_KEY)
TEST_API_KEY_ROW = ApiKey(
    id=uuid.uuid4(),
    key_hash=TEST_API_KEY_HASH,
    label="test",
    created_at=datetime.now(timezone.utc),
    revoked_at=None,
)


async def _mock_require_api_key():
    return TEST_API_KEY_ROW


async def _mock_get_db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # Make execute().scalar_one_or_none() return None so auth lookups fail
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    yield session


@pytest_asyncio.fixture
async def client():
    """Authenticated async test client with mocked auth."""
    app.dependency_overrides[require_api_key] = _mock_require_api_key
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthed_client():
    """Unauthenticated async test client with mocked DB but real auth."""
    # Override get_db so it doesn't try to connect to a real database,
    # but do NOT override require_api_key so auth checks are real.
    app.dependency_overrides[get_db] = _mock_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
