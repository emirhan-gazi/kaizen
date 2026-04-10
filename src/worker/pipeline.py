"""DSPy MIPROv2 optimization pipeline orchestration.

Runs inside Celery worker (sync only). Creates its own sync SQLAlchemy
engine -- cannot use async engine from database.py (Pitfall 7).

7-state lifecycle: PENDING -> RUNNING -> EVALUATING -> COMPILING -> SUCCESS / FAILURE / PR_FAILED
Each transition writes to PostgreSQL via session.commit() (D-21).
"""

import json
import logging
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dspy
import litellm
from sqlalchemy import create_engine, func

# Disable SSL verification for corporate APIs with self-signed certs
from src.config import settings as _settings_early

if not _settings_early.SSL_VERIFY:
    import httpx

    litellm.ssl_verify = False
    litellm.client_session = httpx.Client(verify=False)  # noqa: S501
from sqlalchemy.orm import Session

from src.config import settings
from src.models.base import (
    FeedbackEntry,
    OptimizationJob,
    PromptVersion,
    Task,
    Trace,
)
from src.services.auto_pr import AutoPRError, create_optimization_pr
from src.services.git_provider import get_git_provider
from src.services.prompt_file import detect_format, extract_prompt
from src.utils.crypto import decrypt_token
from src.utils.pr_template import PRContext
from src.worker.evaluators import batch_evaluate_traces, create_evaluator

logger = logging.getLogger(__name__)


def _get_sync_engine():
    """Create a sync SQLAlchemy engine for the Celery worker.

    The main app uses async engine (database.py) which cannot be used
    in sync Celery tasks (Pitfall 7).
    """
    # DATABASE_URL uses psycopg driver which works for sync
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def _update_job_status(
    session: Session,
    job: OptimizationJob,
    status: str,
    progress_step: str,
    extra_metadata: dict | None = None,
) -> None:
    """Update job status and progress, committing to PostgreSQL at each transition (D-21)."""
    job.status = status
    job.progress_step = progress_step

    if status == "RUNNING" and job.started_at is None:
        job.started_at = datetime.now(timezone.utc)

    if status in ("SUCCESS", "FAILURE", "PR_FAILED"):
        job.completed_at = datetime.now(timezone.utc)

    if extra_metadata:
        current = job.job_metadata or {}
        current.update(extra_metadata)
        job.job_metadata = current

    session.commit()
    logger.info(
        "Job %s: %s -> %s (step: %s)",
        job.id, job.status, status, progress_step,
    )


def run_optimization_pipeline(task_id: str, job_id: str) -> dict:
    """Run DSPy MIPROv2 optimization end-to-end.

    Called from Celery task with string IDs (Pitfall 6: no ORM objects).
    All code is sync def (Pitfall 7: no async in Celery).

    Returns dict with job result metadata.
    """
    engine = _get_sync_engine()
    started = datetime.now(timezone.utc)
    _reset_cost_tracker()

    with Session(engine) as session:
        # Load job and task by their IDs
        job = session.get(OptimizationJob, job_id)
        if job is None:
            raise ValueError(f"OptimizationJob {job_id} not found")

        task = session.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        try:
            return _run_pipeline(session, job, task, started)
        except Exception as exc:
            # On ANY exception: mark FAILURE with full traceback (D-22)
            duration = (datetime.now(timezone.utc) - started).total_seconds()
            error_tb = traceback.format_exc()
            job.error_message = str(exc)
            _update_job_status(
                session, job, "FAILURE", "error",
                extra_metadata={
                    "error_traceback": error_tb,
                    "duration_seconds": duration,
                    "last_successful_step": job.progress_step,
                },
            )
            raise


