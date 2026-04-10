"""Auto-instrument LLM libraries to capture traces.

Level 1 (zero config): kaizen_sdk.instrument(litellm)
Level 2 (named tasks): kaizen_sdk.instrument(litellm, task_map={"SUMMARIZE_PROMPT": "summarize_ticket"})

Monkey-patches library functions to wrap calls with trace capture.
All patches are idempotent — calling instrument() twice won't double-patch (D-23).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Callable

import httpx

from kaizen_sdk.detect import detect_prompt_source

logger = logging.getLogger("kaizen_sdk.instrument")

# Registry to track what's been patched (idempotency — D-23)
_patched: set[str] = set()
_lock = threading.Lock()

# Module-level config set by instrument()
_api_key: str | None = None
_base_url: str = "http://localhost:8000"
_task_map: dict[str, str] | None = None
_ignore_unmapped: bool = False


def instrument(
    library: Any,
    *,
    task_map: dict[str, str] | None = None,
    ignore_unmapped: bool = False,
    api_key: str | None = None,
    base_url: str | None = None,
) -> None:
    """Instrument an LLM library for auto-trace capture.

    Args:
        library: The library module to patch (litellm, openai, or langchain).
        task_map: Optional Level 2 mapping {variable_name: task_name}.
                  If provided, only mapped prompts are tracked (D-09, D-10).
        ignore_unmapped: If True and task_map is set, skip unmapped prompts (D-11).
        api_key: CT API key. Falls back to KAIZEN_API_KEY env var.
        base_url: CT API base URL. Falls back to KAIZEN_BASE_URL env var.
    """
    global _api_key, _base_url, _task_map, _ignore_unmapped  # noqa: PLW0603

    _api_key = api_key or os.environ.get("KAIZEN_API_KEY")
    _base_url = (
        base_url or os.environ.get("KAIZEN_BASE_URL", "http://localhost:8000")
    ).rstrip("/")
    _task_map = task_map
    _ignore_unmapped = ignore_unmapped

    lib_name = getattr(library, "__name__", str(library))

    if "litellm" in lib_name:
        _patch_litellm(library)
    elif "openai" in lib_name:
        _patch_openai(library)
    elif "langchain" in lib_name:
        _patch_langchain(library)
    else:
        msg = (
            f"Unsupported library: {lib_name}. "
            "Supported: litellm, openai, langchain"
        )
        raise ValueError(msg)


def _patch_litellm(litellm: Any) -> None:
    """Patch litellm.completion and litellm.acompletion (D-20)."""
    with _lock:
        if "litellm.completion" not in _patched:
            original = litellm.completion
            litellm.completion = _wrap_sync(original, "litellm.completion")
            _patched.add("litellm.completion")
            logger.info("Patched litellm.completion")

        if "litellm.acompletion" not in _patched:
            original = litellm.acompletion
            litellm.acompletion = _wrap_async(original, "litellm.acompletion")
            _patched.add("litellm.acompletion")
            logger.info("Patched litellm.acompletion")


def _patch_openai(openai: Any) -> None:
    """Patch openai.chat.completions.create (D-21)."""
    with _lock:
        if "openai.chat.completions.create" not in _patched:
            chat_cls = openai.resources.chat.completions.Completions
            original = chat_cls.create
            chat_cls.create = _wrap_sync(
                original, "openai.chat.completions.create"
            )
            _patched.add("openai.chat.completions.create")
            logger.info("Patched openai.chat.completions.create")


def _patch_langchain(langchain: Any) -> None:
    """Patch langchain BaseLLM._generate and BaseChatModel._generate (D-22)."""
    with _lock:
        if "langchain.BaseLLM._generate" not in _patched:
            try:
                from langchain.llms.base import BaseLLM  # noqa: PLC0415

                original = BaseLLM._generate
                BaseLLM._generate = _wrap_sync(
                    original, "langchain.BaseLLM._generate"
                )
                _patched.add("langchain.BaseLLM._generate")
                logger.info("Patched langchain BaseLLM._generate")
            except ImportError:
                logger.warning(
                    "langchain.llms.base.BaseLLM not found — skipping"
                )

        if "langchain.BaseChatModel._generate" not in _patched:
            try:
                from langchain.chat_models.base import (  # noqa: PLC0415
                    BaseChatModel,
                )

                original = BaseChatModel._generate
                BaseChatModel._generate = _wrap_sync(
                    original, "langchain.BaseChatModel._generate"
                )
                _patched.add("langchain.BaseChatModel._generate")
                logger.info("Patched langchain BaseChatModel._generate")
            except ImportError:
                logger.warning(
                    "langchain.chat_models.base.BaseChatModel not found"
                    " — skipping"
                )


def _extract_prompt_from_args(
    args: tuple, kwargs: dict, patch_name: str
) -> str | None:
    """Extract the prompt text from LLM call arguments."""
    if "litellm" in patch_name:
        messages = kwargs.get("messages") or (args[0] if args else None)
        if messages and isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    return msg.get("content", "")
            if isinstance(messages[-1], dict):
                return messages[-1].get("content", "")
            return str(messages[-1])
    elif "openai" in patch_name:
        messages = kwargs.get("messages") or (
            args[1] if len(args) > 1 else None
        )
        if messages and isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("role") == "user":
                    return msg.get("content", "")
    elif "langchain" in patch_name:
        prompts = args[1] if len(args) > 1 else kwargs.get("prompts", [])
        if prompts:
            return str(prompts[0])
    return None


def _extract_response_text(result: Any, patch_name: str) -> str | None:
    """Extract response text from LLM call result."""
    try:
        if "litellm" in patch_name or "openai" in patch_name:
            if hasattr(result, "choices") and result.choices:
                choice = result.choices[0]
                if hasattr(choice, "message"):
                    return choice.message.content
                if hasattr(choice, "text"):
                    return choice.text
        elif "langchain" in patch_name:
            if hasattr(result, "generations") and result.generations:
                first_gen = result.generations[0]
                return first_gen[0].text if first_gen else None
    except (IndexError, AttributeError):
        pass
    return None


def _extract_token_usage(result: Any) -> int | None:
    """Extract total token count from result."""
    try:
        if hasattr(result, "usage") and result.usage:
            return getattr(result.usage, "total_tokens", None)
    except AttributeError:
        pass
    return None


def _extract_model_name(kwargs: dict, result: Any) -> str | None:
    """Extract model name from kwargs or result."""
    model = kwargs.get("model")
    if model:
        return model
    if hasattr(result, "model"):
        return result.model
    return None


def _resolve_task(source: Any) -> str | None:
    """Resolve task name from task_map or auto-detect.

    Returns None if ignore_unmapped and prompt is not in task_map.
    """
    if _task_map and source and source.variable:
        mapped = _task_map.get(source.variable)
        if mapped:
            return mapped
        if _ignore_unmapped:
            return None
    if source:
        return source.task_name
    return None


def _send_trace(trace_data: dict) -> str | None:
    """Send trace to CT API. Returns trace_id or None on failure."""
    if not _api_key:
        logger.warning("KAIZEN_API_KEY not set — trace not sent")
        return None

    try:
        resp = httpx.post(
            f"{_base_url}/api/v1/traces",
            json=trace_data,
            headers={"X-API-Key": _api_key},
            timeout=5.0,
        )
        if resp.status_code == 201:
            return resp.json().get("id")
        logger.warning(
            "Trace upload failed: %s %s",
            resp.status_code,
            resp.text[:200],
        )
    except Exception:
        logger.warning("Trace upload failed", exc_info=True)
    return None


def _build_trace_data(
    prompt_text: str | None,
    source: Any,
    result: Any,
    kwargs: dict,
    latency_ms: float,
    patch_name: str,
) -> dict:
    """Build trace payload from captured data."""
    return {
        "task_id": source.task_name if source else "unknown",
        "prompt_text": prompt_text,
        "response_text": _extract_response_text(result, patch_name),
        "model": _extract_model_name(kwargs, result),
        "tokens": _extract_token_usage(result),
        "latency_ms": round(latency_ms, 2),
        "source_file": source.file if source else None,
        "source_variable": source.variable if source else None,
    }


def _attach_trace_helpers(result: Any, trace_id: str) -> None:
    """Attach ct_trace_id and ct_score helper to result object (D-17, D-18)."""
    try:
        result.ct_trace_id = trace_id
        result.ct_score = lambda score, scored_by="sdk": _score_trace(
            trace_id, score, scored_by
        )
    except (AttributeError, TypeError):
        pass


def _wrap_sync(original: Callable, patch_name: str) -> Callable:
    """Wrap a synchronous LLM call to capture traces."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        prompt_text = _extract_prompt_from_args(args, kwargs, patch_name)
        source = detect_prompt_source(prompt_text) if prompt_text else None
        task_name = _resolve_task(source)

        if task_name is None and _task_map and _ignore_unmapped:
            return original(*args, **kwargs)

        start = time.monotonic()
        result = original(*args, **kwargs)
        latency_ms = (time.monotonic() - start) * 1000

        trace_data = _build_trace_data(
            prompt_text, source, result, kwargs, latency_ms, patch_name
        )
        trace_id = _send_trace(trace_data)

        if trace_id is not None:
            _attach_trace_helpers(result, trace_id)

        return result

    return wrapper


