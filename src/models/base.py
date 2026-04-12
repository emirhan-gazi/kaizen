import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String, unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    schema_json: Mapped[dict | None] = mapped_column(JSONB)
    feedback_threshold: Mapped[int] = mapped_column(
        Integer, default=50
    )
    feedback_retention_limit: Mapped[int] = mapped_column(
        Integer, default=1000, server_default=text("1000")
    )
    evaluator_config: Mapped[dict | None] = mapped_column(JSONB)
    teacher_model: Mapped[str | None] = mapped_column(String, nullable=True)
    judge_model: Mapped[str | None] = mapped_column(String, nullable=True)
    module_type: Mapped[str] = mapped_column(String, default="predict")
    optimizer_type: Mapped[str] = mapped_column(
        String, default="gepa", server_default=text("'gepa'")
    )
    gepa_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cost_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Git provider config (per-task overrides)
    git_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    git_base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    git_token_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    git_project: Mapped[str | None] = mapped_column(String, nullable=True)
    git_repo: Mapped[str | None] = mapped_column(String, nullable=True)
    git_base_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_path: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_format: Mapped[str | None] = mapped_column(String, nullable=True)
    # Legacy aliases kept as DB columns for migration continuity
    github_repo: Mapped[str | None] = mapped_column(String, nullable=True)
    github_base_branch: Mapped[str | None] = mapped_column(String, nullable=True)
    github_token_encrypted: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_file: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_locator: Mapped[str | None] = mapped_column(String, nullable=True)
    mode: Mapped[str] = mapped_column(
        String, default="optimize_only", server_default=text("'optimize_only'")
    )
    feedback_source: Mapped[str] = mapped_column(
        String, default="sdk", server_default=text("'sdk'")
    )
    auto_eval: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class FeedbackEntry(Base):
    __tablename__ = "feedback_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=False,
    )
    inputs: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )

    __table_args__ = (
        Index(
            "ix_feedback_entries_task_created",
            "task_id",
            "created_at",
        ),
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    prompt_text: Mapped[str | None] = mapped_column(Text)
    original_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    dspy_state_json: Mapped[dict | None] = mapped_column(JSONB)
    eval_score: Mapped[float | None] = mapped_column(Float)
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String, default="draft")
    optimizer: Mapped[str | None] = mapped_column(String)
    dspy_version: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class OptimizationJob(Base):
    __tablename__ = "optimization_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=False,
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("prompt_versions.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String, default="PENDING"
    )
    triggered_by: Mapped[str | None] = mapped_column(String)
    feedback_count: Mapped[int | None] = mapped_column(Integer)
    pr_url: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    job_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    progress_step: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id"),
        nullable=False,
    )
    prompt_text: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String)
    tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    source_file: Mapped[str | None] = mapped_column(String)
    source_variable: Mapped[str | None] = mapped_column(String)
    score: Mapped[float | None] = mapped_column(Float)
    scored_by: Mapped[str | None] = mapped_column(String)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_traces_task_created", "task_id", "created_at"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key_hash: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False
    )
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
