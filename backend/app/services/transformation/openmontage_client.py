"""OpenMontage Isolated Subprocess Client (Phase D8.1).

Enforces strict boundary between Limo backend and OpenMontage:
- Zero direct Python imports of OpenMontage modules in Limo backend.
- Communicates exclusively over an isolated subprocess boundary.
- Passes structured VideoGenerationContract JSON.
- Receives machine-readable execution results with validated media metadata.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional

logger = logging.getLogger("limo.services.transformation.openmontage_client")


class OpenMontageExecutionError(Exception):
    """Raised when the OpenMontage isolated runner returns an error."""

    def __init__(self, message: str, code: str = "EXECUTION_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class OpenMontageTimeoutError(OpenMontageExecutionError):
    """Raised when an OpenMontage execution times out."""
    pass


class OpenMontageClient:
    """Subprocess client to invoke the isolated OpenMontage runner."""

    def __init__(
        self,
        runner_path: Optional[Path] = None,
        default_timeout_seconds: float = 180.0,
    ) -> None:
        if runner_path is not None:
            self.runner_path = runner_path.resolve()
        else:
            # Default location: engines/video/scripts/limo_runner.py
            limo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.runner_path = (limo_root / "engines" / "video" / "scripts" / "limo_runner.py").resolve()

        self.default_timeout = default_timeout_seconds

    def is_available(self) -> bool:
        """Check if the runner script exists."""
        return self.runner_path.is_file()

    def run_preflight(
        self,
        contract: Dict[str, Any],
        timeout_seconds: float = 30.0,
    ) -> Dict[str, Any]:
        """Perform cheap in-memory script planning and quality gate check without creating workspace or disk artifacts.

        Returns:
            Dict containing {"status": "READY", ...} or {"status": "BLOCKED", "error": ...}
        """
        if not self.is_available():
            return {
                "status": "BLOCKED",
                "error": f"OpenMontage runner script not found at {self.runner_path}",
            }

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(contract, f, indent=2)
            temp_contract_file = Path(f.name)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            temp_output_file = Path(f.name)

        try:
            cmd = [
                sys.executable,
                str(self.runner_path),
                "--contract",
                str(temp_contract_file),
                "--output-json",
                str(temp_output_file),
                "--preflight",
            ]

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.runner_path.parent.parent),
                timeout=timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )

            result_data: Optional[Dict[str, Any]] = None
            if temp_output_file.is_file() and temp_output_file.stat().st_size > 0:
                try:
                    result_data = json.loads(temp_output_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            if result_data is None and proc.stdout.strip():
                try:
                    result_data = json.loads(proc.stdout.strip())
                except Exception:
                    pass

            if result_data is None:
                return {
                    "status": "BLOCKED",
                    "error": proc.stderr or f"Preflight process exited with code {proc.returncode}",
                }

            return result_data

        except subprocess.TimeoutExpired:
            return {
                "status": "BLOCKED",
                "error": f"Preflight script planning timed out after {timeout_seconds} seconds",
            }
        except Exception as e:
            return {
                "status": "BLOCKED",
                "error": f"Preflight execution failed: {e}",
            }
        finally:
            if temp_contract_file.exists():
                try:
                    temp_contract_file.unlink()
                except OSError:
                    pass
            if temp_output_file.exists():
                try:
                    temp_output_file.unlink()
                except OSError:
                    pass

    def run_contract(
        self,
        contract: Dict[str, Any],
        work_dir: Optional[Path] = None,
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a video generation contract in an isolated subprocess.

        Args:
            contract: Dictionary matching VideoGenerationContract schema.
            work_dir: Optional explicit workspace directory.
            timeout_seconds: Maximum execution time before SIGTERM/kill.
            progress_callback: Optional callable(stage_name, message) for real-time progress.

        Returns:
            Structured JSON result dictionary with output metadata and stage records.

        Raises:
            OpenMontageExecutionError: If runner fails or returns non-zero exit code.
            OpenMontageTimeoutError: If execution times out.
        """
        if not self.is_available():
            raise OpenMontageExecutionError(
                f"OpenMontage runner script not found at {self.runner_path}",
                code="RUNNER_NOT_FOUND",
            )

        timeout = timeout_seconds or self.default_timeout

        # Write contract to a secure temporary file to avoid command-line quoting issues
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(contract, f, indent=2)
            temp_contract_file = Path(f.name)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            temp_output_file = Path(f.name)

        proc: Optional[subprocess.Popen] = None
        stderr_lines: List[str] = []

        try:
            cmd = [
                sys.executable,
                str(self.runner_path),
                "--contract",
                str(temp_contract_file),
                "--output-json",
                str(temp_output_file),
            ]

            if work_dir is not None:
                cmd.extend(["--work-dir", str(work_dir.resolve())])

            logger.info("Executing OpenMontage runner: %s (timeout: %ss)", self.runner_path.name, timeout)

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.runner_path.parent.parent),  # external/OpenMontage
                encoding="utf-8",
                errors="replace",
            )

            # Threaded or line-by-line reading of stderr for live progress
            def _read_stderr():
                if proc and proc.stderr:
                    try:
                        for line in iter(proc.stderr.readline, ""):
                            line_str = line.strip()
                            if line_str:
                                stderr_lines.append(line_str)
                                logger.debug("[openmontage_client] %s", line_str)
                                if progress_callback and "[runner]" in line_str:
                                    # Map runner stage logs
                                    if "project initialized" in line_str:
                                        progress_callback("workspace_init", "Preparing video")
                                    elif "planning scenes" in line_str or "script prepared" in line_str:
                                        progress_callback("script_planning", "Planning scenes")
                                    elif "generated narration" in line_str:
                                        progress_callback("narration_generation", "Generating narration")
                                    elif "acquired visuals" in line_str or "fallback visuals" in line_str:
                                        progress_callback("asset_acquisition", "Collecting visuals")
                                    elif "composition complete" in line_str or "composing video" in line_str:
                                        progress_callback("video_composition", "Rendering video")
                                    elif "output validated" in line_str:
                                        progress_callback("output_validation", "Finalizing video")
                    except (ValueError, OSError):
                        pass

            import threading
            err_thread = threading.Thread(target=_read_stderr, daemon=True)
            err_thread.start()

            stdout_data, _ = proc.communicate(timeout=timeout)
            err_thread.join(timeout=2.0)

            # Check output json first
            result_data: Optional[Dict[str, Any]] = None
            if temp_output_file.is_file() and temp_output_file.stat().st_size > 0:
                try:
                    result_data = json.loads(temp_output_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # If output json wasn't populated, attempt stdout parse
            if result_data is None and stdout_data.strip():
                try:
                    result_data = json.loads(stdout_data.strip())
                except Exception:
                    pass

            stderr_full = "\n".join(stderr_lines)

            if proc.returncode != 0 or not (result_data and result_data.get("success")):
                err_info = (result_data or {}).get("error", {})
                err_code = err_info.get("code", "RUNNER_EXECUTION_FAILED")
                err_msg = err_info.get("message", stderr_full or f"Process exited with code {proc.returncode}")
                raise OpenMontageExecutionError(
                    err_msg,
                    code=err_code,
                    details=result_data or {"stdout": stdout_data, "stderr": stderr_full},
                )

            return result_data

        except subprocess.TimeoutExpired as exc:
            logger.error("OpenMontage execution timed out after %s seconds, terminating child process", timeout)
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=3.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            raise OpenMontageTimeoutError(
                f"Video generation timed out after {timeout} seconds",
                code="RUNNER_TIMEOUT",
            ) from exc

        finally:
            if temp_contract_file.exists():
                try:
                    temp_contract_file.unlink()
                except OSError:
                    pass
            if temp_output_file.exists():
                try:
                    temp_output_file.unlink()
                except OSError:
                    pass


# Singleton instance for Limo
openmontage_client = OpenMontageClient()
