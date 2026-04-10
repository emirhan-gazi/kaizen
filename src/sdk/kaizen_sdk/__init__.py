"""Kaizen Python SDK."""

# New minimal API
from kaizen_sdk.core import (
    close,
    flush,
    flush_sync,
    get_buffered_traces,
    get_prompt,
    init,
    reset_buffer,
    trace,
    trace_sync,
)

# Legacy clients (kept for backwards compat)
from kaizen_sdk.async_client import AsyncCTClient
from kaizen_sdk.client import CTClient
from kaizen_sdk.detect import PromptSource, detect_prompt_source
from kaizen_sdk.exceptions import (
    CTAuthError,
    CTError,
    CTNotFoundError,
    CTServerError,
    CTValidationError,
)
from kaizen_sdk.instrument import instrument
from kaizen_sdk.models import (
    CostEstimate,
    FeedbackResult,
    Job,
    OptimizeResult,
    Prompt,
    PromptVersion,
    Task,
    TraceResult,
)

__all__ = [
    # New minimal API
    "init",
    "trace",
    "trace_sync",
    "flush",
    "flush_sync",
    "get_prompt",
    "get_buffered_traces",
    "reset_buffer",
    "close",
    # Legacy
    "CTClient",
    "AsyncCTClient",
    "Task",
    "Prompt",
    "Job",
    "FeedbackResult",
    "PromptVersion",
    "CostEstimate",
    "OptimizeResult",
    "TraceResult",
    "CTError",
    "CTAuthError",
    "CTValidationError",
    "CTNotFoundError",
    "CTServerError",
    "instrument",
    "PromptSource",
    "detect_prompt_source",
]
