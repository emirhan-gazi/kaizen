"""Tests for API endpoints and authentication."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.auth import hash_api_key
from src.api.main import app
from src.database import get_db
from src.models.base import (
    OptimizationJob,
    PromptVersion,
    Task,
)

pytestmark = pytest.mark.asyncio


# ── Health check (no auth) ──────────────────────────────────────


class TestHealth:
    async def test_health_no_auth(self, unauthed_client):
        resp = await unauthed_client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── Authentication ──────────────────────────────────────────────


class TestAuth:
    async def test_missing_api_key_returns_401(self, unauthed_client):
        resp = await unauthed_client.get("/api/v1/tasks/")
        assert resp.status_code == 401

    async def test_invalid_api_key_returns_401(self, unauthed_client):
        resp = await unauthed_client.get(
            "/api/v1/tasks/",
            headers={"X-API-Key": "ct_invalid-key"},
        )
        assert resp.status_code == 401


# ── Tasks ───────────────────────────────────────────────────────


class TestTasks:
    async def test_create_task(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Mock: no existing task with same name
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Mock flush + refresh to set task attributes
        async def mock_refresh(obj):
            obj.id = task_id
            obj.created_at = now

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.post(
                "/api/v1/tasks/",
                json={
                    "name": "summarize_ticket",
                    "description": "Summarize support tickets",
                    "feedback_threshold": 30,
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["name"] == "summarize_ticket"
            assert data["feedback_threshold"] == 30
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_create_task_duplicate_409(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Task(
            id=uuid.uuid4(), name="dup"
        )
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.post(
                "/api/v1/tasks/",
                json={"name": "dup"},
            )
            assert resp.status_code == 409
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_get_task_404(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.get(f"/api/v1/tasks/{uuid.uuid4()}")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Feedback ────────────────────────────────────────────────────


class TestFeedback:
    async def test_create_feedback(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        task_id = uuid.uuid4()
        entry_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # get(Task, task_id) returns a task
        mock_db.get = AsyncMock(
            return_value=Task(id=task_id, name="test", schema_json=None)
        )

        async def mock_refresh(obj):
            obj.id = entry_id
            obj.created_at = now

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock(side_effect=mock_refresh)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.post(
                "/api/v1/feedback/",
                json={
                    "task_id": str(task_id),
                    "inputs": {"text": "hello"},
                    "output": "world",
                    "score": 0.9,
                    "source": "sdk",
                },
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["score"] == 0.9
            assert data["task_id"] == str(task_id)
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_feedback_task_not_found(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.post(
                "/api/v1/feedback/",
                json={"task_id": str(uuid.uuid4())},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_feedback_schema_validation(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        task_id = uuid.uuid4()
        mock_db.get = AsyncMock(
            return_value=Task(
                id=task_id,
                name="test",
                schema_json={"fields": ["text", "category"]},
            )
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.post(
                "/api/v1/feedback/",
                json={
                    "task_id": str(task_id),
                    "inputs": {"text": "hello"},  # missing "category"
                },
            )
            assert resp.status_code == 422
            assert "category" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Prompts ─────────────────────────────────────────────────────


class TestPrompts:
    async def test_get_active_prompt_cache_miss(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        task_id = uuid.uuid4()
        prompt_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mock_db.get = AsyncMock(
            return_value=Task(id=task_id, name="test")
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = PromptVersion(
            id=prompt_id,
            task_id=task_id,
            version_number=1,
            prompt_text="You are a helpful assistant",
            eval_score=0.85,
            status="active",
            optimizer="MIPROv2",
            created_at=now,
        )
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            with patch("src.api.routes.prompts.redis_client") as mock_redis:
                mock_redis.get = AsyncMock(return_value=None)
                mock_redis.set = AsyncMock()

                resp = await client.get(f"/api/v1/prompts/{task_id}")
                assert resp.status_code == 200
                data = resp.json()
                assert data["prompt_text"] == "You are a helpful assistant"
                assert data["status"] == "active"

                # Verify cache was populated
                mock_redis.set.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_get_active_prompt_cache_hit(self, client):
        task_id = uuid.uuid4()
        prompt_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        cached_json = (
            f'{{"id":"{prompt_id}","task_id":"{task_id}",'
            f'"version_number":1,"prompt_text":"cached prompt",'
            f'"eval_score":0.9,"status":"active","optimizer":"MIPROv2",'
            f'"created_at":"{now.isoformat()}"}}'
        )

        with patch("src.api.routes.prompts.redis_client") as mock_redis:
            mock_redis.get = AsyncMock(return_value=cached_json)

            resp = await client.get(f"/api/v1/prompts/{task_id}")
            assert resp.status_code == 200
            assert resp.json()["prompt_text"] == "cached prompt"

    async def test_no_active_prompt_404(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        task_id = uuid.uuid4()
        mock_db.get = AsyncMock(
            return_value=Task(id=task_id, name="test")
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            with patch("src.api.routes.prompts.redis_client") as mock_redis:
                mock_redis.get = AsyncMock(return_value=None)
                resp = await client.get(f"/api/v1/prompts/{task_id}")
                assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Jobs ────────────────────────────────────────────────────────


class TestJobs:
    async def test_get_job(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()

        job_id = uuid.uuid4()
        task_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mock_db.get = AsyncMock(
            return_value=OptimizationJob(
                id=job_id,
                task_id=task_id,
                status="COMPLETED",
                triggered_by="api",
                feedback_count=50,
                created_at=now,
            )
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.get(f"/api/v1/jobs/{job_id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "COMPLETED"
            assert data["feedback_count"] == 50
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_get_job_404(self, client):
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.get(f"/api/v1/jobs/{uuid.uuid4()}")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Auth hash utility ───────────────────────────────────────────


class TestAuthUtility:
    def test_hash_api_key_deterministic(self):
        key = "ct_test123"
        assert hash_api_key(key) == hash_api_key(key)

    def test_hash_api_key_different_for_different_keys(self):
        assert hash_api_key("ct_a") != hash_api_key("ct_b")
