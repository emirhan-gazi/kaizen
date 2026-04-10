"""GitHub PR creation service for auto-generated optimization PRs.

Handles: branch creation, file commit, PR opening, duplicate prevention (D-21),
rate limit handling (D-22), repository validation (D-23), and retry with
exponential backoff (D-12).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from github import (
    Auth,
    Github,
    GithubException,
    RateLimitExceededException,
)
from github.Repository import Repository

import yaml as _yaml

from src.config import settings
from src.services.prompt_file import detect_format, replace_prompt
from src.utils.crypto import decrypt_token
from src.utils.pr_template import PRContext, build_pr_body, build_pr_title

logger = logging.getLogger(__name__)

# Retry config (D-12): 3 attempts with exponential backoff
MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds
BACKOFF_MAX = 30  # seconds

# Rate limit threshold: back off when fewer than this many requests remain (D-22)
RATE_LIMIT_THRESHOLD = 50


@dataclass
class PRResult:
    """Result of a PR creation attempt."""

    success: bool
    pr_url: str | None = None
    error: str | None = None
    reused_existing: bool = False


class GitHubPRServiceError(Exception):
    """Raised when PR creation fails after all retries."""


def _get_github_token(task_token_encrypted: str | None) -> str:
    """Resolve the GitHub token: per-task encrypted override or global default (D-16)."""
    if task_token_encrypted:
        return decrypt_token(task_token_encrypted)
    if settings.GITHUB_TOKEN:
        return settings.GITHUB_TOKEN
    raise GitHubPRServiceError(
        "No GitHub token configured. Set GITHUB_TOKEN env var or "
        "configure a per-task encrypted token."
    )


def _get_github_client(token: str) -> Github:
    """Create an authenticated PyGithub client."""
    return Github(auth=Auth.Token(token))


def _resolve_repo_name(task_github_repo: str | None) -> str:
    """Resolve repo: per-task override or global default (D-01)."""
    repo = task_github_repo or settings.GITHUB_REPO
    if not repo:
        raise GitHubPRServiceError(
            "No GitHub repo configured. Set GITHUB_REPO env var or "
            "configure github_repo on the task."
        )
    return repo


def _resolve_base_branch(task_base_branch: str | None) -> str:
    """Resolve base branch: per-task override or global default (D-02)."""
    return task_base_branch or settings.GITHUB_BASE_BRANCH or "main"


def _check_rate_limit(client: Github) -> None:
    """Check GitHub API rate limit and sleep if near threshold (D-22)."""
    rate = client.get_rate_limit().core
    if rate.remaining < RATE_LIMIT_THRESHOLD:
        wait = max(0, (rate.reset - time.time())) + 1
        wait = min(wait, BACKOFF_MAX)
        logger.warning(
            "GitHub rate limit low (%d remaining). Sleeping %.1fs until reset.",
            rate.remaining,
            wait,
        )
        time.sleep(wait)


def validate_repository(
    task_token_encrypted: str | None = None,
    task_github_repo: str | None = None,
    task_base_branch: str | None = None,
) -> dict:
    """Validate GitHub repository access and permissions (D-23, FR-9.6).

    Returns dict with validation results and actionable error messages.
    """
    result = {
        "valid": False,
        "repo": None,
        "base_branch": None,
        "errors": [],
    }

    try:
        token = _get_github_token(task_token_encrypted)
    except GitHubPRServiceError as exc:
        result["errors"].append(str(exc))
        return result

    repo_name = None
    try:
        repo_name = _resolve_repo_name(task_github_repo)
        result["repo"] = repo_name
    except GitHubPRServiceError as exc:
        result["errors"].append(str(exc))
        return result

    base_branch = _resolve_base_branch(task_base_branch)
    result["base_branch"] = base_branch

    try:
        client = _get_github_client(token)
        repo = client.get_repo(repo_name)

        # Check write access
        if not repo.permissions.push:
            result["errors"].append(
                f"Token lacks write access to {repo_name}. "
                "Ensure the token has 'Contents: write' permission."
            )
            return result

        # Check base branch exists
        try:
            repo.get_branch(base_branch)
        except GithubException:
            result["errors"].append(
                f"Base branch '{base_branch}' not found in {repo_name}. "
                "Check GITHUB_BASE_BRANCH or task config."
            )
            return result

        result["valid"] = True
        client.close()

    except GithubException as exc:
        status = getattr(exc, "status", None)
        if status == 401:
            result["errors"].append(
                "GitHub token is invalid or expired. "
                "Generate a new fine-grained PAT with repo access."
            )
        elif status == 404:
            result["errors"].append(
                f"Repository '{repo_name}' not found. "
                "Check the repo name and token scopes."
            )
        else:
            result["errors"].append(f"GitHub API error: {exc}")

    return result


def _find_existing_pr(
    repo: Repository,
    branch_name: str,
    base_branch: str,
) -> str | None:
    """Check for existing open PR from the same branch (D-21, FR-9.7).

    Returns existing PR URL if found, None otherwise.
    """
    try:
        pulls = repo.get_pulls(state="open", head=f"{repo.owner.login}:{branch_name}", base=base_branch)
        for pr in pulls:
            logger.info(
                "Found existing open PR #%d for branch %s",
                pr.number,
                branch_name,
            )
            return pr.html_url
    except GithubException as exc:
        logger.warning("Failed to check existing PRs: %s", exc)
    return None


def create_optimization_pr(
    ctx: PRContext,
    prompt_content: str,
    task_token_encrypted: str | None = None,
    task_github_repo: str | None = None,
    task_base_branch: str | None = None,
    prompt_path: str | None = None,
    prompt_format: str = "text",
    prompt_file: str | None = None,
    prompt_locator: str | None = None,
) -> PRResult:
    """Create a GitHub PR with the optimized prompt (FR-9.2, FR-9.3, FR-9.4).

    Retries up to MAX_RETRIES times with exponential backoff (D-12).
    Checks for duplicate PRs before creating (D-21).
    Handles rate limits (D-22).
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _create_pr_attempt(
                ctx=ctx,
                prompt_content=prompt_content,
                task_token_encrypted=task_token_encrypted,
                task_github_repo=task_github_repo,
                task_base_branch=task_base_branch,
                prompt_path=prompt_path,
                prompt_format=prompt_format,
                prompt_file=prompt_file,
                prompt_locator=prompt_locator,
            )
        except RateLimitExceededException as exc:
            last_error = f"Rate limit exceeded: {exc}"
            logger.warning(
                "PR creation attempt %d/%d: rate limited. Retrying...",
                attempt, MAX_RETRIES,
            )
            _backoff_sleep(attempt)
        except GithubException as exc:
            last_error = f"GitHub API error (status {getattr(exc, 'status', '?')}): {exc}"
            logger.warning(
                "PR creation attempt %d/%d failed: %s",
                attempt, MAX_RETRIES, last_error,
            )
            # Don't retry on auth or not-found errors
            status = getattr(exc, "status", None)
            if status in (401, 403, 404):
                break
            _backoff_sleep(attempt)
        except GitHubPRServiceError:
            raise
        except Exception as exc:
            last_error = f"Unexpected error: {exc}"
            logger.warning(
                "PR creation attempt %d/%d unexpected error: %s",
                attempt, MAX_RETRIES, last_error,
            )
            _backoff_sleep(attempt)

    return PRResult(success=False, error=last_error)


