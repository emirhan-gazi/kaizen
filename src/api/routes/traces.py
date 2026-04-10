"""Trace ingestion and scoring endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_api_key
from src.api.schemas import TraceCreate, TraceResponse, TraceScoreRequest
from src.database import get_db
from src.models.base import Task, Trace

logger = logging.getLogger("kaizen")

router = APIRouter(prefix="/api/v1/traces", tags=["traces"])


@router.post("/", response_model=TraceResponse, status_code=201)
async def create_trace(
    body: TraceCreate,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> TraceResponse:
    """Ingest a trace from the SDK (D-12)."""
    task = await db.get(Task, body.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    trace = Trace(
        task_id=body.task_id,
        prompt_text=body.prompt_text,
        response_text=body.response_text,
        model=body.model,
        tokens=body.tokens,
        latency_ms=body.latency_ms,
        source_file=body.source_file,
        source_variable=body.source_variable,
        metadata_=body.metadata,
    )
    db.add(trace)
    await db.flush()
    await db.refresh(trace)
    return TraceResponse.model_validate(trace, from_attributes=True)


@router.post("/{trace_id}/score", response_model=TraceResponse)
async def score_trace(
    trace_id: uuid.UUID,
    body: TraceScoreRequest,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> TraceResponse:
    """Score an existing trace (D-13, Option A)."""
    trace = await db.get(Trace, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    trace.score = body.score
    trace.scored_by = body.scored_by
    await db.flush()
    await db.refresh(trace)
    return TraceResponse.model_validate(trace, from_attributes=True)


@router.get("/", response_model=list[TraceResponse])
async def list_traces(
    task_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> list[TraceResponse]:
    """List traces, optionally filtered by task_id."""
    query = select(Trace).order_by(Trace.created_at.desc())
    if task_id is not None:
        query = query.where(Trace.task_id == task_id)
    query = query.limit(min(limit, 1000)).offset(offset)
    result = await db.execute(query)
    rows = result.scalars().all()
    return [TraceResponse.model_validate(row, from_attributes=True) for row in rows]
