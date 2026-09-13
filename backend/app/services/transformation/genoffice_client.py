"""GenOffice Localhost Automation Client (Phase D7.5).

Communicates with GenOffice's local Electron automation control server (127.0.0.1:<port>)
via standard loopback HTTP:
- Reads discovery metadata from ~/.genoffice/automation.json
- Checks health (GET /api/v1/health)
- Polls job status and artifact payload (GET /api/v1/jobs/:job_id)
- Opens files directly in GenOffice (POST /api/v1/open) with OS fallback
"""

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, Optional

import httpx

from ...models.artifact import Artifact

logger = logging.getLogger("limo.services.transformation.genoffice_client")


class GenOfficeClientError(Exception):
    """Base exception for GenOffice automation client errors."""
    pass


class GenOfficeUnavailableError(GenOfficeClientError):
    """Raised when GenOffice automation server is not running or unreachable."""
    pass


class GenOfficeAutomationClient:
    """Client for GenOffice Electron Main loopback automation server."""

    def __init__(self, discovery_path: Optional[Path] = None, timeout_seconds: float = 10.0):
        self.discovery_path = discovery_path or (Path.home() / ".genoffice" / "automation.json")
        self.timeout_seconds = timeout_seconds

    def get_discovery_metadata(self) -> Optional[Dict[str, Any]]:
        """Read connection metadata from ~/.genoffice/automation.json."""
        if not self.discovery_path.exists():
            return None
        try:
            content = self.discovery_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, dict) and "port" in data and "token" in data:
                return data
        except Exception as e:
            logger.warning("Failed to parse GenOffice discovery file '%s': %s", self.discovery_path, e)
        return None

    def health_check(self) -> bool:
        """Check if GenOffice automation server is running and healthy."""
        meta = self.get_discovery_metadata()
        if not meta:
            return False
        host = meta.get("host", "127.0.0.1")
        port = meta.get("port")
        url = f"http://{host}:{port}/api/v1/health"
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    return bool(data.get("ok") and data.get("status") == "ready")
        except Exception:
            pass
        return False

    def poll_job(self, genoffice_job_id: str) -> Dict[str, Any]:
        """Query GenOffice automation job status and artifact payload."""
        meta = self.get_discovery_metadata()
        if not meta:
            raise GenOfficeUnavailableError("GenOffice discovery metadata not found. Is GenOffice running?")

        host = meta.get("host", "127.0.0.1")
        port = meta.get("port")
        token = meta.get("token")
        url = f"http://{host}:{port}/api/v1/jobs/{genoffice_job_id}"
        headers = {"X-GenOffice-Token": str(token)}

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 404:
                    raise GenOfficeClientError(f"Job '{genoffice_job_id}' not found in GenOffice queue")
                if res.status_code != 200:
                    raise GenOfficeClientError(f"GenOffice returned HTTP {res.status_code}: {res.text}")
                return res.json()
        except httpx.RequestError as e:
            raise GenOfficeUnavailableError(f"Could not connect to GenOffice automation server: {e}") from e

    def ensure_genoffice_running(self) -> bool:
        """Verify GenOffice automation server is reachable; if not, spawn it in background."""
        if self.health_check():
            return True

        logger.info("GenOffice not running. Auto-launching GenOffice Electron process in background...")
        genoffice_dir = Path(__file__).resolve().parents[4] / "external" / "GenOffice"
        if not genoffice_dir.exists():
            logger.warning("GenOffice directory not found at: %s", genoffice_dir)
            return False

        electron_bin = (
            genoffice_dir / "node_modules" / "electron" / "dist" / "electron.exe"
            if sys.platform == "win32"
            else genoffice_dir / "node_modules" / ".bin" / "electron"
        )
        if not electron_bin.exists():
            logger.warning("Electron binary not found at: %s", electron_bin)
            return False

        env = dict(os.environ)
        env["GENOFFICE_AUTOMATION_ENABLED"] = "true"
        subprocess.Popen(
            [str(electron_bin), "apps/shell"],
            cwd=str(genoffice_dir),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + 30.0
        while time.time() < deadline:
            if self.health_check():
                logger.info("GenOffice successfully launched and verified healthy.")
                return True
            time.sleep(0.5)

        logger.warning("Timed out waiting for GenOffice auto-launch after 30 seconds.")
        return False

    def submit_job(
        self,
        format: str,
        prompt: str,
        title: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submit a document generation job to GenOffice Electron."""
        self.ensure_genoffice_running()
        meta = self.get_discovery_metadata()
        if not meta:
            raise GenOfficeUnavailableError("GenOffice discovery metadata not found. Is GenOffice running?")

        host = meta.get("host", "127.0.0.1")
        port = meta.get("port")
        token = meta.get("token")
        url = f"http://{host}:{port}/api/v1/generate"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-GenOffice-Token": str(token),
            "Content-Type": "application/json",
        }

        job_options = dict(options or {})
        if title:
            job_options["title"] = title

        payload = {
            "format": format,
            "prompt": prompt,
            "options": job_options,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                res = client.post(url, headers=headers, json=payload)
                if res.status_code not in (200, 202):
                    raise GenOfficeClientError(f"GenOffice returned HTTP {res.status_code}: {res.text}")
                return res.json()
        except httpx.RequestError as e:
            raise GenOfficeUnavailableError(f"Could not connect to GenOffice automation server: {e}") from e

    def generate_and_handoff(
        self,
        format: str,
        prompt: str,
        title: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        timeout_sec: float = 120.0,
    ) -> Artifact:
        """Submit job to GenOffice, await completion, and ingest physical artifact into Limo."""
        from .handoff import job_artifact_handoff_service
        from ...services.job_service import job_service
        from ...services.project_service import project_service
        from ...models.enums import OutputFormat
        from ...models.generation_config import GenerationConfig

        # 1. Ensure project and job exist for handoff tracking
        if not project_id:
            proj = project_service.create_project(
                name=title or f"{format.capitalize()} Workspace Project",
                description=f"Automated deliverable project for prompt: {prompt[:80]}",
            )
            project_id = proj.id

        fmt_enum = OutputFormat.DOCUMENT
        norm_fmt = format.lower().strip()
        if norm_fmt in ("presentation", "slides", "pptx"):
            fmt_enum = OutputFormat.PRESENTATION
            format = "presentation"
        elif norm_fmt in ("spreadsheet", "sheets", "xlsx"):
            fmt_enum = OutputFormat.SPREADSHEET
            format = "spreadsheet"
        elif norm_fmt in ("pdf",):
            fmt_enum = OutputFormat.PDF
            format = "pdf"
        else:
            format = "document"

        limo_job = job_service.create_job(
            project_id=project_id,
            session_id=session_id,
            requested_formats=[fmt_enum],
            configuration=GenerationConfig(),
        )

        # 2. Submit to GenOffice
        submit_res = self.submit_job(format=format, prompt=prompt, title=title)
        genoffice_job_id = submit_res.get("job_id")
        if not genoffice_job_id:
            raise GenOfficeClientError(f"Invalid response from GenOffice submit: {submit_res}")
        logger.info("GenOffice job enqueued: %s (format: %s)", genoffice_job_id, format)

        # 3. Poll until completed or failed
        deadline = time.time() + timeout_sec
        final_job = None
        last_substate = None
        while time.time() < deadline:
            poll_data = self.poll_job(genoffice_job_id)
            job = poll_data.get("job") or poll_data
            status = job.get("status")
            substate = (job.get("progress") or {}).get("substate", "")
            if substate != last_substate:
                logger.info("GenOffice job %s: status=%s, substate=%s", genoffice_job_id, status, substate)
                last_substate = substate
            if status == "completed":
                final_job = job
                break
            elif status == "failed":
                err = job.get("error", {})
                raise GenOfficeClientError(f"GenOffice generation failed: {err.get('message', 'Unknown error')}")
            time.sleep(0.6)

        if not final_job:
            raise GenOfficeClientError(f"Timed out waiting for GenOffice job '{genoffice_job_id}' after {timeout_sec}s")

        artifact_payload = final_job.get("artifact")
        if not artifact_payload:
            raise GenOfficeClientError("GenOffice job completed but artifact payload is missing")

        # 4. Handoff to Limo sandboxed storage & SQLite
        artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
            job_id=limo_job.id,
            genoffice_job_id=genoffice_job_id,
            genoffice_artifact=artifact_payload,
        )
        return artifact

    def open_file(self, file_path: str) -> Dict[str, Any]:
        """Open a generated document in GenOffice via loopback HTTP action or OS fallback."""
        target_path = Path(file_path).resolve()
        if not target_path.exists():
            raise FileNotFoundError(f"Document file not found at path: '{file_path}'")

        clean_path_str = str(target_path)

        # 1. Tier 1: Try local HTTP open action if GenOffice server is active
        meta = self.get_discovery_metadata()
        if meta:
            host = meta.get("host", "127.0.0.1")
            port = meta.get("port")
            token = meta.get("token")
            url = f"http://{host}:{port}/api/v1/open"
            headers = {"X-GenOffice-Token": str(token), "Content-Type": "application/json"}
            payload = {"file_path": clean_path_str}

            try:
                with httpx.Client(timeout=5.0) as client:
                    res = client.post(url, headers=headers, json=payload)
                    if res.status_code == 200:
                        data = res.json()
                        if data.get("ok"):
                            logger.info("Successfully opened '%s' via GenOffice HTTP action", clean_path_str)
                            return {
                                "ok": True,
                                "method": "genoffice_http",
                                "opened": True,
                                "file_path": clean_path_str,
                            }
            except Exception as e:
                logger.warning("Tier 1 HTTP open action failed, falling back: %s", e)

        # 2. Tier 2 & 3: Fallback to OS file association / launcher
        try:
            if sys.platform == "win32":
                os.startfile(clean_path_str)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", clean_path_str])
            else:
                subprocess.Popen(["xdg-open", clean_path_str])

            logger.info("Opened '%s' via OS shell fallback", clean_path_str)
            return {
                "ok": True,
                "method": "os_shell",
                "opened": True,
                "file_path": clean_path_str,
            }
        except Exception as err:
            logger.error("Failed to open file '%s': %s", clean_path_str, err)
            raise GenOfficeClientError(f"Failed to open deliverable: {err}") from err


genoffice_client = GenOfficeAutomationClient()
