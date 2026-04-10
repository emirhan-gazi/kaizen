"""Typed Pydantic response models for the Kaizen SDK.

These models mirror server API responses independently (no imports from server code).
All models use extra='ignore' so new server fields don't break old SDK versions.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class Task(BaseModel):
    """A tuning task (e.g. 'summarize_ticket') with its configuration and status."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: uuid.UUID
    name: str
    description: str | None = None
    task_schema: dict | None = Field(None, alias="schema_json")
    feedback_threshold: int
    feedback_retention_limit: int = 1000
    evaluator_config: dict | None = None
    teacher_model: str | None = None
    judge_model: str | None = None
    module_type: str = "predict"
    cost_budget: float | None = None
    github_repo: str | None = None
    github_base_branch: str | None = None
    prompt_path: str | None = None
    prompt_format: str | None = None
    created_at: datetime
    feedback_count: int = 0
    last_optimization: datetime | None = None
    active_prompt_score: float | None = None
    threshold_progress: str = "0/50"


class FeedbackResult(BaseModel):
    """A single feedback entry logged for a task."""

    model_config = {"extra": "ignore"}

    id: uuid.UUID
    task_id: uuid.UUID
    inputs: dict | None = None
    output: str | None = None
    score: float | None = None
    source: str | None = None
    metadata: dict | None = Field(None, alias="metadata_")
    created_at: datetime


class Prompt(BaseModel):
    """A prompt version produced by optimization."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: uuid.UUID
    task_id: uuid.UUID
    version_number: int
    prompt_text: str | None = None
    eval_score: float | None = None
    status: str
    optimizer: str | None = None
    dspy_version: str | None = None
    created_at: datetime


# PromptVersion is a semantic alias for Prompt used in listing contexts
PromptVersion = Prompt


class Job(BaseModel):
    """An optimization job (running or completed)."""

    model_config = {"extra": "ignore"}

    id: uuid.UUID
    task_id: uuid.UUID
    prompt_version_id: uuid.UUID | None = None
    status: str
    triggered_by: str | None = None
    feedback_count: int | None = None
    pr_url: str | None = None
    error_message: str | None = None
    job_metadata: dict | None = None
    progress_step: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime


class CostEstimate(BaseModel):
    """Estimated cost for an optimization run."""

    model_config = {"extra": "ignore"}

    estimated_cost_usd: float
    estimated_llm_calls: int
    train_size: int
    val_size: int
    max_trials: int
    teacher_model: str
    judge_model: str


class OptimizeResult(BaseModel):
    """Result of triggering an optimization — includes the job and cost estimate."""

    model_config = {"extra": "ignore"}

    job: Job
    cost_estimate: CostEstimate
    budget_warning: str | None = None


class TraceResult(BaseModel):
    """A trace captured by the auto-instrument SDK."""

    model_config = {"extra": "ignore"}

    id: uuid.UUID
    task_id: uuid.UUID
    prompt_text: str | None = None
    response_text: str | None = None
    model: str | None = None
    tokens: int | None = None
    latency_ms: float | None = None
    source_file: str | None = None
    source_variable: str | None = None
    score: float | None = None
    scored_by: str | None = None
    created_at: datetime
