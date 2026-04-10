"""Integration tests for AsyncCTClient using httpx MockTransport."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx  # noqa: E402
import pytest  # noqa: E402

from kaizen_sdk.async_client import AsyncCTClient  # noqa: E402
from kaizen_sdk.exceptions import (  # noqa: E402
    CTAuthError,
    CTError,
    CTNotFoundError,
)

# ---------------------------------------------------------------------------
# Sample response payloads (same as sync tests)
# ---------------------------------------------------------------------------

_TASK_ID = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
_JOB_ID = "cccccccc-4444-5555-6666-dddddddddddd"
_PROMPT_ID = "eeeeeeee-7777-8888-9999-ffffffffffff"
_FEEDBACK_ID = "11111111-aaaa-bbbb-cccc-222222222222"

TASK_JSON = {
    "id": _TASK_ID,
    "name": "test_task",
    "description": "A test task",
    "schema_json": None,
    "feedback_threshold": 50,
    "feedback_retention_limit": 1000,
    "evaluator_config": None,
    "teacher_model": None,
    "judge_model": None,
    "module_type": "predict",
    "cost_budget": None,
    "github_repo": None,
    "github_base_branch": None,
    "prompt_path": None,
    "prompt_format": None,
    "created_at": "2026-01-01T00:00:00Z",
    "feedback_count": 0,
    "last_optimization": None,
    "active_prompt_score": None,
    "threshold_progress": "0/50",
}

FEEDBACK_JSON = {
    "id": _FEEDBACK_ID,
    "task_id": _TASK_ID,
    "inputs": {"q": "hi"},
    "output": "hello",
    "score": 0.9,
    "source": "sdk",
    "metadata_": None,
    "created_at": "2026-01-01T00:00:00Z",
}

PROMPT_JSON = {
    "id": _PROMPT_ID,
    "task_id": _TASK_ID,
    "version_number": 1,
    "prompt_text": "You are a helpful assistant.",
    "eval_score": 0.85,
    "status": "active",
    "optimizer": "MIPROv2",
    "dspy_version": "3.0",
    "created_at": "2026-01-01T00:00:00Z",
}

JOB_JSON = {
    "id": _JOB_ID,
    "task_id": _TASK_ID,
    "prompt_version_id": None,
    "status": "completed",
    "triggered_by": "api",
    "feedback_count": 50,
    "pr_url": None,
    "error_message": None,
    "job_metadata": None,
    "progress_step": None,
    "started_at": "2026-01-01T00:00:00Z",
    "completed_at": "2026-01-01T00:01:00Z",
    "created_at": "2026-01-01T00:00:00Z",
}

COST_ESTIMATE_JSON = {
    "estimated_cost_usd": 1.50,
    "estimated_llm_calls": 100,
    "train_size": 40,
    "val_size": 10,
    "max_trials": 5,
    "teacher_model": "gpt-4",
    "judge_model": "gpt-4",
}

OPTIMIZE_JSON = {
    "job": JOB_JSON,
    "cost_estimate": COST_ESTIMATE_JSON,
    "budget_warning": None,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_async_client(handler) -> AsyncCTClient:
    """Create an AsyncCTClient wired to an async mock transport."""
    transport = httpx.MockTransport(handler)
    client = AsyncCTClient(api_key="test-key", base_url="http://test:8000")
    client._client = httpx.AsyncClient(  # noqa: SLF001
        transport=transport,
        base_url="http://test:8000",
        headers={"X-API-Key": "test-key"},
    )
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_feedback():
    """log_feedback POSTs correct payload and returns FeedbackResult."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/feedback"
        body = json.loads(request.content)
        assert body["task_id"] == _TASK_ID
        assert body["score"] == 0.9
        return httpx.Response(201, json=FEEDBACK_JSON)

    client = _make_async_client(handler)
    result = await client.log_feedback(
        _TASK_ID, inputs={"q": "hi"}, output="hello", score=0.9
    )
    assert str(result.task_id) == _TASK_ID
    assert result.score == 0.9
    await client.close()


