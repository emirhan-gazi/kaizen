"""Asynchronous HTTP client for the Kaizen API.

Mirror of :class:`kaizen_sdk.client.CTClient` using ``httpx.AsyncClient``
and ``async def`` for all methods.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from kaizen_sdk.cache import TTLCache
from kaizen_sdk.exceptions import CTError, raise_for_status
from kaizen_sdk.models import (
    FeedbackResult,
    Job,
    OptimizeResult,
    Prompt,
    Task,
    TraceResult,
)


class AsyncCTClient:
    """Asynchronous client for the Kaizen API.

    Usage::

        async with AsyncCTClient(api_key="sk-...") as client:
            await client.log_feedback(task_id, inputs={"q": "hi"}, output="hello", score=0.9)
            prompt = await client.get_prompt(task_id)

    Configuration via environment variables when constructor args are omitted:

    * ``KAIZEN_API_KEY``  -- API key for authentication
    * ``KAIZEN_BASE_URL`` -- Base URL of the CT server (default ``http://localhost:8000``)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        cache_ttl: float = 300.0,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or os.environ.get("KAIZEN_API_KEY")
        if not self._api_key:
            raise CTError(
                "API key required. Pass api_key= or set KAIZEN_API_KEY env var."
            )
        self._base_url = (
            base_url or os.environ.get("KAIZEN_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self._cache = TTLCache(ttl_seconds=cache_ttl)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": self._api_key},
            follow_redirects=True,
            timeout=timeout,
        )

    # -- Feedback -----------------------------------------------------------

    async def log_feedback(
        self,
        task_id: str,
        inputs: dict | None = None,
        output: str | None = None,
        score: float | None = None,
        source: str = "sdk",
        metadata: dict | None = None,
    ) -> FeedbackResult:
        """Log a feedback entry for *task_id*."""
        resp = await self._client.post(
            "/api/v1/feedback",
            json={
                "task_id": str(task_id),
                "inputs": inputs,
                "output": output,
                "score": score,
                "source": source,
                "metadata": metadata,
            },
        )
        raise_for_status(resp)
        return FeedbackResult.model_validate(resp.json())

    # -- Prompts ------------------------------------------------------------

    async def get_prompt(self, task_id: str) -> Prompt:
        """Retrieve the active prompt for *task_id* (cached by TTL)."""
        key = f"prompt:{task_id}"
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        resp = await self._client.get(f"/api/v1/prompts/{task_id}")
        raise_for_status(resp)
        prompt = Prompt.model_validate(resp.json())
        self._cache.set(key, prompt)
        return prompt

    async def activate_prompt(self, task_id: str, version_id: str) -> Prompt:
        """Activate a specific prompt version and invalidate cache."""
        resp = await self._client.post(
            f"/api/v1/prompts/{task_id}/activate",
            json={"version_id": str(version_id)},
        )
        raise_for_status(resp)
        self._cache.invalidate(f"prompt:{task_id}")
        return Prompt.model_validate(resp.json())

    # -- Optimization -------------------------------------------------------

    async def trigger_optimization(self, task_id: str) -> OptimizeResult:
        """Trigger an optimization run for *task_id*."""
        resp = await self._client.post(f"/api/v1/optimize/{task_id}")
        raise_for_status(resp)
        return OptimizeResult.model_validate(resp.json())

    # -- Jobs ---------------------------------------------------------------

    async def get_job(self, job_id: str) -> Job:
        """Get the status of an optimization job."""
        resp = await self._client.get(f"/api/v1/jobs/{job_id}")
        raise_for_status(resp)
        return Job.model_validate(resp.json())

    # -- Tasks --------------------------------------------------------------

    async def list_tasks(self) -> list[Task]:
        """List all tasks."""
        resp = await self._client.get("/api/v1/tasks")
        raise_for_status(resp)
        return [Task.model_validate(t) for t in resp.json()]

    async def create_task(
        self,
        name: str,
        description: str | None = None,
        schema_json: dict | None = None,
        feedback_threshold: int = 50,
        **kwargs: Any,
    ) -> Task:
        """Create a new task."""
        body: dict[str, Any] = {
            "name": name,
            "description": description,
            "schema_json": schema_json,
            "feedback_threshold": feedback_threshold,
            **kwargs,
        }
        resp = await self._client.post(
            "/api/v1/tasks",
            json={k: v for k, v in body.items() if v is not None},
        )
        raise_for_status(resp)
        return Task.model_validate(resp.json())

    # -- Traces ---------------------------------------------------------------

    async def score(self, trace_id: str, score: float, scored_by: str = "sdk") -> TraceResult:
        """Score a trace by ID (D-18)."""
        resp = await self._client.post(
            f"/api/v1/traces/{trace_id}/score",
            json={"score": score, "scored_by": scored_by},
        )
        raise_for_status(resp)
        return TraceResult.model_validate(resp.json())

    # -- Lifecycle ----------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def __aenter__(self) -> AsyncCTClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
