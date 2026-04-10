"""API key authentication middleware."""

import hashlib

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.base import ApiKey

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of a raw API key for storage and lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """FastAPI dependency that validates the X-API-Key header.

    Returns the ApiKey row if valid; raises 401 otherwise.
    """
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = hash_api_key(api_key)
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.revoked_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    return row
