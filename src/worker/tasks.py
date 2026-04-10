from src.config import settings
from src.worker.celery_app import app


@app.task(name="test_noop")
def test_noop():
    """No-op task to verify Celery worker connects to Redis broker."""
    return {"status": "ok"}


@app.task(
    name="run_optimization",
    bind=True,
    time_limit=settings.OPTIMIZATION_WALL_TIMEOUT + 60,   # hard kill (FR-6.9)
    soft_time_limit=settings.OPTIMIZATION_WALL_TIMEOUT,    # graceful (NFR-3.1)
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_optimization(self, task_id: str, job_id: str):
    """Run DSPy MIPROv2 optimization. MUST be sync def (NFR-3.4, Pitfall 7).

    Accepts task_id and job_id as strings (UUID serialized for Celery, Pitfall 6).
    Import pipeline inside function to avoid circular imports at module load.
    """
    from src.worker.pipeline import run_optimization_pipeline  # noqa: PLC0415

    return run_optimization_pipeline(task_id, job_id)
