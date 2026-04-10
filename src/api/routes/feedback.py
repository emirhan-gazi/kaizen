"""Feedback ingestion endpoints with auto-trigger threshold check."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import FeedbackCreate, FeedbackResponse
from src.config import settings
from src.database import get_db, redis_client
from src.models.base import FeedbackEntry, OptimizationJob, Task
from src.utils.crypto import encrypt_token

logger = logging.getLogger("kaizen")

router = APIRouter(prefix="/api/v1/feedback", tags=["feedback"])

# Active job statuses — must match optimize.py (FR-6.10)
_ACTIVE_STATUSES = ("PENDING", "RUNNING", "EVALUATING", "COMPILING")


async def _check_auto_trigger(task: Task, db: AsyncSession) -> None:
    """Check if live feedback count crosses threshold and auto-dispatch optimization.

    Uses Redis lock to prevent duplicate dispatch at threshold boundary (D-03, FR-7.2).
    Rolling window: counts entries where source != 'seed' and created_at > last optimization (D-02).
    """
    # Only live feedback counts toward threshold (D-07)
    # Rolling window: count new entries since last completed optimization
    last_opt_query = select(func.max(OptimizationJob.completed_at)).where(
        OptimizationJob.task_id == task.id,
        OptimizationJob.status == "SUCCESS",
    )
    last_opt_result = await db.execute(last_opt_query)
    last_opt_at = last_opt_result.scalar()

    count_query = select(func.count(FeedbackEntry.id)).where(
        FeedbackEntry.task_id == task.id,
        FeedbackEntry.source != "seed",
    )
    if last_opt_at is not None:
        count_query = count_query.where(FeedbackEntry.created_at > last_opt_at)

    count_result = await db.execute(count_query)
    live_count: int = count_result.scalar() or 0

    if live_count < task.feedback_threshold:
        return

    # Threshold reached — try to acquire Redis lock (D-03)
    lock_key = f"lock:optimize:{task.id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=300)
    if not acquired:
        logger.info(
            "Auto-trigger skipped for task %s — lock already held", task.id
        )
        return

    # Check no active job exists (FR-6.10)
    active_result = await db.execute(
        select(OptimizationJob).where(
            OptimizationJob.task_id == task.id,
            OptimizationJob.status.in_(_ACTIVE_STATUSES),
        )
    )
    if active_result.scalar_one_or_none() is not None:
        logger.info(
            "Auto-trigger skipped for task %s — active job exists", task.id
        )
        return

    # Count total feedback for the job record (including seeds for dataset)
    total_count_result = await db.execute(
        select(func.count(FeedbackEntry.id)).where(
            FeedbackEntry.task_id == task.id
        )
    )
    total_count: int = total_count_result.scalar() or 0

    # Create job and dispatch
    job = OptimizationJob(
        task_id=task.id,
        status="PENDING",
        triggered_by="auto_threshold",
        feedback_count=total_count,
        progress_step="PENDING",
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    # Import here to avoid circular imports at module load
    from src.worker.tasks import run_optimization  # noqa: PLC0415

    run_optimization.delay(str(task.id), str(job.id))
    logger.info(
        "Auto-triggered optimization for task %s (live_count=%d, threshold=%d, job=%s)",
        task.id,
        live_count,
        task.feedback_threshold,
        job.id,
    )


async def _resolve_task(body: FeedbackCreate, db: AsyncSession) -> Task:
    """Resolve task by task_id or task_name, auto-creating if needed."""
    # Lookup by task_id (existing behaviour)
    if body.task_id is not None:
        task = await db.get(Task, body.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    # Lookup by task_name — upsert if missing
    assert body.task_name is not None  # guaranteed by schema validator
    result = await db.execute(
        select(Task).where(Task.name == body.task_name)
    )
    task = result.scalar_one_or_none()
    if task is not None:
        return task

    # Auto-create task from feedback context
    schema_json = (
        {k: "string" for k in body.inputs.keys()} if body.inputs else None
    )
    # Git config: prefer client-sent values, fall back to server settings
    git_token_raw = body.git_token or settings.GIT_TOKEN
    git_token_encrypted = encrypt_token(git_token_raw) if git_token_raw else None
    task = Task(
        name=body.task_name,
        schema_json=schema_json,
        feedback_threshold=body.feedback_threshold or 5,
        feedback_source="sdk",
        teacher_model=body.teacher_model,
        judge_model=body.judge_model,
        git_provider=body.git_provider or settings.GIT_PROVIDER or None,
        git_base_url=body.git_base_url or settings.GIT_BASE_URL or None,
        git_token_encrypted=git_token_encrypted,
        git_project=body.git_project or settings.GIT_PROJECT or None,
        git_repo=body.git_repo or settings.GIT_REPO or None,
        git_base_branch=body.git_base_branch or settings.GIT_BASE_BRANCH or None,
        prompt_file=body.prompt_file,
        prompt_locator=body.prompt_locator,
        mode=body.mode or "optimize_only",
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    logger.info("Auto-created task %s (id=%s) from feedback", body.task_name, task.id)
    return task


@router.post("/", response_model=FeedbackResponse, status_code=201)
async def create_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> FeedbackResponse:
    """Submit feedback for a task. Auto-triggers optimization at threshold (FR-7.1)."""
    task = await _resolve_task(body, db)
    auto_created = body.task_id is None and body.task_name is not None

    # Validate inputs against task schema — strict exact field match (D-05)
    # Skip validation for auto-created tasks (schema was inferred, not enforced)
    if task.schema_json and not auto_created:
        expected_fields = set(task.schema_json.keys())
        actual_fields = set((body.inputs or {}).keys())
        missing = expected_fields - actual_fields
        extra = actual_fields - expected_fields
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"Missing required input fields: {sorted(missing)}",
            )
        if extra:
            raise HTTPException(
                status_code=422,
                detail=f"Unexpected input fields: {sorted(extra)}",
            )

    entry = FeedbackEntry(
        task_id=task.id,
        inputs=body.inputs,
        output=body.output,
        score=body.score,
        source=body.source,
        metadata_=body.metadata,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)

    # Auto-trigger check — inline after insert (D-01, D-05)
    # Only for non-seed feedback (D-07)
    if body.source != "seed":
        try:
            await _check_auto_trigger(task, db)
        except Exception:
            # Auto-trigger failure must not break feedback ingestion
            logger.exception(
                "Auto-trigger check failed for task %s", task.id
            )

    return FeedbackResponse.model_validate(entry, from_attributes=True)


@router.get("/", response_model=list[FeedbackResponse])
async def list_feedback(
    task_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> list[FeedbackResponse]:
    """List feedback entries, optionally filtered by task_id."""
    query = select(FeedbackEntry).order_by(FeedbackEntry.created_at.desc())

    if task_id is not None:
        query = query.where(FeedbackEntry.task_id == task_id)

    query = query.limit(min(limit, 1000)).offset(offset)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        FeedbackResponse.model_validate(row, from_attributes=True) for row in rows
    ]
