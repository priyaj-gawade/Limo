"""GitHub Actions On-Demand Dispatcher Service (Phase D9.6).

Dispatches heavy render tasks (Infographics & Video) to GitHub Actions
via fine-grained Personal Access Tokens and repository_dispatch events.
Provides remote execution tracking and cancellation APIs.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

from ...config import settings
from ...models.transformation import PlannedDeliverable

logger = logging.getLogger("limo.services.transformation.github_dispatcher")


class GitHubActionsDispatcher:
    """Dispatches on-demand compute jobs to GitHub Actions runners."""

    def __init__(
        self,
        pat: Optional[str] = None,
        repo: Optional[str] = None,
        backend_url: Optional[str] = None,
    ):
        self._pat = pat
        self._repo = repo
        self._backend_url = backend_url

    @property
    def pat(self) -> str:
        if self._pat is not None:
            return self._pat.strip()
        # Read from both os.getenv AND settings (pydantic-settings) as belt-and-suspenders
        from ...config import settings
        raw = os.getenv("GITHUB_PAT", "").strip()
        if raw:
            return raw
        return (settings.github_pat or "").strip()

    @property
    def repo(self) -> str:
        if self._repo is not None:
            return self._repo.strip()
        from ...config import settings
        raw = os.getenv("GITHUB_REPO", "").strip()
        if raw:
            return raw
        return (settings.github_repo or "priyaj-gawade/Limo").strip()

    @property
    def backend_url(self) -> str:
        from ...config import settings
        return (
            self._backend_url
            or os.getenv("PUBLIC_BACKEND_URL", "")
            or (settings.public_backend_url if settings.public_backend_url else "")
            or "https://api.limo-ai.online"
        ).rstrip("/")

    def is_configured(self) -> bool:
        """Check if GitHub Actions dispatcher has required credentials."""
        has_pat = bool(self.pat)
        has_repo = bool(self.repo)
        if not has_pat or not has_repo:
            from ...config import settings
            logger.warning(
                "GitHub Actions dispatcher NOT configured: has_pat=%s, has_repo=%s, "
                "os.getenv('GITHUB_PAT')=%s, settings.github_pat=%s",
                has_pat,
                has_repo,
                "SET" if os.getenv("GITHUB_PAT") else "EMPTY",
                "SET" if settings.github_pat else "EMPTY",
            )
        else:
            logger.info("GitHub Actions dispatcher configured: repo=%s, pat=***%s", self.repo, self.pat[-4:] if len(self.pat) > 4 else "****")
        return has_pat and has_repo

    def dispatch_render_job(
        self,
        job_id: str,
        execution_id: str,
        attempt: int,
        target_format: str,
        artifact_id: str,
        title: Optional[str] = None,
        directive: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
    ) -> bool:
        """Send repository_dispatch event to GitHub API.

        Strict invariant: client_payload contains ONLY metadata and URL endpoints.
        Zero large source text or binary content in client_payload.
        """
        if not self.is_configured():
            logger.warning("GitHub Actions dispatcher is not configured (missing GITHUB_PAT or GITHUB_REPO).")
            return False

        dispatch_url = f"https://api.github.com/repos/{self.repo}/dispatches"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.pat}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        client_payload = {
            "job_id": job_id,
            "execution_id": execution_id,
            "attempt": attempt,
            "target_format": target_format,
            "artifact_id": artifact_id,
            "title": title or "Deliverable Render",
            "aspect_ratio": aspect_ratio or "3:4",
            "worker_auth_token": (settings.resolved_worker_token or "").strip(),
            "fetch_url": f"{self.backend_url}/api/v1/jobs/{job_id}/context",
            "callback_url": f"{self.backend_url}/api/v1/jobs/{job_id}/callback",
            "upload_url": f"{self.backend_url}/api/v1/jobs/{job_id}/upload",
        }

        req_body = {
            "event_type": "render_deliverable",
            "client_payload": client_payload,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.post(dispatch_url, headers=headers, json=req_body)
                if res.status_code == 204:
                    logger.info(
                        "Dispatched GitHub Action render job successfully: repo=%s, job=%s, exec=%s",
                        self.repo,
                        job_id,
                        execution_id,
                    )
                    return True
                else:
                    logger.error(
                        "GitHub repository_dispatch failed (%d): %s",
                        res.status_code,
                        res.text,
                    )
                    return False
        except Exception as e:
            logger.error("Failed to connect to GitHub Actions API: %s", e)
            return False

    def cancel_workflow_run(self, run_id: str) -> bool:
        """Cancel a running GitHub Actions workflow execution."""
        if not self.is_configured() or not run_id or str(run_id) == "0":
            return False

        cancel_url = f"https://api.github.com/repos/{self.repo}/actions/runs/{run_id}/cancel"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.pat}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(cancel_url, headers=headers)
                return res.status_code in (202, 200)
        except Exception as e:
            logger.warning("Failed to cancel GitHub workflow run %s: %s", run_id, e)
            return False

    def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Query workflow run execution status from GitHub Actions."""
        if not self.is_configured() or not run_id or str(run_id) == "0":
            return None

        status_url = f"https://api.github.com/repos/{self.repo}/actions/runs/{run_id}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.pat}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.get(status_url, headers=headers)
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.warning("Failed to get GitHub run status for %s: %s", run_id, e)
        return None


github_actions_dispatcher = GitHubActionsDispatcher()