def _create_pr_attempt(
    ctx: PRContext,
    prompt_content: str,
    task_token_encrypted: str | None,
    task_github_repo: str | None,
    task_base_branch: str | None,
    prompt_path: str | None,
    prompt_format: str,
    prompt_file: str | None = None,
    prompt_locator: str | None = None,
) -> PRResult:
    """Single attempt to create a PR. Raises on failure."""
    token = _get_github_token(task_token_encrypted)
    client = _get_github_client(token)
    repo_name = _resolve_repo_name(task_github_repo)
    base_branch = _resolve_base_branch(task_base_branch)

    try:
        _check_rate_limit(client)

        repo = client.get_repo(repo_name)

        # Branch name: feature/tune-{task_name}-v{version} (D-20)
        branch_name = f"feature/tune-{ctx.task_name}-v{ctx.version_number}"

        # Check for existing PR (D-21, FR-9.7)
        existing_url = _find_existing_pr(repo, branch_name, base_branch)
        if existing_url:
            return PRResult(
                success=True,
                pr_url=existing_url,
                reused_existing=True,
            )

        # Get base branch ref
        base_ref = repo.get_git_ref(f"heads/{base_branch}")
        base_sha = base_ref.object.sha

        # Create feature branch (FR-9.2)
        try:
            repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)
        except GithubException as exc:
            if getattr(exc, "status", None) == 422:
                # Branch already exists -- update it
                logger.info("Branch %s already exists, updating.", branch_name)
            else:
                raise

        # Determine file commit strategy (D-14 to D-17)
        if prompt_file and prompt_locator:
            # Phase 10: Modify actual source file using prompt_file service
            _commit_source_file_change(
                repo, branch_name, ctx, prompt_content,
                prompt_file, prompt_locator,
            )
        else:
            # Fallback: create/update a dedicated prompt file (D-16)
            file_path = prompt_path or f"prompts/{ctx.task_name}.{prompt_format}"
            _commit_new_prompt_file(
                repo, branch_name, ctx, prompt_content, file_path,
            )

        # Commit .ct-tune.yaml metadata (D-18, D-19, D-20)
        _commit_ct_tune_metadata(
            repo, branch_name, ctx, prompt_file, prompt_locator,
        )

        # Build PR title and body
        title = build_pr_title(ctx)
        body = build_pr_body(ctx)

        # Open PR (FR-9.4)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base=base_branch,
        )

        logger.info(
            "Created PR #%d for task %s v%d: %s",
            pr.number, ctx.task_name, ctx.version_number, pr.html_url,
        )

        return PRResult(success=True, pr_url=pr.html_url)

    finally:
        client.close()


