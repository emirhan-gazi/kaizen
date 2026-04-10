"""Optimize endpoint — dispatches DSPy optimization jobs."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import CostEstimate, JobResponse, OptimizeResponse
from src.config import settings
from src.database import get_db
from src.models.base import FeedbackEntry, OptimizationJob, Task
from src.worker.cost_estimator import estimate_optimization_cost
from src.worker.tasks import run_optimization

router = APIRouter(prefix="/api/v1/optimize", tags=["optimize"])

# Active job statuses — a task can only have one at a time (FR-6.10)
_ACTIVE_STATUSES = ("PENDING", "RUNNING", "EVALUATING", "COMPILING")


@router.post("/{task_id}", response_model=OptimizeResponse)
async def trigger_optimization(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> OptimizeResponse:
    """Estimate cost, create job row, dispatch Celery optimization task.

    Returns job info + cost estimate immediately.  Budget warning is
    non-blocking per D-08 — the job still dispatches even if the estimate
    exceeds the task's budget.
    """
    # 1. Look up the task
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. Check for an already-active job (FR-6.10)
    active_query = select(OptimizationJob).where(
        OptimizationJob.task_id == task_id,
        OptimizationJob.status.in_(_ACTIVE_STATUSES),
    )
    active_result = await db.execute(active_query)
    if active_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Active optimization job already exists for this task",
        )

    # 3. Count available feedback
    count_result = await db.execute(
        select(func.count(FeedbackEntry.id)).where(
            FeedbackEntry.task_id == task_id
        )
    )
    feedback_count: int = count_result.scalar() or 0

    if feedback_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No feedback entries available for optimization",
        )

    # 4. Compute cost estimate
    teacher = task.teacher_model or settings.TEACHER_MODEL
    judge = task.judge_model or settings.JUDGE_MODEL
    max_trials = settings.MAX_TRIALS_DEFAULT

    cost_data = estimate_optimization_cost(
        feedback_count=feedback_count,
        max_trials=max_trials,
        teacher_model=teacher,
        judge_model=judge,
    )

    # 5. Determine budget and build warning (D-08, D-09)
    budget = task.cost_budget or settings.COST_BUDGET_DEFAULT
    budget_warning: str | None = None
    if cost_data["estimated_cost_usd"] > budget:
        budget_warning = (
            f"Estimated cost ${cost_data['estimated_cost_usd']:.2f} "
            f"exceeds budget ${budget:.2f}"
        )

    # 6. Create OptimizationJob row
    job = OptimizationJob(
        task_id=task_id,
        status="PENDING",
        triggered_by="api_on_demand",
        feedback_count=feedback_count,
        progress_step="PENDING",
    )
    db.add(job)
    await db.commit()  # commit before dispatch so worker can find the row

    # 7. Dispatch Celery task (job still dispatches even if over budget)
    run_optimization.delay(str(task_id), str(job.id))

    # 8. Build response
    job_response = JobResponse.model_validate(job, from_attributes=True)
    cost_estimate = CostEstimate(**cost_data)

    return OptimizeResponse(
        job=job_response,
        cost_estimate=cost_estimate,
        budget_warning=budget_warning,
    )
