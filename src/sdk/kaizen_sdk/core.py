"""Minimal Kaizen SDK — trace, flush, get_prompt."""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger("kaizen_sdk")

_api_key: str | None = None
_base_url: str = "http://localhost:8000"
_http_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None
_git_config: dict[str, str] = {}
_task_defaults: dict[str, Any] = {}


@dataclass
class BufferedTrace:
    task_name: str
    inputs: dict
    output: str
    prompt_file: str | None = None
    prompt_locator: str | None = None
    task_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestBuffer:
    traces: list[BufferedTrace] = field(default_factory=list)


_buffer: ContextVar[RequestBuffer] = ContextVar("ct_buffer")


def init(
    api_key: str | None = None,
    base_url: str | None = None,
    *,
    git_provider: str | None = None,
    git_base_url: str | None = None,
    git_token: str | None = None,
    git_project: str | None = None,
    git_repo: str | None = None,
    git_base_branch: str | None = None,
    feedback_threshold: int | None = None,
    teacher_model: str | None = None,
    judge_model: str | None = None,
    mode: str = "optimize_only",
) -> None:
    """Initialize Kaizen SDK. Call once at startup.

    Args:
        mode: "optimize_only" (default) — optimize prompts, view in dashboard.
              "auto_pr" — optimize + create PR on your git repo.
              "pr_preview" — optimize + store PR preview, approve from dashboard.
    """
    global _api_key, _base_url, _http_client, _sync_client, _git_config, _task_defaults

    # Close existing clients if re-initializing
    if _http_client is not None or _sync_client is not None:
        _http_client = None
        _sync_client = None

    _api_key = api_key or os.environ.get("KAIZEN_API_KEY", "")
    _base_url = (
        base_url or os.environ.get("KAIZEN_BASE_URL", "http://localhost:8000")
    ).rstrip("/")

    _git_config = {}
    for key, val in [
        ("git_provider", git_provider or os.environ.get("KAIZEN_GIT_PROVIDER", "")),
        ("git_base_url", git_base_url or os.environ.get("KAIZEN_GIT_BASE_URL", "")),
        ("git_token", git_token or os.environ.get("KAIZEN_GIT_TOKEN", "")),
        ("git_project", git_project or os.environ.get("KAIZEN_GIT_PROJECT", "")),
        ("git_repo", git_repo or os.environ.get("KAIZEN_GIT_REPO", "")),
        ("git_base_branch", git_base_branch or os.environ.get("KAIZEN_GIT_BASE_BRANCH", "")),
    ]:
        if val:
            _git_config[key] = val

    _task_defaults = {"mode": mode}
    if feedback_threshold is not None:
        _task_defaults["feedback_threshold"] = feedback_threshold
    if teacher_model:
        _task_defaults["teacher_model"] = teacher_model
    if judge_model:
        _task_defaults["judge_model"] = judge_model


def _get_async_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=_base_url,
            headers={"X-API-Key": _api_key or ""},
            follow_redirects=True,
            timeout=30.0,
        )
    return _http_client


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            base_url=_base_url,
            headers={"X-API-Key": _api_key or ""},
            follow_redirects=True,
            timeout=30.0,
        )
    return _sync_client


def _get_or_create_buffer() -> RequestBuffer:
    try:
        return _buffer.get()
    except LookupError:
        buf = RequestBuffer()
        _buffer.set(buf)
        return buf


def reset_buffer() -> None:
    """Reset trace buffer for a new request."""
    _buffer.set(RequestBuffer())


def _extract_output(result: Any) -> str:
    """Extract text from various LLM result types."""
    if isinstance(result, str):
        return result
    if hasattr(result, "content"):
        return str(result.content)
    if hasattr(result, "choices") and result.choices:
        choice = result.choices[0]
        if hasattr(choice, "message"):
            return str(choice.message.content)
    return str(result)


def _append_trace(
    task_name: str,
    inputs: dict,
    output_text: str,
    prompt_file: str | None,
    prompt_locator: str | None,
    task_overrides: dict[str, Any] | None = None,
) -> None:
    buf = _get_or_create_buffer()
    buf.traces.append(
        BufferedTrace(
            task_name=task_name,
            inputs={k: str(v) for k, v in inputs.items()},
            output=output_text,
            prompt_file=prompt_file,
            prompt_locator=prompt_locator,
            task_overrides=task_overrides or {},
        )
    )