def _run_pipeline(
    session: Session,
    job: OptimizationJob,
    task: Task,
    started: datetime,
) -> dict:
    """Core pipeline logic, separated for clean error handling."""

    # --- PENDING -> RUNNING ---
    _update_job_status(session, job, "RUNNING", "loading_data")

    # Load data from traces or feedback based on task config (D-14)
    schema_keys = list((task.schema_json or {}).keys())

    if task.feedback_source == "traces":
        examples = _load_from_traces(session, task, schema_keys)
    else:
        examples = _load_from_feedback(session, task, schema_keys)

    if not examples:
        raise ValueError(
            f"No data found for task {task.id}. "
            "Cannot run optimization without data."
        )

    # --- Build trainset (D-03, D-06, Pitfall 3) ---
    _update_job_status(session, job, "RUNNING", "building_trainset")

    # 20/80 train/val split (D-06, FR-6.3, Pitfall 3)
    # IMPORTANT: 20% train, 80% validation -- NOT 80/20
    train_size = max(1, len(examples) // 5)
    train = examples[:train_size]
    val = examples[train_size:]

    logger.info(
        "Dataset split: %d total, %d train (20%%), %d val (80%%)",
        len(examples), len(train), len(val),
    )

    # --- Configure DSPy (D-07, D-03, D-01, D-02) ---
    _update_job_status(session, job, "RUNNING", "configuring_dspy")

    teacher_model = task.teacher_model or settings.TEACHER_MODEL
    judge_model = task.judge_model or settings.JUDGE_MODEL

    # Configure DSPy LM via LiteLLM (D-07)
    # Model already has provider prefix (e.g., "openai/model-name") — don't add "litellm/"
    teacher_lm = dspy.LM(
        teacher_model,
        api_key=settings.OPENAI_API_KEY,
        api_base=settings.OPENAI_API_BASE or None,
        timeout=settings.LLM_TIMEOUT,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )

    # Auto-generate DSPy Signature from task.schema_json (D-03)
    sig_fields = {}
    for key in schema_keys:
        sig_fields[key] = dspy.InputField()
    sig_fields["response"] = dspy.OutputField()

    # Seed with existing prompt so MIPROv2 refines rather than rewrites
    existing_prompt = _load_existing_prompt(session, task)
    if existing_prompt:
        signature = dspy.Signature(sig_fields, instructions=existing_prompt)
        logger.info("Seeded signature with existing prompt (%d chars)", len(existing_prompt))
    else:
        signature = dspy.Signature(sig_fields)

    # Select module type (D-01, D-02)
    if task.module_type == "chain_of_thought":
        module = dspy.ChainOfThought(signature)
    else:
        module = dspy.Predict(signature)

    # --- RUNNING -> EVALUATING ---
    _update_job_status(session, job, "EVALUATING", "creating_evaluator")

    metric_fn = create_evaluator(task, settings)

    # --- EVALUATING -> COMPILING ---
    _update_job_status(session, job, "COMPILING", "running_miprov2")

    task_max_trials = settings.MAX_TRIALS_DEFAULT

    # Conservative optimization: small incremental prompt changes
    # - max_bootstrapped_demos=1: minimal few-shot examples
    # - max_labeled_demos=1: keep prompt close to original
    # - num_candidates=task_max_trials: explore within tight bounds
    with dspy.context(lm=teacher_lm):
        optimizer = dspy.MIPROv2(
            metric=metric_fn,
            auto=None,
            num_candidates=task_max_trials,
            max_bootstrapped_demos=1,
            max_labeled_demos=1,
        )
        compiled = optimizer.compile(
            module,
            trainset=train,
            num_trials=task_max_trials,
            valset=val,
            minibatch_size=min(len(val), 25),
        )

    # --- Save compiled state (Pattern 3 from ARCHITECTURE.md) ---
    _update_job_status(session, job, "COMPILING", "saving_compiled_state")

    # Save as JSON only -- never pickle (save_program=False)
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_path = str(Path(tmp_dir) / "compiled_state.json")
        compiled.save(state_path, save_program=False)

        with open(state_path) as f:
            dspy_state = json.load(f)

    # Extract prompt text from compiled program
    prompt_text = _extract_prompt_text(compiled)

    # --- Dual scoring: dataset score + judge score ---
    # Dataset score: how well the optimized prompt performs on validation set
    dataset_score = _get_best_score(optimizer, metric_fn, compiled, val)

    # Judge score: independent LLM evaluation of the optimized prompt quality
    _update_job_status(session, job, "COMPILING", "judge_evaluation")
    with dspy.context(lm=teacher_lm):
        judge_score = _run_judge_evaluation(compiled, val, task, settings, schema_keys)

    # Get next version number
    max_version = session.query(
        func.max(PromptVersion.version_number)
    ).filter_by(task_id=task.id).scalar()
    next_version = (max_version or 0) + 1

    # Insert PromptVersion row
    prompt_version = PromptVersion(
        task_id=task.id,
        version_number=next_version,
        prompt_text=prompt_text,
        dspy_state_json=dspy_state,
        eval_score=dataset_score,
        judge_score=judge_score,
        status="draft",
        optimizer="MIPROv2",
        dspy_version=dspy.__version__,
    )
    session.add(prompt_version)
    session.flush()  # Get the id

    # --- COMPILING -> SUCCESS ---
    completed = datetime.now(timezone.utc)
    duration = (completed - started).total_seconds()

    # Build job metadata (D-12, D-22)
    job_meta = {
        "cost_usd": _tracker.total_cost or None,
        "total_tokens": _tracker.total_tokens or None,
        "total_llm_calls": _tracker.total_calls or None,
        "teacher_model": teacher_model,
        "judge_model": judge_model,
        "litellm_version": getattr(litellm, "__version__", "1.80.12"),
        "dspy_version": dspy.__version__,
        "trials_completed": task_max_trials,
        "dataset_score": dataset_score,
        "train_size": len(train),
        "val_size": len(val),
        "duration_seconds": duration,
    }

    job.prompt_version_id = prompt_version.id
    job.feedback_count = len(examples)

    _update_job_status(session, job, "SUCCESS", "completed", extra_metadata=job_meta)

    logger.info(
        "Optimization complete: job=%s, version=%d, score=%.4f, duration=%.1fs",
        job.id, next_version, dataset_score, duration,
    )

    # --- Mode check: skip PR if optimize_only ---
    if task.mode == "optimize_only":
        logger.info("Task %s mode=optimize_only — skipping PR creation", task.id)
        return {
            "job_id": str(job.id),
            "status": "SUCCESS",
            "pr_skipped": True,
            "reason": "mode=optimize_only",
        }

    # --- Quality gate: skip PR if scores are too low ---
    min_score = 0.3
    if dataset_score < min_score and judge_score < min_score:
        logger.warning(
            "Skipping PR for job %s — scores too low (dataset=%.2f, judge=%.2f, min=%.2f)",
            job.id, dataset_score, judge_score, min_score,
        )
        return {
            "job_id": str(job.id),
            "status": "SUCCESS",
            "pr_skipped": True,
            "reason": f"Scores below threshold (dataset={dataset_score:.2f}, judge={judge_score:.2f})",
        }

    # --- Attempt PR creation (D-11, D-14) ---
    # Optimization result is preserved regardless of PR outcome.
    _attempt_pr_creation(
        session=session,
        job=job,
        task=task,
        prompt_version=prompt_version,
        prompt_text=prompt_text,
        dataset_score=dataset_score,
        job_meta=job_meta,
        train_size=len(train),
        val_size=len(val),
        feedback_count=len(examples),
    )

    return {
        "job_id": str(job.id),
        "prompt_version_id": str(prompt_version.id),
        "version_number": next_version,
        "dataset_score": dataset_score,
        "duration_seconds": duration,
        "train_size": len(train),
        "val_size": len(val),
        "pr_url": job.pr_url,
    }


def _load_from_feedback(
    session: Session, task: Task, schema_keys: list[str]
) -> list:
    """Load DSPy examples from feedback_entries table (original behavior)."""
    feedback_entries = (
        session.query(FeedbackEntry)
        .filter_by(task_id=task.id)
        .order_by(FeedbackEntry.created_at.desc())
        .all()
    )

    examples = []
    for entry in feedback_entries:
        example_data = {}
        inputs = entry.inputs or {}
        for key in schema_keys:
            example_data[key] = inputs.get(key, "")
        example_data["response"] = entry.output or ""
        ex = dspy.Example(**example_data).with_inputs(*schema_keys)
        examples.append(ex)
    return examples


def _load_from_traces(
    session: Session, task: Task, schema_keys: list[str]
) -> list:
    """Load DSPy examples from traces table (D-14).

    Auto-evaluates unscored traces if task.auto_eval is enabled (D-06, D-07, D-11).
    """
    traces = (
        session.query(Trace)
        .filter_by(task_id=task.id)
        .order_by(Trace.created_at.desc())
        .all()
    )

    if not traces:
        return []

    # Auto-evaluate unscored traces if enabled (D-06, D-07, D-11)
    if task.auto_eval:
        unscored = [t for t in traces if t.score is None]
        if unscored:
            logger.info(
                "Auto-evaluating %d unscored traces for task %s",
                len(unscored), task.id,
            )
            eval_results = batch_evaluate_traces(unscored, task, settings)
            for trace, score in eval_results:
                trace.score = score
                trace.scored_by = "auto_judge"
            session.commit()

    # Build DSPy examples from traces (D-13)
    examples = []
    for trace in traces:
        example_data = {}
        # Use prompt_text as the input (traces don't have structured inputs)
        if schema_keys:
            example_data[schema_keys[0]] = trace.prompt_text or ""
            for key in schema_keys[1:]:
                example_data[key] = ""
        else:
            example_data["input"] = trace.prompt_text or ""
        example_data["response"] = trace.response_text or ""

        input_keys = schema_keys if schema_keys else ["input"]
        ex = dspy.Example(**example_data).with_inputs(*input_keys)
        examples.append(ex)

    return examples


def _attempt_pr_creation(
    session: Session,
    job: OptimizationJob,
    task: Task,
    prompt_version: PromptVersion,
    prompt_text: str,
    dataset_score: float,
    job_meta: dict,
    train_size: int,
    val_size: int,
    feedback_count: int,
) -> None:
    """Attempt PR creation via git provider after successful optimization.

    If PR creation fails, marks job as PR_FAILED but preserves the
    optimization result (draft prompt_version).
    """
    # Resolve git provider config: per-task overrides > global settings
    provider_type = task.git_provider or settings.GIT_PROVIDER
    git_repo = task.git_repo or task.github_repo or settings.GIT_REPO or settings.GITHUB_REPO
    git_base_branch = (
        task.git_base_branch or task.github_base_branch
        or settings.GIT_BASE_BRANCH or settings.GITHUB_BASE_BRANCH or "main"
    )
    git_token_encrypted = task.git_token_encrypted or task.github_token_encrypted

    # Skip PR creation if no repo configured
    if not task.prompt_path and not git_repo:
        logger.info("No git config for task %s, skipping PR creation.", task.id)
        return

    # Resolve token
    token = ""
    if git_token_encrypted:
        token = decrypt_token(git_token_encrypted)
    elif settings.GIT_TOKEN:
        token = settings.GIT_TOKEN
    elif settings.GITHUB_TOKEN:
        token = settings.GITHUB_TOKEN

    # Build provider instance
    try:
        provider = get_git_provider(
            provider_type,
            base_url=task.git_base_url or settings.GIT_BASE_URL,
            token=token,
            project=task.git_project or settings.GIT_PROJECT,
            repo=git_repo,
            base_branch=git_base_branch,
            ssl_verify=settings.SSL_VERIFY,
        )
    except Exception as exc:
        _update_job_status(
            session, job, "PR_FAILED", "pr_creation_failed",
            extra_metadata={"pr_error": f"Provider init failed: {exc}"},
        )
        return

    # Get previous active prompt for before/after comparison
    prev_prompt = (
        session.query(PromptVersion)
        .filter_by(task_id=task.id, status="active")
        .first()
    )

    # Extract few-shot examples from DSPy state
    few_shots = _extract_few_shot_examples(prompt_version.dspy_state_json)

    ctx = PRContext(
        task_name=task.name,
        version_number=prompt_version.version_number,
        before_score=prev_prompt.eval_score if prev_prompt else None,
        after_score=dataset_score,
        feedback_count=feedback_count,
        optimizer=prompt_version.optimizer or "MIPROv2",
        teacher_model=job_meta.get("teacher_model", settings.TEACHER_MODEL),
        judge_model=job_meta.get("judge_model", settings.JUDGE_MODEL),
        trials_completed=job_meta.get("trials_completed", 0),
        duration_seconds=job_meta.get("duration_seconds", 0),
        train_size=train_size,
        val_size=val_size,
        old_prompt_text=prev_prompt.prompt_text if prev_prompt else None,
        new_prompt_text=prompt_text,
        few_shot_examples=few_shots,
        job_id=str(job.id),
        dspy_version=job_meta.get("dspy_version"),
        litellm_version=job_meta.get("litellm_version"),
        cost_usd=job_meta.get("cost_usd"),
        judge_score=prompt_version.judge_score,
    )

    try:
        result = create_optimization_pr(
            provider=provider,
            ctx=ctx,
            prompt_content=prompt_text,
            base_branch=git_base_branch,
            prompt_path=task.prompt_path,
            prompt_format=task.prompt_format or "text",
            prompt_file=task.prompt_file,
            prompt_locator=task.prompt_locator,
        )

        if result.success:
            job.pr_url = result.pr_url
            session.commit()
            logger.info(
                "PR created for job %s: %s (reused=%s)",
                job.id, result.pr_url, result.reused_existing,
            )
        else:
            _update_job_status(
                session, job, "PR_FAILED", "pr_creation_failed",
                extra_metadata={"pr_error": result.error},
            )
            logger.warning(
                "PR creation failed for job %s: %s",
                job.id, result.error,
            )
    except AutoPRError as exc:
        _update_job_status(
            session, job, "PR_FAILED", "pr_creation_failed",
            extra_metadata={"pr_error": str(exc)},
        )
        logger.warning(
            "PR creation error for job %s: %s", job.id, exc,
        )


def _extract_few_shot_examples(dspy_state: dict | None) -> list[dict] | None:
    """Extract few-shot demo examples from DSPy compiled state JSON."""
    if not dspy_state:
        return None
    try:
        demos = []
        # DSPy state stores demos per predictor
        for _key, predictor_state in dspy_state.items():
            if isinstance(predictor_state, dict) and "demos" in predictor_state:
                for demo in predictor_state["demos"]:
                    if isinstance(demo, dict):
                        demos.append(demo)
        return demos if demos else None
    except Exception as exc:
        logger.warning("Failed to extract few-shot examples: %s", exc)
        return None


def _extract_prompt_text(compiled: Any) -> str:
    """Extract prompt/instruction text from a compiled DSPy program."""
    try:
        # DSPy compiled programs store instructions in predictors
        parts = []
        for name, predictor in compiled.named_predictors():
            if hasattr(predictor, "signature"):
                sig = predictor.signature
                if hasattr(sig, "instructions"):
                    parts.append(f"[{name}] {sig.instructions}")
            # Also capture demos if present
            if hasattr(predictor, "demos") and predictor.demos:
                parts.append(f"  ({len(predictor.demos)} demos)")
        return "\n".join(parts) if parts else "No instructions extracted"
    except Exception as exc:
        logger.warning("Failed to extract prompt text: %s", exc)
        return "Extraction failed"


def _load_existing_prompt(session: Session, task: Any) -> str | None:
    """Load the existing prompt to seed MIPROv2.

    Priority: 1) latest active PromptVersion, 2) source file via git, 3) None.
    """
    # Try latest active prompt version
    active = (
        session.query(PromptVersion)
        .filter_by(task_id=task.id, status="active")
        .order_by(PromptVersion.version_number.desc())
        .first()
    )
    if active and active.prompt_text:
        return active.prompt_text

    # Try latest draft
    latest = (
        session.query(PromptVersion)
        .filter_by(task_id=task.id)
        .order_by(PromptVersion.version_number.desc())
        .first()
    )
    if latest and latest.prompt_text:
        return latest.prompt_text

    # Try reading from source file via git provider
    if task.prompt_file and task.prompt_locator:
        try:
            provider_type = task.git_provider or settings.GIT_PROVIDER
            git_repo = task.git_repo or settings.GIT_REPO
            git_base_branch = task.git_base_branch or settings.GIT_BASE_BRANCH or "main"
            git_token_encrypted = task.git_token_encrypted

            if git_repo and git_token_encrypted:
                token = decrypt_token(git_token_encrypted)
                provider = get_git_provider(
                    provider_type,
                    token=token,
                    base_url=task.git_base_url or settings.GIT_BASE_URL or "",
                    project=task.git_project or settings.GIT_PROJECT or "",
                    repo=git_repo,
                )
                fc = provider.read_file(task.prompt_file, ref=git_base_branch)
                fmt = detect_format(task.prompt_file)
                return extract_prompt(fc.content, fmt, task.prompt_locator)
        except Exception as exc:
            logger.warning("Could not load existing prompt from git: %s", exc)

    return None


def _run_judge_evaluation(
    compiled: Any,
    val: list,
    task: Any,
    settings: Any,
    schema_keys: list[str],
) -> float:
    """Run independent LLM-as-judge evaluation on the compiled prompt.

    Generates predictions with the optimized prompt, then has the judge
    model score each prediction independently (not comparing to expected).
    Returns average judge score across validation set.
    """
    judge_model = task.judge_model or settings.JUDGE_MODEL

    scores: list[float] = []
    for ex in val[:10]:  # Cap at 10 for cost
        try:
            inputs = {k: getattr(ex, k) for k in schema_keys}
            pred = compiled(**inputs)
            predicted = getattr(pred, "response", str(pred))

            prompt = (
                f"You are an expert evaluator.\n\n"
                f"Task: {task.description or task.name}\n\n"
                f"Input: {_format_judge_inputs(inputs)}\n\n"
                f"Response:\n{predicted}\n\n"
                f"Score the response quality on a scale of 0.0 to 1.0.\n"
                f"Consider: accuracy, relevance, completeness, and clarity.\n"
                f"Do NOT favor longer responses.\n\n"
                f"Respond with ONLY a single decimal number between 0.0 and 1.0."
            )

            response = litellm.completion(
                model=judge_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=settings.LLM_TIMEOUT,
                temperature=0.0,
                api_base=settings.OPENAI_API_BASE or None,
                api_key=settings.OPENAI_API_KEY,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            score_text = response.choices[0].message.content.strip()
            score = _parse_judge_score(score_text)
            scores.append(score)
        except Exception as exc:
            logger.warning("Judge eval failed for example: %s", exc)

    if not scores:
        return 0.0
    avg = sum(scores) / len(scores)
    logger.info("Judge evaluation: %d examples, avg=%.3f", len(scores), avg)
    return round(avg, 4)


def _format_judge_inputs(inputs: dict) -> str:
    return "\n".join(f"{k}: {v}" for k, v in inputs.items())


def _parse_judge_score(text: str) -> float:
    text = text.strip()
    for token in text.split():
        try:
            score = float(token)
            if 0.0 <= score <= 1.0:
                return score
        except ValueError:
            continue
    try:
        return max(0.0, min(1.0, float(text)))
    except (ValueError, TypeError):
        return 0.0


def _get_best_score(
    optimizer: Any,
    metric_fn: Any,
    compiled: Any,
    val: list,
) -> float:
    """Get the best evaluation score from the optimization run."""
    try:
        if hasattr(optimizer, "best_score"):
            return float(optimizer.best_score)
        # Fallback: evaluate a sample
        if val:
            scores = []
            for ex in val[:5]:  # Sample 5 for speed
                try:
                    pred = compiled(**{k: getattr(ex, k) for k in ex.keys() if k != "response"})
                    score = metric_fn(ex, pred)
                    scores.append(score)
                except Exception:
                    pass
            if scores:
                return sum(scores) / len(scores)
    except Exception as exc:
        logger.warning("Could not compute best score: %s", exc)
    return 0.0


class _CostTracker:
    """Track LLM cost and usage via litellm success callbacks."""

    def __init__(self):
        self.total_cost: float = 0.0
        self.total_tokens: int = 0
        self.total_calls: int = 0

    def success_callback(self, kwargs, completion_response, start_time, end_time):
        """Called by litellm after each successful completion."""
        self.total_calls += 1
        usage = getattr(completion_response, "usage", None)
        if usage:
            self.total_tokens += getattr(usage, "total_tokens", 0)
        # litellm attaches _hidden_params with cost info
        hidden = getattr(completion_response, "_hidden_params", {}) or {}
        self.total_cost += hidden.get("response_cost", 0.0)


# Module-level tracker instance, reset per pipeline run
_tracker = _CostTracker()


def _reset_cost_tracker() -> _CostTracker:
    """Reset and register the cost tracker for a new pipeline run."""
    global _tracker
    _tracker = _CostTracker()
    # Register as litellm success callback
    if _tracker.success_callback not in litellm.success_callback:
        litellm.success_callback.append(_tracker.success_callback)
    return _tracker
