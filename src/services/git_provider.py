"""Abstract git provider interface for multi-provider support.

Defines the GitProvider ABC that all concrete providers implement,
plus a factory function to instantiate the right provider from config.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class GitProviderError(Exception):
    """Raised when a git provider operation fails."""


@dataclass
class FileContent:
    """Content of a file read from a git provider."""

    content: str
    sha: str  # Provider-specific ref used for update operations


@dataclass
class PRResult:
    """Result of a PR creation or lookup."""

    success: bool
    pr_url: str | None = None
    error: str | None = None
    reused_existing: bool = False


class GitProvider(ABC):
    """Abstract interface for git hosting providers.

    Implementations: GitHubProvider, BitbucketServerProvider, GitLabProvider (stub).
    """

    @abstractmethod
    def validate_access(self) -> dict:
        """Validate repository access and permissions.

        Returns dict with keys: valid (bool), repo (str|None),
        base_branch (str|None), errors (list[str]).
        """

    @abstractmethod
    def read_file(self, path: str, ref: str) -> FileContent:
        """Read a file from the repository at a given ref/branch.

        Raises GitProviderError if file not found or access denied.
        """

    @abstractmethod
    def create_branch(self, branch_name: str, from_ref: str) -> None:
        """Create a new branch from the given ref.

        Should be idempotent — if branch already exists, do nothing.
        Raises GitProviderError on failure.
        """

    @abstractmethod
    def commit_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> None:
        """Create or update a file on a branch.

        If sha is provided, it's an update (must match current sha).
        If sha is None, it's a create.
        Raises GitProviderError on failure.
        """

    @abstractmethod
    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PRResult:
        """Create a pull request from head branch to base branch.

        Returns PRResult with the PR URL on success.
        """

    @abstractmethod
    def find_open_pr(self, head: str, base: str) -> str | None:
        """Find an existing open PR from head to base.

        Returns the PR URL if found, None otherwise.
        """


def get_git_provider(
    provider_type: str,
    *,
    base_url: str = "",
    token: str = "",
    project: str = "",
    repo: str = "",
    base_branch: str = "main",
    ssl_verify: bool = True,
) -> GitProvider:
    """Factory: return the right GitProvider implementation.

    Args:
        provider_type: "github", "bitbucket_server", or "gitlab"
        base_url: Base URL for self-hosted providers
        token: Authentication token
        project: Project/org key (Bitbucket Server)
        repo: Repository name (owner/repo for GitHub, slug for Bitbucket)
        base_branch: Default target branch
        ssl_verify: Whether to verify SSL certificates
    """
    if provider_type == "github":
        from src.services.github_provider import GitHubProvider

        return GitHubProvider(
            token=token,
            repo=repo,
            base_branch=base_branch,
            base_url=base_url or None,
        )
    elif provider_type == "bitbucket_server":
        from src.services.bitbucket_provider import BitbucketServerProvider

        return BitbucketServerProvider(
            base_url=base_url,
            token=token,
            project=project,
            repo=repo,
            base_branch=base_branch,
            ssl_verify=ssl_verify,
        )
    elif provider_type == "gitlab":
        from src.services.gitlab_provider import GitLabProvider

        return GitLabProvider()
    else:
        raise GitProviderError(
            f"Unknown git provider: {provider_type!r}. "
            "Supported: github, bitbucket_server, gitlab"
        )