def _wrap_async(original: Callable, patch_name: str) -> Callable:
    """Wrap an async LLM call to capture traces."""

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        prompt_text = _extract_prompt_from_args(args, kwargs, patch_name)
        source = detect_prompt_source(prompt_text) if prompt_text else None
        task_name = _resolve_task(source)

        if task_name is None and _task_map and _ignore_unmapped:
            return await original(*args, **kwargs)

        start = time.monotonic()
        result = await original(*args, **kwargs)
        latency_ms = (time.monotonic() - start) * 1000

        trace_data = _build_trace_data(
            prompt_text, source, result, kwargs, latency_ms, patch_name
        )
        trace_id = _send_trace(trace_data)

        if trace_id is not None:
            _attach_trace_helpers(result, trace_id)

        return result

    return wrapper


def _score_trace(
    trace_id: str, score: float, scored_by: str = "sdk"
) -> None:
    """Score a trace via the API (D-18)."""
    if not _api_key:
        logger.warning("KAIZEN_API_KEY not set — score not sent")
        return

    try:
        httpx.post(
            f"{_base_url}/api/v1/traces/{trace_id}/score",
            json={"score": score, "scored_by": scored_by},
            headers={"X-API-Key": _api_key},
            timeout=5.0,
        )
    except Exception:
        logger.warning(
            "Score upload failed for trace %s", trace_id, exc_info=True
        )