@pytest.mark.asyncio
async def test_get_prompt():
    """get_prompt returns a Prompt model."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PROMPT_JSON)

    client = _make_async_client(handler)
    prompt = await client.get_prompt(_TASK_ID)
    assert str(prompt.id) == _PROMPT_ID
    assert prompt.version_number == 1
    await client.close()


@pytest.mark.asyncio
async def test_get_prompt_cached():
    """Second get_prompt call uses cache -- no HTTP request."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=PROMPT_JSON)

    client = _make_async_client(handler)
    await client.get_prompt(_TASK_ID)
    await client.get_prompt(_TASK_ID)
    assert call_count == 1, "Second call should use cache, not HTTP"
    await client.close()


@pytest.mark.asyncio
async def test_trigger_optimization():
    """trigger_optimization returns OptimizeResult."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(200, json=OPTIMIZE_JSON)

    client = _make_async_client(handler)
    result = await client.trigger_optimization(_TASK_ID)
    assert result.job.status == "completed"
    assert result.cost_estimate.estimated_cost_usd == 1.50
    await client.close()


@pytest.mark.asyncio
async def test_get_job():
    """get_job returns Job model."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=JOB_JSON)

    client = _make_async_client(handler)
    job = await client.get_job(_JOB_ID)
    assert str(job.id) == _JOB_ID
    assert job.status == "completed"
    await client.close()


@pytest.mark.asyncio
async def test_list_tasks():
    """list_tasks returns list of Task models."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[TASK_JSON])

    client = _make_async_client(handler)
    tasks = await client.list_tasks()
    assert len(tasks) == 1
    assert tasks[0].name == "test_task"
    await client.close()


@pytest.mark.asyncio
async def test_create_task():
    """create_task POSTs and returns Task model."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["name"] == "new_task"
        return httpx.Response(201, json=TASK_JSON)

    client = _make_async_client(handler)
    task = await client.create_task("new_task", description="desc")
    assert str(task.id) == _TASK_ID
    await client.close()


@pytest.mark.asyncio
async def test_activate_prompt_invalidates_cache():
    """After activate_prompt, get_prompt makes a fresh HTTP call."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=PROMPT_JSON)

    client = _make_async_client(handler)
    await client.get_prompt(_TASK_ID)
    await client.activate_prompt(_TASK_ID, _PROMPT_ID)
    await client.get_prompt(_TASK_ID)
    assert call_count == 3, "Cache should be invalidated after activate"
    await client.close()


@pytest.mark.asyncio
async def test_auth_error_raised():
    """401 response raises CTAuthError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"detail": "Invalid API key", "title": "Unauthorized"}
        )

    client = _make_async_client(handler)
    with pytest.raises(CTAuthError) as exc_info:
        await client.list_tasks()
    assert exc_info.value.status_code == 401
    await client.close()


@pytest.mark.asyncio
async def test_not_found_error():
    """404 response raises CTNotFoundError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"detail": "Not found", "title": "Not Found"}
        )

    client = _make_async_client(handler)
    with pytest.raises(CTNotFoundError) as exc_info:
        await client.get_job("nonexistent")
    assert exc_info.value.status_code == 404
    await client.close()


@pytest.mark.asyncio
async def test_env_var_config(monkeypatch):
    """AsyncCTClient reads KAIZEN_API_KEY and KAIZEN_BASE_URL from env."""
    monkeypatch.setenv("KAIZEN_API_KEY", "from-env")
    monkeypatch.setenv("KAIZEN_BASE_URL", "http://env-host:9000")
    client = AsyncCTClient()
    assert client._api_key == "from-env"  # noqa: SLF001
    assert client._base_url == "http://env-host:9000"  # noqa: SLF001
    await client.close()


def test_missing_api_key_raises(monkeypatch):
    """AsyncCTClient with no key raises CTError."""
    monkeypatch.delenv("KAIZEN_API_KEY", raising=False)
    with pytest.raises(CTError, match="API key required"):
        AsyncCTClient()


@pytest.mark.asyncio
async def test_async_context_manager():
    """async with AsyncCTClient(...) works."""
    async with AsyncCTClient(api_key="test-key") as client:
        assert client._api_key == "test-key"  # noqa: SLF001
