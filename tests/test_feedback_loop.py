"""Tests for Phase 4: feedback loop automation (auto-trigger + seed upload)."""

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.api.main import app
from src.database import get_db
from src.models.base import Task

pytestmark = pytest.mark.asyncio


def _make_task(task_id=None, threshold=3, schema_json=None):
    return Task(
        id=task_id or uuid.uuid4(),
        name="test_task",
        feedback_threshold=threshold,
        schema_json=schema_json,
        created_at=datetime.now(timezone.utc),
    )


def _make_mock_db(task, execute_returns=None):
    """Build a mock db session with a task preloaded."""
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.get = AsyncMock(return_value=task)

    # Default: execute returns scalar() -> 0 (counts) and scalar_one_or_none -> None
    if execute_returns:
        mock_db.execute = AsyncMock(side_effect=execute_returns)
    else:
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

    async def mock_refresh(obj):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()
        if not hasattr(obj, "created_at") or obj.created_at is None:
            obj.created_at = datetime.now(timezone.utc)

    mock_db.refresh = AsyncMock(side_effect=mock_refresh)
    return mock_db


# ── Auto-trigger ────────────────────────────────────────────────


class TestAutoTrigger:
    async def test_feedback_below_threshold_no_trigger(self, client):
        """Feedback count below threshold should not trigger optimization."""
        task = _make_task(threshold=50)
        mock_db = _make_mock_db(task)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            with patch("src.api.routes.feedback.redis_client") as mock_redis:
                mock_redis.set = AsyncMock(return_value=True)

                resp = await client.post(
                    "/api/v1/feedback/",
                    json={
                        "task_id": str(task.id),
                        "inputs": {"text": "hello"},
                        "output": "world",
                        "score": 0.9,
                        "source": "sdk",
                    },
                )
                assert resp.status_code == 201
                # Redis lock should NOT be attempted (below threshold)
                mock_redis.set.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_feedback_at_threshold_triggers_optimization(self, client):
        """When live feedback reaches threshold, optimization should be dispatched."""
        task = _make_task(threshold=3)

        # Build execute side effects:
        # 1. last_opt query -> scalar() returns None (no prior optimization)
        # 2. live count query -> scalar() returns 3 (threshold met)
        # 3. active job check -> scalar_one_or_none() returns None (no active job)
        # 4. total count query -> scalar() returns 5 (includes seeds)
        last_opt_result = MagicMock()
        last_opt_result.scalar.return_value = None

        live_count_result = MagicMock()
        live_count_result.scalar.return_value = 3

        active_job_result = MagicMock()
        active_job_result.scalar_one_or_none.return_value = None

        total_count_result = MagicMock()
        total_count_result.scalar.return_value = 5

        mock_db = _make_mock_db(
            task,
            execute_returns=[
                last_opt_result,
                live_count_result,
                active_job_result,
                total_count_result,
            ],
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            with (
                patch("src.api.routes.feedback.redis_client") as mock_redis,
                patch("src.worker.tasks.run_optimization") as mock_dispatch,
            ):
                mock_redis.set = AsyncMock(return_value=True)  # Lock acquired
                mock_dispatch.delay = MagicMock()

                resp = await client.post(
                    "/api/v1/feedback/",
                    json={
                        "task_id": str(task.id),
                        "inputs": {"text": "hello"},
                        "output": "world",
                        "score": 0.9,
                        "source": "sdk",
                    },
                )
                assert resp.status_code == 201
                # Celery task should have been dispatched
                mock_dispatch.delay.assert_called_once()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_redis_lock_prevents_duplicate_dispatch(self, client):
        """If Redis lock is already held, no job should be dispatched."""
        task = _make_task(threshold=3)

        last_opt_result = MagicMock()
        last_opt_result.scalar.return_value = None

        live_count_result = MagicMock()
        live_count_result.scalar.return_value = 3

        mock_db = _make_mock_db(
            task,
            execute_returns=[last_opt_result, live_count_result],
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            with (
                patch("src.api.routes.feedback.redis_client") as mock_redis,
                patch("src.worker.tasks.run_optimization") as mock_dispatch,
            ):
                mock_redis.set = AsyncMock(return_value=False)  # Lock NOT acquired
                mock_dispatch.delay = MagicMock()

                resp = await client.post(
                    "/api/v1/feedback/",
                    json={
                        "task_id": str(task.id),
                        "inputs": {"text": "hello"},
                        "output": "world",
                        "score": 0.9,
                        "source": "sdk",
                    },
                )
                assert resp.status_code == 201
                # Should NOT dispatch since lock was not acquired
                mock_dispatch.delay.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_auto_trigger_skips_when_active_job_exists(self, client):
        """If an active job exists, no new job should be dispatched even at threshold."""
        task = _make_task(threshold=3)

        last_opt_result = MagicMock()
        last_opt_result.scalar.return_value = None

        live_count_result = MagicMock()
        live_count_result.scalar.return_value = 3

        # Active job exists
        active_job_result = MagicMock()
        active_job_result.scalar_one_or_none.return_value = MagicMock()  # active job

        mock_db = _make_mock_db(
            task,
            execute_returns=[last_opt_result, live_count_result, active_job_result],
        )

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            with (
                patch("src.api.routes.feedback.redis_client") as mock_redis,
                patch("src.worker.tasks.run_optimization") as mock_dispatch,
            ):
                mock_redis.set = AsyncMock(return_value=True)  # Lock acquired
                mock_dispatch.delay = MagicMock()

                resp = await client.post(
                    "/api/v1/feedback/",
                    json={
                        "task_id": str(task.id),
                        "inputs": {"text": "hello"},
                        "output": "world",
                        "score": 0.9,
                        "source": "sdk",
                    },
                )
                assert resp.status_code == 201
                # Should NOT dispatch since active job exists
                mock_dispatch.delay.assert_not_called()
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Seed upload ─────────────────────────────────────────────────


class TestSeedUpload:
    async def test_seed_upload_valid_jsonl(self, client):
        """Valid JSONL file should be accepted."""
        task = _make_task()

        # execute returns: existing seed count = 0
        seed_count_result = MagicMock()
        seed_count_result.scalar.return_value = 0

        mock_db = _make_mock_db(task, execute_returns=[seed_count_result])

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            jsonl_content = (
                '{"inputs": {"text": "hello"}, "output": "world", "score": 0.9}\n'
                '{"inputs": {"text": "foo"}, "output": "bar", "score": 0.5}\n'
            )
            resp = await client.post(
                f"/api/v1/tasks/{task.id}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["accepted"] == 2
            assert data["rejected"] == 0
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_seed_upload_task_not_found(self, client):
        """Seed upload on nonexistent task returns 404."""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            jsonl_content = '{"inputs": {"text": "hello"}, "output": "world", "score": 0.9}\n'
            resp = await client.post(
                f"/api/v1/tasks/{uuid.uuid4()}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")},
            )
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_seed_upload_invalid_json_lines(self, client):
        """Lines with invalid JSON should be rejected, valid ones accepted."""
        task = _make_task()

        seed_count_result = MagicMock()
        seed_count_result.scalar.return_value = 0

        mock_db = _make_mock_db(task, execute_returns=[seed_count_result])

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            jsonl_content = (
                '{"inputs": {"text": "hello"}, "output": "world", "score": 0.9}\n'
                'not valid json\n'
                '{"inputs": {"text": "foo"}, "output": "bar", "score": 0.5}\n'
            )
            resp = await client.post(
                f"/api/v1/tasks/{task.id}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")},
            )
            assert resp.status_code == 201
            data = resp.json()
            assert data["accepted"] == 2
            assert data["rejected"] == 1
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_seed_upload_score_out_of_range(self, client):
        """Score outside 0-1 range should be rejected."""
        task = _make_task()

        seed_count_result = MagicMock()
        seed_count_result.scalar.return_value = 0

        mock_db = _make_mock_db(task, execute_returns=[seed_count_result])

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            jsonl_content = '{"inputs": {"text": "hello"}, "output": "world", "score": 1.5}\n'
            resp = await client.post(
                f"/api/v1/tasks/{task.id}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")},
            )
            # All lines invalid -> 422
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_seed_upload_schema_validation(self, client):
        """Seeds should be validated against task schema (D-10)."""
        task = _make_task(schema_json={"fields": ["text", "category"]})

        seed_count_result = MagicMock()
        seed_count_result.scalar.return_value = 0

        mock_db = _make_mock_db(task, execute_returns=[seed_count_result])

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            # Missing "category" field
            jsonl_content = '{"inputs": {"text": "hello"}, "output": "world", "score": 0.9}\n'
            resp = await client.post(
                f"/api/v1/tasks/{task.id}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")},
            )
            assert resp.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_seed_upload_empty_file(self, client):
        """Empty file should return 400."""
        task = _make_task()
        mock_db = _make_mock_db(task)

        # Need seed count check
        seed_count_result = MagicMock()
        seed_count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(return_value=seed_count_result)

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            resp = await client.post(
                f"/api/v1/tasks/{task.id}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(b""), "application/jsonl")},
            )
            assert resp.status_code == 400
        finally:
            app.dependency_overrides.pop(get_db, None)

    async def test_seed_limit_reached(self, client):
        """Should reject upload when seed limit already reached (D-09)."""
        task = _make_task()

        seed_count_result = MagicMock()
        seed_count_result.scalar.return_value = 1000  # At limit

        mock_db = _make_mock_db(task, execute_returns=[seed_count_result])

        async def override_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_db
        try:
            jsonl_content = '{"inputs": {"text": "hello"}, "output": "world", "score": 0.9}\n'
            resp = await client.post(
                f"/api/v1/tasks/{task.id}/seed",
                files={"file": ("seed.jsonl", io.BytesIO(jsonl_content.encode()), "application/jsonl")},
            )
            assert resp.status_code == 400
            assert "limit" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(get_db, None)
