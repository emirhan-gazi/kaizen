"""Pydantic schemas for API request/response validation."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# --- Tasks ---


class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    schema_json: dict | None = None
    feedback_threshold: int = Field(default=50, ge=1)
    feedback_retention_limit: int = Field(default=1000, ge=1)
    evaluator_config: dict | None = None
    teacher_model: str | None = None
    judge_model: str | None = None
    module_type: str = Field(default="predict", pattern=r"^(predict|chain_of_thought)$")
    cost_budget: float | None = Field(default=None, gt=0)
    # Git provider config (per-task overrides)
    git_provider: str | None = Field(default=None, pattern=r"^(github|bitbucket_server|gitlab)$")
    git_base_url: str | None = None
    git_token_raw: str | None = Field(default=None, repr=False)
    git_project: str | None = None
    git_repo: str | None = None
    git_base_branch: str | None = None
    prompt_path: str | None = None
    prompt_format: str | None = Field(default=None, pattern=r"^(json|text|yaml|python)$")
    prompt_file: str | None = None
    prompt_locator: str | None = None
    feedback_source: str = Field(default="sdk", pattern=r"^(sdk|traces)$")
    auto_eval: bool = False
    # Legacy aliases (backwards compat)
    github_repo: str | None = None
    github_base_branch: str | None = None
    github_token_raw: str | None = Field(default=None, repr=False)


class TaskSummary(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    schema_json: dict | None
    feedback_threshold: int
    feedback_retention_limit: int = 1000
    evaluator_config: dict | None = None
    teacher_model: str | None = None
    judge_model: str | None = None
    module_type: str = "predict"
    cost_budget: float | None = None
    git_provider: str | None = None
    git_base_url: str | None = None
    git_project: str | None = None
    git_repo: str | None = None
    git_base_branch: str | None = None
    prompt_path: str | None = None
    prompt_format: str | None = None
    prompt_file: str | None = None
    prompt_locator: str | None = None
    feedback_source: str = "sdk"
    auto_eval: bool = False
    # Legacy aliases (backwards compat)
    github_repo: str | None = None
    github_base_branch: str | None = None
    created_at: datetime
    feedback_count: int = 0
    last_optimization: datetime | None = None
    active_prompt_score: float | None = None
    threshold_progress: str = "0/50"

    model_config = {"from_attributes": True}


# --- Feedback ---


class FeedbackCreate(BaseModel):
    task_id: uuid.UUID | None = None
    task_name: str | None = None
    inputs: dict | None = None
    output: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    source: Literal["sdk", "user_rating", "auto_eval", "seed"] = "sdk"
    metadata: dict | None = None
    prompt_file: str | None = None
    prompt_locator: str | None = None
    # Git config (sent by SDK, used when auto-creating tasks)
    git_provider: str | None = None
    git_base_url: str | None = None
    git_token: str | None = Field(default=None, repr=False)
    git_project: str | None = None
    git_repo: str | None = None
    git_base_branch: str | None = None
    # Task config (sent by SDK, used when auto-creating tasks)
    feedback_threshold: int | None = None
    teacher_model: str | None = None
    judge_model: str | None = None

    @model_validator(mode="after")
    def require_task_id_or_name(self) -> "FeedbackCreate":
        if self.task_id is None and self.task_name is None:
            raise ValueError("Either task_id or task_name must be provided")
        return self


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    inputs: dict | None
    output: str | None
    score: float | None
    source: str | None
    metadata: dict | None = Field(None, alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


# --- Prompts ---


class PromptResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    version_number: int
    prompt_text: str | None
    eval_score: float | None
    judge_score: float | None = None
    status: str
    optimizer: str | None
    dspy_version: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- Jobs ---


class JobResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    prompt_version_id: uuid.UUID | None
    status: str
    triggered_by: str | None
    feedback_count: int | None
    pr_url: str | None
    error_message: str | None
    job_metadata: dict | None = None
    progress_step: str | None = None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# --- API Keys ---


# --- Optimize ---


class CostEstimate(BaseModel):
    estimated_cost_usd: float
    estimated_llm_calls: int
    train_size: int
    val_size: int
    max_trials: int
    teacher_model: str
    judge_model: str


class OptimizeResponse(BaseModel):
    job: JobResponse
    cost_estimate: CostEstimate
    budget_warning: str | None = None  # "Estimated cost $X exceeds budget $Y" per D-09


# --- API Keys ---


class SeedUploadResponse(BaseModel):
    accepted: int
    rejected: int
    errors: list[str] = []
    total_seeds: int
    seed_limit: int


# --- Traces ---


class TraceCreate(BaseModel):
    task_id: uuid.UUID
    prompt_text: str | None = None
    response_text: str | None = None
    model: str | None = None
    tokens: int | None = None
    latency_ms: float | None = None
    source_file: str | None = None
    source_variable: str | None = None
    metadata: dict | None = None


class TraceResponse(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    prompt_text: str | None
    response_text: str | None
    model: str | None
    tokens: int | None
    latency_ms: float | None
    source_file: str | None
    source_variable: str | None
    score: float | None
    scored_by: str | None
    metadata: dict | None = Field(None, alias="metadata_")
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class TraceScoreRequest(BaseModel):
    score: float = Field(..., ge=0.0, le=1.0)
    scored_by: str = "sdk"


class ApiKeyCreate(BaseModel):
    label: str | None = None


class ApiKeyCreatedResponse(BaseModel):
    id: uuid.UUID
    key: str
    label: str | None
    created_at: datetime


class ApiKeyListItem(BaseModel):
    id: uuid.UUID
    label: str | None
    created_at: datetime
    revoked_at: datetime | None = None

    model_config = {"from_attributes": True}
