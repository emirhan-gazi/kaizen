from celery import Celery

from src.config import settings
from src.worker.logging_config import setup_logging

setup_logging()

app = Celery("kaizen")

app.conf.update(
    include=["src.worker.tasks"],
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    broker_transport_options={"visibility_timeout": 7200},
    task_time_limit=5400,
    task_soft_time_limit=5100,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
