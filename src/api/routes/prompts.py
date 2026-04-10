"""Prompt retrieval endpoints with Redis caching."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import PromptResponse
from src.config import settings
from src.database import get_db, redis_client
from src.models.base import PromptVersion, Task

router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


def _cache_key(task_id: uuid.UUID) -> str:
    return f"prompt:active:{task_id}"


@router.get("/{task_id}", response_model=PromptResponse)
async def get_active_prompt(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> PromptResponse:
    """Return the active prompt for a task, served from Redis cache when available."""
    # Check cache first
    cache_key = _cache_key(task_id)
    cached = await redis_client.get(cache_key)
    if cached is not None:
        return PromptResponse.model_validate_json(cached)

    # Verify task exists
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Query active prompt
    result = await db.execute(
        select(PromptVersion)
        .where(
            PromptVersion.task_id == task_id,
            PromptVersion.status == "active",
        )
        .order_by(PromptVersion.version_number.desc())
        .limit(1)
    )
    prompt = result.scalar_one_or_none()

    if prompt is None:
        raise HTTPException(
            status_code=404,
            detail="No active prompt for this task",
        )

    response = PromptResponse.model_validate(prompt, from_attributes=True)

    # Populate cache
    await redis_client.set(
        cache_key,
        response.model_dump_json(),
        ex=settings.PROMPT_CACHE_TTL,
    )

    return response


@router.post("/{task_id}/activate", response_model=PromptResponse)
async def activate_prompt(
    task_id: uuid.UUID,
    version_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> PromptResponse:
    """Promote a draft prompt to active, archiving the current active version."""
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Find the draft version to activate
    draft = await db.get(PromptVersion, version_id)
    if draft is None or draft.task_id != task_id:
        raise HTTPException(status_code=404, detail="Prompt version not found for this task")
    if draft.status != "draft":
        raise HTTPException(status_code=409, detail=f"Version is '{draft.status}', not 'draft'")

    # Archive current active version
    result = await db.execute(
        select(PromptVersion).where(
            PromptVersion.task_id == task_id,
            PromptVersion.status == "active",
        )
    )
    current_active = result.scalar_one_or_none()
    if current_active:
        current_active.status = "archived"

    # Activate the draft
    draft.status = "active"
    await db.commit()
    await db.refresh(draft)

    # Invalidate Redis cache
    await redis_client.delete(_cache_key(task_id))

    return PromptResponse.model_validate(draft, from_attributes=True)


@router.get("/{task_id}/versions", response_model=list[PromptResponse])
async def list_prompt_versions(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> list[PromptResponse]:
    """List all prompt versions for a task."""
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await db.execute(
        select(PromptVersion)
        .where(PromptVersion.task_id == task_id)
        .order_by(PromptVersion.version_number.desc())
    )
    rows = result.scalars().all()
    return [
        PromptResponse.model_validate(row, from_attributes=True) for row in rows
    ]
