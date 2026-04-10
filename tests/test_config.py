import os

from src.config import Settings


def test_settings_loads_from_env():
    os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@testhost:5432/testdb"
    s = Settings()
    assert s.DATABASE_URL == "postgresql+psycopg://test:test@testhost:5432/testdb"


def test_settings_has_all_required_fields():
    s = Settings()
    assert hasattr(s, "DATABASE_URL")
    assert hasattr(s, "REDIS_URL")
    assert hasattr(s, "CELERY_BROKER_URL")
    assert hasattr(s, "CELERY_RESULT_BACKEND")
    assert hasattr(s, "API_HOST")
    assert hasattr(s, "API_PORT")
    assert hasattr(s, "OPENAI_API_KEY")
