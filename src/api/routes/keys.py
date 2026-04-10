"""API key management endpoints."""

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import hash_api_key, require_api_key
from src.api.schemas import ApiKeyCreate, ApiKeyCreatedResponse, ApiKeyListItem
from src.database import get_db
from src.models.base import ApiKey

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


@router.get("/status")
async def keys_status(db: AsyncSession = Depends(get_db)) -> dict:
    """Check if any API keys exist. No auth required."""
    count_result = await db.execute(
        select(func.count(ApiKey.id)).where(ApiKey.revoked_at.is_(None))
    )
    count = count_result.scalar() or 0
    return {"has_keys": count > 0, "count": count}


@router.get("/", response_model=list[ApiKeyListItem])
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> list[ApiKeyListItem]:
    """List all API keys (without hashes)."""
    result = await db.execute(
        select(ApiKey).order_by(ApiKey.created_at.desc())
    )
    return [
        ApiKeyListItem.model_validate(row, from_attributes=True)
        for row in result.scalars().all()
    ]


@router.post("/", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> ApiKeyCreatedResponse:
    """Create a new API key. The raw key is returned only once."""
    raw_key = "kaizen_" + secrets.token_hex(16)
    key_hash = hash_api_key(raw_key)

    row = ApiKey(key_hash=key_hash, label=body.label)
    db.add(row)
    await db.flush()
    await db.refresh(row)

    return ApiKeyCreatedResponse(
        id=row.id,
        key=raw_key,
        label=row.label,
        created_at=row.created_at,
    )


@router.delete("/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _key=Depends(require_api_key),
) -> None:
    """Revoke an API key by setting revoked_at timestamp."""
    row = await db.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if row.revoked_at is not None:
        raise HTTPException(status_code=409, detail="API key already revoked")
    row.revoked_at = datetime.now(timezone.utc)
    await db.flush()


@router.post("/bootstrap", response_model=ApiKeyCreatedResponse, status_code=201)
async def bootstrap_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreatedResponse:
    """Create the first API key without authentication.

    This endpoint only works when no API keys exist yet.
    Once a key exists, it returns 403.
    """
    count_result = await db.execute(select(func.count(ApiKey.id)))
    count = count_result.scalar() or 0

    if count > 0:
        raise HTTPException(
            status_code=403,
            detail="Bootstrap disabled: API keys already exist",
        )

    raw_key = "kaizen_" + secrets.token_hex(16)
    key_hash = hash_api_key(raw_key)

    row = ApiKey(key_hash=key_hash, label=body.label or "bootstrap")
    db.add(row)
    await db.flush()
    await db.refresh(row)

    return ApiKeyCreatedResponse(
        id=row.id,
        key=raw_key,
        label=row.label,
        created_at=row.created_at,
    )
