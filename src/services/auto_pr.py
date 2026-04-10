"""Provider-agnostic auto-PR service for optimization results.

Replaces the GitHub-specific github_pr.py. Uses the GitProvider interface
so PRs can be created on GitHub, Bitbucket Server, or any future provider.

Handles: retry with exponential backoff (D-12), duplicate prevention (D-21).
"""

from __future__ import annotations

import logging
import time

import yaml as _yaml

from src.services.git_provider import GitProvider, GitProviderError, PRResult
from src.services.prompt_file import detect_format, replace_prompt
from src.utils.pr_template import PRContext, build_pr_body, build_pr_title

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2
BACKOFF_MAX = 30


class AutoPRError(Exception):
    """Raised when PR creation fails after all retries."""


def create_optimization_pr(
    provider: GitProvider,
    ctx: PRContext,
    prompt_content: str,
    base_branch: str = "main",
    prompt_path: str | None = None,
    prompt_format: str = "text",
    prompt_file: str | None = None,
    prompt_locator: str | None = None,
) -> PRResult:
    """Create a PR with the optimized prompt via any git provider.

    Retries up to MAX_RETRIES times with exponential backoff.
    Checks for duplicate PRs before creating.
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _create_pr_attempt(
                provider=provider,
                ctx=ctx,
                prompt_content=prompt_content,
                base_branch=base_branch,
                prompt_path=prompt_path,
                prompt_format=prompt_format,
                prompt_file=prompt_file,
                prompt_locator=prompt_locator,
            )
        except AutoPRError:
            raise
        except GitProviderError as exc:
            last_error = f"Git provider error: {exc}"
            logger.warning(
                "PR creation attempt %d/%d failed: %s",
                attempt, MAX_RETRIES, last_error,
            )
            _backoff_sleep(attempt)
        except Exception as exc:
            last_error = f"Unexpected error: {exc}"
            logger.warning(
                "PR creation attempt %d/%d unexpected error: %s",
                attempt, MAX_RETRIES, last_error,
            )
            _backoff_sleep(attempt)

    return PRResult(success=False, error=last_error)


def _create_pr_attempt(
    provider: GitProvider,
    ctx: PRContext,
    prompt_content: str,
    base_branch: str,
    prompt_path: str | None,
    prompt_format: str,
    prompt_file: str | None = None,
    prompt_locator: str | None = None,
) -> PRResult:
    """Single attempt to create a PR via the provider."""
    branch_name = f"feature/tune-{ctx.task_name}-v{ctx.version_number}"

    # Check for existing PR
    existing_url = provider.find_open_pr(branch_name, base_branch)
    if existing_url:
        return PRResult(success=True, pr_url=existing_url, reused_existing=True)

    # Create feature branch
    provider.create_branch(branch_name, base_branch)

    # Commit prompt changes
    if prompt_file and prompt_locator:
        _commit_source_file_change(
            provider, branch_name, ctx, prompt_content,
            prompt_file, prompt_locator,
        )
    else:
        file_path = prompt_path or f"prompts/{ctx.task_name}.{prompt_format}"
        _commit_new_prompt_file(
            provider, branch_name, ctx, prompt_content, file_path,
        )

    # Commit .ct-tune.yaml metadata
    _commit_ct_tune_metadata(
        provider, branch_name, ctx, prompt_file, prompt_locator,
    )

    # Create PR
    title = build_pr_title(ctx)
    body = build_pr_body(ctx)
    result = provider.create_pr(title=title, body=body, head=branch_name, base=base_branch)

    if result.success:
        logger.info(
            "Created PR for task %s v%d: %s",
            ctx.task_name, ctx.version_number, result.pr_url,
        )

    return result


def _commit_source_file_change(
    provider: GitProvider,
    branch_name: str,
    ctx: PRContext,
    new_prompt: str,
    prompt_file: str,
    prompt_locator: str,
) -> None:
    """Read source file, replace prompt, commit modified file."""
    existing = provider.read_file(prompt_file, ref=branch_name)

    fmt = detect_format(prompt_file)
    modified_content = replace_prompt(existing.content, fmt, prompt_locator, new_prompt)

    commit_msg = (
        f"tune({ctx.task_name}): optimized prompt v{ctx.version_number}\n\n"
        f"Score: {ctx.after_score:.4f}\n"
        f"Modified: {prompt_file} [{prompt_locator}]"
    )
    provider.commit_file(
        path=prompt_file,
        content=modified_content,
        message=commit_msg,
        branch=branch_name,
        sha=existing.sha,
    )
    logger.info("Modified source file %s [%s]", prompt_file, prompt_locator)


def _commit_new_prompt_file(
    provider: GitProvider,
    branch_name: str,
    ctx: PRContext,
    prompt_content: str,
    file_path: str,
) -> None:
    """Create or update a dedicated prompt file."""
    commit_msg = (
        f"tune({ctx.task_name}): optimized prompt v{ctx.version_number}\n\n"
        f"Score: {ctx.after_score:.4f}"
    )
    try:
        existing = provider.read_file(file_path, ref=branch_name)
        provider.commit_file(
            path=file_path,
            content=prompt_content,
            message=commit_msg,
            branch=branch_name,
            sha=existing.sha,
        )
    except GitProviderError:
        provider.commit_file(
            path=file_path,
            content=prompt_content,
            message=commit_msg,
            branch=branch_name,
        )


def _commit_ct_tune_metadata(
    provider: GitProvider,
    branch_name: str,
    ctx: PRContext,
    prompt_file: str | None,
    prompt_locator: str | None,
) -> None:
    """Add/update .ct-tune.yaml metadata file in the PR."""
    metadata_path = ".ct-tune.yaml"
    existing_data: dict = {}
    existing_sha: str | None = None

    try:
        existing = provider.read_file(metadata_path, ref=branch_name)
        existing_data = _yaml.safe_load(existing.content) or {}
        existing_sha = existing.sha
    except GitProviderError:
        pass

    tasks_section = existing_data.setdefault("tasks", {})
    tasks_section[ctx.task_name] = {
        "version": ctx.version_number,
        "score": round(ctx.after_score, 4),
        "optimizer": ctx.optimizer,
        "prompt_file": prompt_file,
        "prompt_locator": prompt_locator,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    content = _yaml.dump(existing_data, default_flow_style=False, sort_keys=False)
    commit_msg = f"tune({ctx.task_name}): update .ct-tune.yaml metadata"

    provider.commit_file(
        path=metadata_path,
        content=content,
        message=commit_msg,
        branch=branch_name,
        sha=existing_sha,
    )


def _backoff_sleep(attempt: int) -> None:
    """Exponential backoff with cap."""
    delay = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
    logger.info("Backing off %.1fs before retry...", delay)
    time.sleep(delay)
