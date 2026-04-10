"""Tests for kaizen_sdk.models — Pydantic response models."""

import uuid
from datetime import datetime, timezone

from kaizen_sdk.models import (
    CostEstimate,
    FeedbackResult,
    Job,
    OptimizeResult,
    Prompt,
    PromptVersion,
    Task,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


TASK_DICT = {
    "id": _uuid(),
    "name": "summarize_ticket",
    "description": "Summarise support tickets",
    "schema_json": {"type": "object"},
    "feedback_threshold": 50,
    "feedback_retention_limit": 500,
    "evaluator_config": None,
    "teacher_model": "gpt-4o",
    "judge_model": "gpt-4o-mini",
    "module_type": "predict",
    "cost_budget": 10.0,
    "github_repo": "org/repo",
    "github_base_branch": "main",
    "prompt_path": "prompts/summarize.txt",
    "prompt_format": "text",
    "created_at": _utcnow(),
    "feedback_count": 42,
    "last_optimization": _utcnow(),
    "active_prompt_score": 0.85,
    "threshold_progress": "42/50",
}


def test_task_model_from_dict():
    task = Task(**TASK_DICT)
    assert task.name == "summarize_ticket"
    assert task.feedback_threshold == 50
    assert task.feedback_count == 42
    assert task.threshold_progress == "42/50"
    assert isinstance(task.id, uuid.UUID)
    assert isinstance(task.created_at, datetime)


def test_task_schema_json_alias():
    """schema_json field is accessible via task_schema attribute."""
    task = Task(**TASK_DICT)
    assert task.task_schema == {"type": "object"}


def test_model_extra_ignore():
    data = {**TASK_DICT, "unknown_field": "should be ignored"}
    task = Task(**data)
    assert task.name == "summarize_ticket"
    assert not hasattr(task, "unknown_field")


def test_feedback_result_model():
    data = {
        "id": _uuid(),
        "task_id": _uuid(),
        "inputs": {"text": "hello"},
        "output": "summary",
        "score": 0.9,
        "source": "sdk",
        "metadata_": {"key": "value"},
        "created_at": _utcnow(),
    }
    fb = FeedbackResult(**data)
    assert isinstance(fb.id, uuid.UUID)
    assert fb.score == 0.9
    assert fb.metadata == {"key": "value"}


def test_feedback_result_optional_fields():
    data = {
        "id": _uuid(),
        "task_id": _uuid(),
        "created_at": _utcnow(),
    }
    fb = FeedbackResult(**data)
    assert fb.inputs is None
    assert fb.output is None
    assert fb.score is None


def test_prompt_model():
    data = {
        "id": _uuid(),
        "task_id": _uuid(),
        "version_number": 3,
        "prompt_text": "Summarize: {text}",
        "eval_score": 0.92,
        "status": "active",
        "optimizer": "mipro",
        "dspy_version": "2.6.0",
        "created_at": _utcnow(),
    }
    prompt = Prompt(**data)
    assert prompt.version_number == 3
    assert prompt.status == "active"
    assert prompt.eval_score == 0.92


def test_prompt_version_is_prompt():
    assert PromptVersion is Prompt


def test_job_model():
    data = {
        "id": _uuid(),
        "task_id": _uuid(),
        "prompt_version_id": _uuid(),
        "status": "completed",
        "triggered_by": "threshold",
        "feedback_count": 60,
        "pr_url": "https://github.com/org/repo/pull/1",
        "error_message": None,
        "job_metadata": {"optimizer": "mipro"},
        "progress_step": "done",
        "started_at": _utcnow(),
        "completed_at": _utcnow(),
        "created_at": _utcnow(),
    }
    job = Job(**data)
    assert job.status == "completed"
    assert job.pr_url == "https://github.com/org/repo/pull/1"
    assert isinstance(job.id, uuid.UUID)


def test_job_optional_fields():
    data = {
        "id": _uuid(),
        "task_id": _uuid(),
        "status": "pending",
        "created_at": _utcnow(),
    }
    job = Job(**data)
    assert job.prompt_version_id is None
    assert job.pr_url is None
    assert job.error_message is None


def test_cost_estimate_model():
    data = {
        "estimated_cost_usd": 1.50,
        "estimated_llm_calls": 200,
        "train_size": 40,
        "val_size": 10,
        "max_trials": 5,
        "teacher_model": "gpt-4o",
        "judge_model": "gpt-4o-mini",
    }
    ce = CostEstimate(**data)
    assert ce.estimated_cost_usd == 1.50
    assert ce.train_size == 40


def test_optimize_result_model():
    job_data = {
        "id": _uuid(),
        "task_id": _uuid(),
        "status": "running",
        "created_at": _utcnow(),
    }
    cost_data = {
        "estimated_cost_usd": 2.0,
        "estimated_llm_calls": 300,
        "train_size": 80,
        "val_size": 20,
        "max_trials": 10,
        "teacher_model": "gpt-4o",
        "judge_model": "gpt-4o-mini",
    }
    result = OptimizeResult(
        job=job_data,
        cost_estimate=cost_data,
        budget_warning="Exceeds budget",
    )
    assert isinstance(result.job, Job)
    assert isinstance(result.cost_estimate, CostEstimate)
    assert result.budget_warning == "Exceeds budget"