async def trace(
    task_name: str,
    fn: Callable,
    inputs: dict,
    *,
    prompt_file: str | None = None,
    prompt_locator: str | None = None,
    feedback_threshold: int | None = None,
    teacher_model: str | None = None,
    judge_model: str | None = None,
) -> Any:
    """Trace an async LLM call. Runs fn(inputs), captures output, buffers it.

    Args:
        task_name: Name of the CT task (e.g. "agent_assist_router").
        fn: Async callable (e.g. chain.ainvoke).
        inputs: Dict of inputs to pass to fn.
        prompt_file: Optional path to prompt source file (for auto-PR).
        prompt_locator: Optional variable name in prompt file (for auto-PR).
        feedback_threshold: Override global threshold for this task.
        teacher_model: Override global teacher model for this task.
        judge_model: Override global judge model for this task.

    Returns:
        The result from fn(inputs).
    """
    result = await fn(inputs)
    overrides = _collect_overrides(feedback_threshold, teacher_model, judge_model)
    _append_trace(task_name, inputs, _extract_output(result), prompt_file, prompt_locator, overrides)
    return result


def trace_sync(
    task_name: str,
    fn: Callable,
    inputs: dict,
    *,
    prompt_file: str | None = None,
    prompt_locator: str | None = None,
    feedback_threshold: int | None = None,
    teacher_model: str | None = None,
    judge_model: str | None = None,
) -> Any:
    """Trace a sync LLM call. Same as trace() but synchronous."""
    result = fn(inputs)
    overrides = _collect_overrides(feedback_threshold, teacher_model, judge_model)
    _append_trace(task_name, inputs, _extract_output(result), prompt_file, prompt_locator, overrides)
    return result


def _collect_overrides(
    feedback_threshold: int | None,
    teacher_model: str | None,
    judge_model: str | None,
) -> dict[str, Any]:
    """Merge per-trace overrides on top of global defaults."""
    merged = dict(_task_defaults)
    if feedback_threshold is not None:
        merged["feedback_threshold"] = feedback_threshold
    if teacher_model:
        merged["teacher_model"] = teacher_model
    if judge_model:
        merged["judge_model"] = judge_model
    return merged


def get_buffered_traces() -> list[dict]:
    """Return buffered traces as serializable dicts (for SSE metadata)."""
    try:
        buf = _buffer.get()
    except LookupError:
        return []
    return [
        {"task_name": t.task_name, "inputs": t.inputs, "output": t.output}
        for t in buf.traces
    ]


def _build_feedback_payload(t: BufferedTrace, score: float) -> dict:
    payload: dict[str, Any] = {
        "task_name": t.task_name,
        "inputs": t.inputs,
        "output": t.output,
        "score": score,
        "source": "sdk",
        "prompt_file": t.prompt_file,
        "prompt_locator": t.prompt_locator,
    }
    if _git_config:
        payload.update(_git_config)
    if t.task_overrides:
        payload.update(t.task_overrides)
    return payload


def _handle_response(t: BufferedTrace, resp: httpx.Response) -> dict:
    if resp.status_code in (200, 201):
        data = resp.json()
        return {"task": t.task_name, "status": "ok", "id": data.get("id")}
    return {"task": t.task_name, "status": "error", "detail": resp.text[:200]}


async def flush(score: float) -> list[dict]:
    """Send all buffered traces to CT API with the given score.

    Returns list of per-trace results.
    """
    try:
        buf = _buffer.get()
    except LookupError:
        return []

    if not buf.traces:
        return []

    client = _get_async_client()
    results = []

    for t in buf.traces:
        try:
            resp = await client.post(
                "/api/v1/feedback/",
                json=_build_feedback_payload(t, score),
            )
            results.append(_handle_response(t, resp))
        except Exception as e:
            logger.warning("ct.flush failed for %s: %s", t.task_name, e)
            results.append({"task": t.task_name, "status": "error", "detail": str(e)})

    buf.traces.clear()
    return results


def flush_sync(score: float) -> list[dict]:
    """Sync version of flush()."""
    try:
        buf = _buffer.get()
    except LookupError:
        return []

    if not buf.traces:
        return []

    client = _get_sync_client()
    results = []

    for t in buf.traces:
        try:
            resp = client.post(
                "/api/v1/feedback/",
                json=_build_feedback_payload(t, score),
            )
            results.append(_handle_response(t, resp))
        except Exception as e:
            logger.warning("ct.flush_sync failed for %s: %s", t.task_name, e)
            results.append({"task": t.task_name, "status": "error", "detail": str(e)})

    buf.traces.clear()
    return results


async def get_prompt(task_name: str) -> Optional[str]:
    """Get the active optimized prompt for a task. Returns None if not found."""
    client = _get_async_client()
    try:
        resp = await client.get("/api/v1/tasks/", params={"name": task_name})
        if resp.status_code != 200:
            return None
        tasks = resp.json()
        if not tasks:
            return None
        task_id = tasks[0]["id"]

        resp = await client.get(f"/api/v1/prompts/{task_id}")
        if resp.status_code != 200:
            return None
        return resp.json().get("prompt_text")
    except Exception:
        logger.warning("ct.get_prompt failed for %s", task_name, exc_info=True)
        return None


async def close() -> None:
    """Close HTTP clients. Call at shutdown."""
    global _http_client, _sync_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
    if _sync_client:
        _sync_client.close()
        _sync_client = None
