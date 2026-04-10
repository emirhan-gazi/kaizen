"""GitLab provider stub — placeholder for future implementation."""

from __future__ import annotations

from src.services.git_provider import (
    FileContent,
    GitProvider,
    PRResult,
)


class GitLabProvider(GitProvider):
    """GitLab provider stub. All methods raise NotImplementedError."""

    def validate_access(self) -> dict:
        raise NotImplementedError("GitLab provider is not yet implemented")

    def read_file(self, path: str, ref: str) -> FileContent:
        raise NotImplementedError("GitLab provider is not yet implemented")

    def create_branch(self, branch_name: str, from_ref: str) -> None:
        raise NotImplementedError("GitLab provider is not yet implemented")

    def commit_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> None:
        raise NotImplementedError("GitLab provider is not yet implemented")

    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PRResult:
        raise NotImplementedError("GitLab provider is not yet implemented")

    def find_open_pr(self, head: str, base: str) -> str | None:
        raise NotImplementedError("GitLab provider is not yet implemented")
