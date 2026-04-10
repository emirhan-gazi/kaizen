"""Bitbucket Server provider implementation using REST API v1.0 via httpx.

Supports Bitbucket Server / Data Center with Bearer token auth.
"""

from __future__ import annotations

import logging

import httpx

from src.services.git_provider import (
    FileContent,
    GitProvider,
    GitProviderError,
    PRResult,
)

logger = logging.getLogger(__name__)


class BitbucketServerProvider(GitProvider):
    """GitProvider implementation for Bitbucket Server / Data Center."""

    def __init__(
        self,
        base_url: str,
        token: str,
        project: str,
        repo: str,
        base_branch: str = "main",
        ssl_verify: bool = True,
    ) -> None:
        if not base_url:
            raise GitProviderError("Bitbucket Server base URL is required")
        if not token:
            raise GitProviderError("Bitbucket Server token is required")
        if not project:
            raise GitProviderError("Bitbucket Server project key is required")
        if not repo:
            raise GitProviderError("Bitbucket Server repo slug is required")

        self._base_url = base_url.rstrip("/")
        self._token = token
        self._project = project
        self._repo = repo
        self._base_branch = base_branch
        self._ssl_verify = ssl_verify

    def _api_url(self, path: str) -> str:
        return f"{self._base_url}/rest/api/1.0/projects/{self._project}/repos/{self._repo}{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(verify=self._ssl_verify, timeout=30.0)

    def validate_access(self) -> dict:
        result: dict = {
            "valid": False,
            "repo": f"{self._project}/{self._repo}",
            "base_branch": self._base_branch,
            "errors": [],
        }
        with self._client() as client:
            # Check repo access
            resp = client.get(self._api_url(""), headers=self._headers())
            if resp.status_code == 401:
                result["errors"].append("Bitbucket token is invalid or expired.")
                return result
            if resp.status_code == 404:
                result["errors"].append(
                    f"Repository '{self._project}/{self._repo}' not found."
                )
                return result
            if resp.status_code != 200:
                result["errors"].append(f"Bitbucket API error: {resp.status_code}")
                return result

            # Check branch exists
            branch_resp = client.get(
                self._api_url(f"/branches?filterText={self._base_branch}"),
                headers=self._headers(),
            )
            if branch_resp.status_code == 200:
                branches = branch_resp.json().get("values", [])
                found = any(
                    b.get("displayId") == self._base_branch for b in branches
                )
                if not found:
                    result["errors"].append(
                        f"Base branch '{self._base_branch}' not found."
                    )
                    return result

            result["valid"] = True
        return result

    def read_file(self, path: str, ref: str) -> FileContent:
        with self._client() as client:
            # Get file content
            resp = client.get(
                self._api_url(f"/browse/{path}"),
                headers=self._headers(),
                params={"at": ref, "limit": 10000},
            )
            if resp.status_code != 200:
                raise GitProviderError(
                    f"Failed to read {path}@{ref}: HTTP {resp.status_code}"
                )
            data = resp.json()
            lines = data.get("lines", [])
            content = "\n".join(line.get("text", "") for line in lines)

            # Get the latest commit SHA on the branch (required for editing existing files)
            sha = ""
            branch_resp = client.get(
                self._api_url(f"/branches?filterText={ref}"),
                headers=self._headers(),
            )
            if branch_resp.status_code == 200:
                for b in branch_resp.json().get("values", []):
                    if b.get("displayId") == ref:
                        sha = b.get("latestCommit", "")
                        break

            return FileContent(content=content, sha=sha)

    def create_branch(self, branch_name: str, from_ref: str) -> None:
        with self._client() as client:
            # Resolve from_ref to a commit hash
            ref_resp = client.get(
                self._api_url(f"/branches?filterText={from_ref}"),
                headers=self._headers(),
            )
            start_point = from_ref
            if ref_resp.status_code == 200:
                branches = ref_resp.json().get("values", [])
                for b in branches:
                    if b.get("displayId") == from_ref:
                        start_point = b.get("latestCommit", from_ref)
                        break

            resp = client.post(
                self._api_url("/branches"),
                headers=self._headers(),
                json={
                    "name": branch_name,
                    "startPoint": start_point,
                },
            )
            if resp.status_code == 409:
                logger.info("Branch %s already exists, continuing.", branch_name)
                return
            if resp.status_code not in (200, 201):
                raise GitProviderError(
                    f"Failed to create branch {branch_name}: HTTP {resp.status_code} — {resp.text}"
                )

    def commit_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> None:
        with self._client() as client:
            # Bitbucket Server uses multipart form for file commits
            content_bytes = content.encode("utf-8")
            files = {
                "content": (path.split("/")[-1], content_bytes),
            }
            data: dict[str, str] = {
                "message": message,
                "branch": branch,
            }
            if sha:
                data["sourceCommitId"] = sha

            resp = client.put(
                self._api_url(f"/browse/{path}"),
                headers={"Authorization": f"Bearer {self._token}"},
                data=data,
                files=files,
            )
            if resp.status_code not in (200, 201):
                raise GitProviderError(
                    f"Failed to commit {path}: HTTP {resp.status_code} — {resp.text}"
                )

    def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PRResult:
        with self._client() as client:
            resp = client.post(
                self._api_url("/pull-requests"),
                headers=self._headers(),
                json={
                    "title": title,
                    "description": body,
                    "fromRef": {
                        "id": f"refs/heads/{head}",
                        "repository": {
                            "slug": self._repo,
                            "project": {"key": self._project},
                        },
                    },
                    "toRef": {
                        "id": f"refs/heads/{base}",
                        "repository": {
                            "slug": self._repo,
                            "project": {"key": self._project},
                        },
                    },
                },
            )
            if resp.status_code in (200, 201):
                pr_data = resp.json()
                pr_id = pr_data.get("id")
                pr_url = (
                    f"{self._base_url}/projects/{self._project}"
                    f"/repos/{self._repo}/pull-requests/{pr_id}"
                )
                logger.info("Created Bitbucket PR #%s: %s", pr_id, pr_url)
                return PRResult(success=True, pr_url=pr_url)
            if resp.status_code == 409:
                # Duplicate PR — find the existing one
                existing = self.find_open_pr(head, base)
                if existing:
                    return PRResult(success=True, pr_url=existing, reused_existing=True)
            return PRResult(
                success=False,
                error=f"Bitbucket PR creation failed: HTTP {resp.status_code} — {resp.text}",
            )

    def find_open_pr(self, head: str, base: str) -> str | None:
        with self._client() as client:
            resp = client.get(
                self._api_url("/pull-requests"),
                headers=self._headers(),
                params={
                    "state": "OPEN",
                    "direction": "OUTGOING",
                },
            )
            if resp.status_code != 200:
                logger.warning("Failed to list PRs: HTTP %s", resp.status_code)
                return None

            for pr in resp.json().get("values", []):
                from_ref = pr.get("fromRef", {}).get("displayId", "")
                to_ref = pr.get("toRef", {}).get("displayId", "")
                if from_ref == head and to_ref == base:
                    pr_id = pr.get("id")
                    pr_url = (
                        f"{self._base_url}/projects/{self._project}"
                        f"/repos/{self._repo}/pull-requests/{pr_id}"
                    )
                    logger.info("Found existing open PR #%s for branch %s", pr_id, head)
                    return pr_url
        return None
