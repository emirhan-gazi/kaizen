"""Optimization job status endpoints, including retry-PR (D-13)."""

import asyncio
import functools
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import JobResponse
from src.config import settings
from src.database import get_db
from src.models.base import OptimizationJob, PromptVersion, Task
from src.services.auto_pr import create_optimization_pr
from src.services.git_provider import get_git_provider
from src.utils.crypto import decrypt_token
from src.utils.pr_template import PRContext

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> JobResponse:
    """Get optimization job status from PostgreSQL."""
    job = await db.get(OptimizationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse.model_validate(job, from_attributes=True)


@router.get("/", response_model=list[JobResponse])
async def list_jobs(
    task_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> list[JobResponse]:
    """List optimization jobs, optionally filtered by task_id."""
    query = select(OptimizationJob).order_by(OptimizationJob.created_at.desc())

    if task_id is not None:
        query = query.where(OptimizationJob.task_id == task_id)

    query = query.limit(min(limit, 200)).offset(offset)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [JobResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/{job_id}/retry-pr", response_model=JobResponse)
async def retry_pr(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> JobResponse:
    """Retry PR creation for a job in PR_FAILED status (D-13).

    Re-attempts GitHub PR creation using the already-saved prompt version.
    Only allowed when job status is PR_FAILED.
    """
    job = await db.get(OptimizationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "PR_FAILED":
        raise HTTPException(
            status_code=409,
            detail=f"Job status is '{job.status}', retry-pr only allowed for PR_FAILED jobs",
        )

    if job.prompt_version_id is None:
        raise HTTPException(
            status_code=409,
            detail="No prompt version associated with this job",
        )

    # Load related objects
    prompt_version = await db.get(PromptVersion, job.prompt_version_id)
    if prompt_version is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    task = await db.get(Task, job.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get previous active prompt for comparison
    prev_query = (
        select(PromptVersion)
        .where(PromptVersion.task_id == task.id, PromptVersion.status == "active")
        .limit(1)
    )
    prev_result = await db.execute(prev_query)
    prev_prompt = prev_result.scalar_one_or_none()

    job_meta = job.job_metadata or {}

    ctx = PRContext(
        task_name=task.name,
        version_number=prompt_version.version_number,
        before_score=prev_prompt.eval_score if prev_prompt else None,
        after_score=prompt_version.eval_score or 0.0,
        feedback_count=job.feedback_count or 0,
        optimizer=prompt_version.optimizer or "MIPROv2",
        teacher_model=job_meta.get("teacher_model", settings.TEACHER_MODEL),
        judge_model=job_meta.get("judge_model", settings.JUDGE_MODEL),
        trials_completed=job_meta.get("trials_completed", 0),
        duration_seconds=job_meta.get("duration_seconds", 0),
        train_size=job_meta.get("train_size", 0),
        val_size=job_meta.get("val_size", 0),
        old_prompt_text=prev_prompt.prompt_text if prev_prompt else None,
        new_prompt_text=prompt_version.prompt_text or "",
        few_shot_examples=None,
        job_id=str(job.id),
        dspy_version=job_meta.get("dspy_version"),
        litellm_version=job_meta.get("litellm_version"),
        cost_usd=job_meta.get("cost_usd"),
    )

    # Resolve git provider (same logic as pipeline)
    token = decrypt_token(task.git_token_encrypted) if task.git_token_encrypted else None
    provider = get_git_provider(
        task.git_provider or "github",
        token=token or "",
        base_url=task.git_base_url or "",
        project=task.git_project or "",
        repo=task.git_repo or task.github_repo or "",
    )
    base_branch = task.git_base_branch or task.github_base_branch or "main"

    # Run sync call in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        functools.partial(
            create_optimization_pr,
            provider=provider,
            ctx=ctx,
            prompt_content=prompt_version.prompt_text or "",
            base_branch=base_branch,
            prompt_path=task.prompt_path,
            prompt_format=task.prompt_format or "text",
            prompt_file=task.prompt_file,
            prompt_locator=task.prompt_locator,
        ),
    )

    if result.success:
        job.pr_url = result.pr_url
        job.status = "SUCCESS"
        job.progress_step = "pr_retry_succeeded"
        # Clear old PR error from metadata
        if job.job_metadata and "pr_error" in job.job_metadata:
            meta = dict(job.job_metadata)
            del meta["pr_error"]
            job.job_metadata = meta
    else:
        # Still PR_FAILED but update error message
        if job.job_metadata is None:
            job.job_metadata = {}
        meta = dict(job.job_metadata)
        meta["pr_error"] = result.error
        meta["pr_retry_attempted"] = True
        job.job_metadata = meta

        raise HTTPException(
            status_code=502,
            detail=f"PR creation failed again: {result.error}",
        )

    return JobResponse.model_validate(job, from_attributes=True)
