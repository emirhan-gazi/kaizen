"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import register_exception_handlers
from src.api.routes import feedback, jobs, keys, optimize, prompts, seed, tasks, traces

logger = logging.getLogger("kaizen")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan handler."""
    yield


app = FastAPI(title="Kaizen", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


# Public health check (no auth, not under /api/v1/ — D-04)
@app.get("/health")
async def health():
    return {"status": "ok"}


# Authenticated API routes
app.include_router(tasks.router)
app.include_router(feedback.router)
app.include_router(prompts.router)
app.include_router(jobs.router)
app.include_router(keys.router)
app.include_router(optimize.router)
app.include_router(seed.router)
app.include_router(traces.router)
