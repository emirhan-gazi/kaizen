"""GitHub provider implementation using PyGithub.

Refactored from github_pr.py into the GitProvider interface.
"""

from __future__ import annotations

import logging

from github import Auth, Github, GithubException

from src.services.git_provider import (
    FileContent,
    GitProvider,
    GitProviderError,
    PRResult,
)

logger = logging.getLogger(__name__)


class GitHubProvider(GitProvider):
    """GitProvider implementation for GitHub (cloud and Enterprise)."""

    def __init__(
        self,
        token: str,
        repo: str,
        base_branch: str = "main",
        base_url: str | None = None,
    ) -> None:
        if not token:
            raise GitProviderError("GitHub token is required")
        if not repo:
            raise GitProviderError("GitHub repo (owner/name) is required")
        self._token = token
        self._repo_name = repo
        self._base_branch = base_branch
        self._base_url = base_url

    def _client(self) -> Github:
        kwargs: dict = {"auth": Auth.Token(self._token)}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return Github(**kwargs)

    def validate_access(self) -> dict:
        result: dict = {
            "valid": False,
            "repo": self._repo_name,
            "base_branch": self._base_branch,
            "errors": [],
        }
        try:
            client = self._client()
            repo = client.get_repo(self._repo_name)

            if not repo.permissions.push:
                result["errors"].append(
                    f"Token lacks write access to {self._repo_name}. "
                    "Ensure the token has 'Contents: write' permission."
                )
                return result

            try:
                repo.get_branch(self._base_branch)
            except GithubException:
                result["errors"].append(
                    f"Base branch '{self._base_branch}' not found in {self._repo_name}."
                )
                return result

            result["valid"] = True
            client.close()
        except GithubException as exc:
            status = getattr(exc, "status", None)
            if status == 401:
                result["errors"].append("GitHub token is invalid or expired.")
            elif status == 404:
                result["errors"].append(f"Repository '{self._repo_name}' not found.")
            else:
                result["errors"].append(f"GitHub API error: {exc}")
        return result

    def read_file(self, path: str, ref: str) -> FileContent:
        client = self._client()
        try:
            repo = client.get_repo(self._repo_name)
            contents = repo.get_contents(path, ref=ref)
            return FileContent(
                content=contents.decoded_content.decode("utf-8"),
                sha=contents.sha,
            )
        except GithubException as exc:
            raise GitProviderError(f"Failed to read {path}@{ref}: {exc}") from exc
        finally:
            client.close()

    def create_branch(self, branch_name: str, from_ref: str) -> None:
        client = self._client()
        try:
            repo = client.get_repo(self._repo_name)
            base_ref = repo.get_git_ref(f"heads/{from_ref}")
            base_sha = base_ref.object.sha
            try:
                repo.create_git_ref(f"refs/heads/{branch_name}", base_sha)
            except GithubException as exc:
                if getattr(exc, "status", None) == 422:
                    logger.info("Branch %s already exists, continuing.", branch_name)
                else:
                    raise
        except GithubException as exc:
            raise GitProviderError(f"Failed to create branch {branch_name}: {exc}") from exc
        finally:
            client.close()

    def commit_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> None:
        client = self._client()
        try:
            repo = client.get_repo(self._repo_name)
            if sha:
                repo.update_file(
                    path=path,
                    message=message,
                    content=content,
                    sha=sha,
                    branch=branch,
                )
            else:
                repo.create_file(
                    path=path,
                    message=message,
                    content=content,
                    branch=branch,
                )
        except GithubException as exc:
            raise GitProviderError(f"Failed to commit {path}: {exc}") from exc
        finally:
            client.close()

    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PRResult:
        client = self._client()
        try:
            repo = client.get_repo(self._repo_name)
            pr = repo.create_pull(title=title, body=body, head=head, base=base)
            logger.info("Created GitHub PR #%d: %s", pr.number, pr.html_url)
            return PRResult(success=True, pr_url=pr.html_url)
        except GithubException as exc:
            return PRResult(success=False, error=f"GitHub PR creation failed: {exc}")
        finally:
            client.close()

    def find_open_pr(self, head: str, base: str) -> str | None:
        client = self._client()
        try:
            repo = client.get_repo(self._repo_name)
            pulls = repo.get_pulls(
                state="open",
                head=f"{repo.owner.login}:{head}",
                base=base,
            )
            for pr in pulls:
                logger.info("Found existing open PR #%d for branch %s", pr.number, head)
                return pr.html_url
        except GithubException as exc:
            logger.warning("Failed to check existing PRs: %s", exc)
        finally:
            client.close()
        return None