def _commit_source_file_change(
    repo: Repository,
    branch_name: str,
    ctx: PRContext,
    new_prompt: str,
    prompt_file: str,
    prompt_locator: str,
) -> None:
    """Read source file from GitHub, replace prompt, commit modified file (D-14, D-15)."""
    existing = repo.get_contents(prompt_file, ref=branch_name)
    original_content = existing.decoded_content.decode("utf-8")

    fmt = detect_format(prompt_file)
    modified_content = replace_prompt(original_content, fmt, prompt_locator, new_prompt)

    commit_msg = (
        f"tune({ctx.task_name}): optimized prompt v{ctx.version_number}\n\n"
        f"Score: {ctx.after_score:.4f}\n"
        f"Modified: {prompt_file} [{prompt_locator}]"
    )
    repo.update_file(
        path=prompt_file,
        message=commit_msg,
        content=modified_content,
        sha=existing.sha,
        branch=branch_name,
    )
    logger.info("Modified source file %s [%s]", prompt_file, prompt_locator)


def _commit_new_prompt_file(
    repo: Repository,
    branch_name: str,
    ctx: PRContext,
    prompt_content: str,
    file_path: str,
) -> None:
    """Create or update a dedicated prompt file (fallback behavior)."""
    commit_msg = (
        f"tune({ctx.task_name}): optimized prompt v{ctx.version_number}\n\n"
        f"Score: {ctx.after_score:.4f}"
    )
    try:
        existing = repo.get_contents(file_path, ref=branch_name)
        repo.update_file(
            path=file_path,
            message=commit_msg,
            content=prompt_content,
            sha=existing.sha,
            branch=branch_name,
        )
    except GithubException:
        repo.create_file(
            path=file_path,
            message=commit_msg,
            content=prompt_content,
            branch=branch_name,
        )


def _commit_ct_tune_metadata(
    repo: Repository,
    branch_name: str,
    ctx: PRContext,
    prompt_file: str | None,
    prompt_locator: str | None,
) -> None:
    """Add/update .ct-tune.yaml metadata file in the PR (D-18, D-19, D-20)."""
    metadata_path = ".ct-tune.yaml"
    existing_data: dict = {}

    try:
        existing = repo.get_contents(metadata_path, ref=branch_name)
        existing_data = _yaml.safe_load(existing.decoded_content.decode("utf-8")) or {}
        existing_sha = existing.sha
    except GithubException:
        existing_sha = None

    # Update task entry in metadata
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

    if existing_sha:
        repo.update_file(
            path=metadata_path,
            message=commit_msg,
            content=content,
            sha=existing_sha,
            branch=branch_name,
        )
    else:
        repo.create_file(
            path=metadata_path,
            message=commit_msg,
            content=content,
            branch=branch_name,
        )


def _backoff_sleep(attempt: int) -> None:
    """Exponential backoff with cap (D-12)."""
    delay = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
    logger.info("Backing off %.1fs before retry...", delay)
    time.sleep(delay)
