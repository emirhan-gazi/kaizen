"""Task management endpoints."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import TaskCreate, TaskSummary
from src.database import get_db
from src.models.base import FeedbackEntry, OptimizationJob, PromptVersion, Task, Trace
from src.utils.crypto import encrypt_token

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.post("/", response_model=TaskSummary, status_code=201)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> TaskSummary:
    """Create a new task."""
    existing = await db.execute(select(Task).where(Task.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Task name already exists")

    task_data = body.model_dump(exclude={"github_token_raw", "git_token_raw"})
    task = Task(**task_data)
    # Encrypt git token: prefer git_token_raw, fall back to github_token_raw
    raw_token = body.git_token_raw or body.github_token_raw
    if raw_token:
        task.git_token_encrypted = encrypt_token(raw_token)
        task.github_token_encrypted = encrypt_token(raw_token)
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return TaskSummary(
        id=task.id,
        name=task.name,
        description=task.description,
        schema_json=task.schema_json,
        feedback_threshold=task.feedback_threshold,
        evaluator_config=task.evaluator_config,
        git_provider=task.git_provider,
        git_base_url=task.git_base_url,
        git_project=task.git_project,
        git_repo=task.git_repo,
        git_base_branch=task.git_base_branch,
        github_repo=task.github_repo,
        github_base_branch=task.github_base_branch,
        prompt_path=task.prompt_path,
        prompt_format=task.prompt_format,
        mode=task.mode,
        created_at=task.created_at,
        feedback_count=0,
        last_optimization=None,
        active_prompt_score=None,
        threshold_progress=f"0/{task.feedback_threshold}",
    )


@router.get("/", response_model=list[TaskSummary])
async def list_tasks(
    cursor: datetime | None = Query(None, description="Cursor: created_at of last item"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> list[TaskSummary]:
    """List all tasks with rich summary — cursor-based pagination."""
    # Subquery: live feedback count per task (excludes seeds — D-07, D-11)
    fb_sq = (
        select(
            FeedbackEntry.task_id,
            func.count(FeedbackEntry.id).label("feedback_count"),
        )
        .where(FeedbackEntry.source != "seed")
        .group_by(FeedbackEntry.task_id)
        .subquery()
    )

    # Subquery: last optimization date per task
    job_sq = (
        select(
            OptimizationJob.task_id,
            func.max(OptimizationJob.completed_at).label("last_optimization"),
        )
        .where(OptimizationJob.status == "SUCCESS")
        .group_by(OptimizationJob.task_id)
        .subquery()
    )

    # Subquery: active prompt score per task
    prompt_sq = (
        select(
            PromptVersion.task_id,
            PromptVersion.eval_score.label("active_prompt_score"),
        )
        .where(PromptVersion.status == "active")
        .subquery()
    )

    query = (
        select(
            Task,
            func.coalesce(fb_sq.c.feedback_count, 0).label("feedback_count"),
            job_sq.c.last_optimization,
            prompt_sq.c.active_prompt_score,
        )
        .outerjoin(fb_sq, Task.id == fb_sq.c.task_id)
        .outerjoin(job_sq, Task.id == job_sq.c.task_id)
        .outerjoin(prompt_sq, Task.id == prompt_sq.c.task_id)
        .order_by(Task.created_at.desc())
        .limit(limit)
    )

    if cursor is not None:
        query = query.where(Task.created_at < cursor)

    result = await db.execute(query)
    rows = result.all()

    summaries = []
    for task, fb_count, last_opt, prompt_score in rows:
        summaries.append(
            TaskSummary(
                id=task.id,
                name=task.name,
                description=task.description,
                schema_json=task.schema_json,
                feedback_threshold=task.feedback_threshold,
                evaluator_config=task.evaluator_config,
                git_provider=task.git_provider,
                git_base_url=task.git_base_url,
                git_project=task.git_project,
                git_repo=task.git_repo,
                git_base_branch=task.git_base_branch,
                github_repo=task.github_repo,
                github_base_branch=task.github_base_branch,
                prompt_path=task.prompt_path,
                prompt_format=task.prompt_format,
                mode=task.mode,
                optimizer_type=task.optimizer_type,
                gepa_config=task.gepa_config,
                created_at=task.created_at,
                feedback_count=fb_count,
                last_optimization=last_opt,
                active_prompt_score=prompt_score,
                threshold_progress=f"{fb_count}/{task.feedback_threshold}",
            )
        )
    return summaries


@router.get("/{task_id}", response_model=TaskSummary)
async def get_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> TaskSummary:
    """Get a single task by ID with rich summary."""
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Live feedback only — excludes seeds (D-07, D-11)
    fb_count_result = await db.execute(
        select(func.count(FeedbackEntry.id)).where(
            FeedbackEntry.task_id == task_id,
            FeedbackEntry.source != "seed",
        )
    )
    fb_count = fb_count_result.scalar() or 0

    last_opt_result = await db.execute(
        select(func.max(OptimizationJob.completed_at)).where(
            OptimizationJob.task_id == task_id,
            OptimizationJob.status == "SUCCESS",
        )
    )
    last_opt = last_opt_result.scalar()

    prompt_result = await db.execute(
        select(PromptVersion.eval_score).where(
            PromptVersion.task_id == task_id,
            PromptVersion.status == "active",
        )
    )
    prompt_score = prompt_result.scalar()

    return TaskSummary(
        id=task.id,
        name=task.name,
        description=task.description,
        schema_json=task.schema_json,
        feedback_threshold=task.feedback_threshold,
        evaluator_config=task.evaluator_config,
        git_provider=task.git_provider,
        git_base_url=task.git_base_url,
        git_project=task.git_project,
        git_repo=task.git_repo,
        git_base_branch=task.git_base_branch,
        github_repo=task.github_repo,
        github_base_branch=task.github_base_branch,
        prompt_path=task.prompt_path,
        prompt_format=task.prompt_format,
        mode=task.mode,
        optimizer_type=task.optimizer_type,
        gepa_config=task.gepa_config,
        created_at=task.created_at,
        feedback_count=fb_count,
        last_optimization=last_opt,
        active_prompt_score=prompt_score,
        threshold_progress=f"{fb_count}/{task.feedback_threshold}",
    )


@router.delete("/{task_id}", status_code=204)
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> None:
    """Delete a task and all related data (feedback, jobs, prompts, traces)."""
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    await db.execute(delete(OptimizationJob).where(OptimizationJob.task_id == task_id))
    await db.execute(delete(PromptVersion).where(PromptVersion.task_id == task_id))
    await db.execute(delete(FeedbackEntry).where(FeedbackEntry.task_id == task_id))
    await db.execute(delete(Trace).where(Trace.task_id == task_id))
    await db.delete(task)

