from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/continuous_tune"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = (
        "db+postgresql+psycopg://postgres:postgres@localhost:5432/continuous_tune"
    )

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Prompt cache
    PROMPT_CACHE_TTL: int = 300  # seconds, 5 min default

    # Database limits
    FEEDBACK_RETENTION_LIMIT: int = 1000

    # Webhooks
    GITHUB_WEBHOOK_SECRET: str = ""

    # LLM
    OPENAI_API_KEY: str = "sk-placeholder"
    OPENAI_API_BASE: str = ""
    SSL_VERIFY: bool = True

    # Seed upload
    SEED_SIZE_LIMIT: int = 1000

    # Optimization pipeline
    TEACHER_MODEL: str = "gpt-4o"
    JUDGE_MODEL: str = "gpt-4o-mini"
    COST_BUDGET_DEFAULT: float = 5.0
    MAX_TRIALS_DEFAULT: int = 15
    LLM_TIMEOUT: int = 120  # seconds, HTTP timeout on LiteLLM calls
    OPTIMIZATION_WALL_TIMEOUT: int = 1800  # seconds, 30 min wall-clock kill
    DEFAULT_OPTIMIZER: str = "gepa"  # gepa | miprov2
    GEPA_AUTO: str = "medium"  # light | medium | heavy

    # Git Provider Config (provider-agnostic)
    GIT_PROVIDER: str = "github"  # github | bitbucket_server | gitlab
    GIT_BASE_URL: str = ""  # e.g. https://bitbucket.company.com
    GIT_TOKEN: str = ""
    GIT_PROJECT: str = ""  # Bitbucket Server project key
    GIT_REPO: str = ""
    GIT_BASE_BRANCH: str = "main"
    GIT_TOKEN_ENCRYPTION_KEY: str = ""

    # Legacy GitHub aliases (backwards compat — take precedence if GIT_* not set)
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = ""
    GITHUB_BASE_BRANCH: str = "main"
    GITHUB_TOKEN_ENCRYPTION_KEY: str = ""


settings = Settings()
