"""Seed dataset upload endpoint for cold-start bootstrap (D-06 through D-10)."""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import SeedUploadResponse
from src.config import settings
from src.database import get_db
from src.models.base import FeedbackEntry, Task

logger = logging.getLogger("kaizen")

router = APIRouter(prefix="/api/v1/tasks", tags=["seed"])


@router.post("/{task_id}/seed", response_model=SeedUploadResponse, status_code=201)
async def upload_seed_dataset(
    task_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> SeedUploadResponse:
    """Upload a JSONL seed dataset to bootstrap a cold-start task.

    Each line must be JSON with keys: inputs (dict), output (str), score (float 0-1).
    Seeds are stored with source='seed' and do NOT count toward auto-trigger (D-07).
    """
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Check existing seed count for this task (D-09)
    existing_count_result = await db.execute(
        select(func.count(FeedbackEntry.id)).where(
            FeedbackEntry.task_id == task_id,
            FeedbackEntry.source == "seed",
        )
    )
    existing_seed_count: int = existing_count_result.scalar() or 0
    seed_limit = settings.SEED_SIZE_LIMIT  # configurable per task in future
    remaining_capacity = max(0, seed_limit - existing_seed_count)

    if remaining_capacity == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Seed limit reached ({seed_limit} entries) for this task",
        )

    # Read and parse JSONL
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")  # noqa: B904

    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="Empty file — no seed entries found")

    # Parse and validate each line
    accepted = 0
    errors: list[str] = []

    # Build expected fields from task schema for validation (D-10)
    expected_fields: set[str] | None = None
    if task.schema_json:
        expected_fields = set(task.schema_json.get("fields", []))

    for i, line in enumerate(lines, start=1):
        if accepted >= remaining_capacity:
            errors.append(f"Line {i}: skipped — seed limit reached ({seed_limit})")
            break

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Line {i}: invalid JSON — {exc}")
            continue

        if not isinstance(record, dict):
            errors.append(f"Line {i}: expected JSON object")
            continue

        # Validate required keys
        inputs = record.get("inputs")
        output = record.get("output")
        score = record.get("score")

        if inputs is not None and not isinstance(inputs, dict):
            errors.append(f"Line {i}: 'inputs' must be a JSON object")
            continue

        if score is not None:
            try:
                score = float(score)
                if not (0.0 <= score <= 1.0):
                    errors.append(f"Line {i}: 'score' must be between 0.0 and 1.0")
                    continue
            except (TypeError, ValueError):
                errors.append(f"Line {i}: 'score' must be a number")
                continue

        # Schema validation — same strict match as regular feedback (D-10)
        if expected_fields and inputs:
            actual_fields = set(inputs.keys())
            missing = expected_fields - actual_fields
            extra = actual_fields - expected_fields
            if missing:
                errors.append(f"Line {i}: missing input fields: {sorted(missing)}")
                continue
            if extra:
                errors.append(f"Line {i}: unexpected input fields: {sorted(extra)}")
                continue

        entry = FeedbackEntry(
            task_id=task_id,
            inputs=inputs,
            output=str(output) if output is not None else None,
            score=score,
            source="seed",
            metadata_={"seed_line": i},
        )
        db.add(entry)
        accepted += 1

    if accepted > 0:
        await db.flush()

    if accepted == 0:
        raise HTTPException(
            status_code=422,
            detail=f"No valid seed entries found. Errors: {errors[:10]}",
        )

    logger.info(
        "Seed upload for task %s: %d accepted, %d errors",
        task_id,
        accepted,
        len(errors),
    )

    return SeedUploadResponse(
        accepted=accepted,
        rejected=len(errors),
        errors=errors[:20],  # Return first 20 errors for debugging
        total_seeds=existing_seed_count + accepted,
        seed_limit=seed_limit,
    )
