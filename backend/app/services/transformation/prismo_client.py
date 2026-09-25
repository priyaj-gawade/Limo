"""Prismo Isolated Subprocess Client (Phase D8.8).

Enforces strict boundary between Limo backend and Prismo:
- Zero direct Python imports of Prismo modules.
- Communicates exclusively over an isolated subprocess boundary with external/Prismo/scripts/limo_runner.ts.
- Serves an ephemeral loopback bridge for LimoModelProvider so Prismo consumes Limo's LLM provider seam
  without managing a second Gemini key pool.
- Enforces output path containment security (verifies output files reside strictly within allowed workspace).
- Handles cancellation, timeouts, and bounded SIGTERM/SIGKILL process termination.
"""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any, Callable, Dict, List, Optional

from ...exceptions import BadRequestError, StorageError

logger = logging.getLogger("limo.services.transformation.prismo_client")


class PrismoExecutionError(Exception):
    """Raised when the Prismo isolated runner returns an error."""

    def __init__(self, message: str, code: str = "EXECUTION_ERROR", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class PrismoTimeoutError(PrismoExecutionError):
    """Raised when a Prismo execution times out."""
    pass


class _LLMBridgeHandler(BaseHTTPRequestHandler):
    """Ephemeral HTTP request handler bridging Prismo runner LLM requests to Limo's LLMProviderManager."""

    token: str = ""
    llm_manager: Any = None

    def log_message(self, format: str, *args: Any) -> None:
        # Silence standard HTTP access logging to keep stdout clean
        pass

    def do_POST(self) -> None:
        # Verify bridge token
        req_token = self.headers.get("X-Limo-Bridge-Token", "")
        if req_token != self.token:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'{"error": "Forbidden: invalid bridge token"}')
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body)

        try:
            if self.path == "/generate":
                response_data = self._handle_generate(data)
            elif self.path == "/generate-text":
                response_data = self._handle_generate_text(data)
            else:
                self.send_response(404)
                self.end_headers()
                return

            resp_bytes = json.dumps(response_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_bytes)))
            self.end_headers()
            self.wfile.write(resp_bytes)
        except Exception as e:
            logger.error("[_LLMBridgeHandler] Bridge inference error: %s", e, exc_info=True)
            err_bytes = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_bytes)))
            self.end_headers()
            self.wfile.write(err_bytes)

    def _handle_generate(self, data: Dict[str, Any]) -> Dict[str, Any]:
        messages = data.get("messages", [])
        options = data.get("options", {})

        # Compose prompt and system instruction from messages
        system_inst = options.get("systemInstruction")
        prompt_parts: List[str] = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content") or ""
            if not content and "parts" in msg:
                content = "\n".join(p.get("text", "") for p in msg["parts"] if p.get("text"))

            if role == "system" and not system_inst:
                system_inst = content
            elif role == "user":
                prompt_parts.append(content)
            elif role == "assistant":
                prompt_parts.append(f"[Assistant]: {content}")

        full_prompt = "\n\n".join(prompt_parts) if prompt_parts else "Generate poster design."

        # Execute through Limo LLMProviderManager in a new or existing event loop
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(
                self.llm_manager.generate(
                    prompt=full_prompt,
                    system_instruction=system_inst,
                    temperature=options.get("temperature", 0.2),
                    tools_declarations=options.get("tools"),
                )
            )
        finally:
            loop.close()

        function_calls_payload = [
            {"name": fc.name, "args": getattr(fc, "args", getattr(fc, "arguments", {}))}
            for fc in getattr(res, "function_calls", [])
        ]

        model_name = getattr(res, "model_name", None) or getattr(self.llm_manager, "primary_model", "gemini-3.5-flash-lite")
        return {
            "result": {
                "text": res.text or "",
                "model": model_name,
                "accountId": getattr(res, "route_key", "limo-route"),
                "finishReason": "STOP",
                "functionCalls": function_calls_payload,
            },
            "diagnostics": {
                "provider": "limo-provider-manager",
                "model": model_name,
                "accountId": getattr(res, "route_key", "limo-route"),
                "durationMs": int(getattr(res, "latency_sec", 0.0) * 1000),
                "fallbackOccurred": getattr(res, "retries_used", 0) > 0,
                "attemptsCount": getattr(res, "retries_used", 0) + 1,
                "attemptedAccounts": [getattr(res, "route_key", "limo-route")],
            },
        }

    def _handle_generate_text(self, data: Dict[str, Any]) -> Dict[str, Any]:
        prompt = data.get("prompt", "")
        system_inst = data.get("systemInstruction")

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(
                self.llm_manager.generate(
                    prompt=prompt,
                    system_instruction=system_inst,
                    temperature=0.2,
                )
            )
        finally:
            loop.close()

        model_name = getattr(res, "model_name", None) or getattr(self.llm_manager, "primary_model", "gemini-3.5-flash-lite")
        return {
            "text": res.text or "",
            "model": model_name,
            "accountId": getattr(res, "route_key", "limo-route"),
        }


class PrismoClient:
    """Subprocess client invoking the isolated Prismo runner."""

    def __init__(
        self,
        runner_path: Optional[Path] = None,
        workspace_dir: Optional[Path] = None,
        default_timeout_seconds: float = 240.0,
    ) -> None:
        limo_root = Path(__file__).resolve().parents[4]

        if runner_path is not None:
            self.runner_path = runner_path.resolve()
        else:
            # Check for production compiled runner first, then development TypeScript runner
            prod_runner = limo_root / "engines" / "prismo" / "dist" / "scripts" / "limo_runner.js"
            dev_runner = limo_root / "engines" / "prismo" / "scripts" / "limo_runner.ts"
            self.runner_path = prod_runner if prod_runner.is_file() else dev_runner

        self.workspace_dir = (workspace_dir or (limo_root / "data" / "prismo-workspace")).resolve()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.default_timeout = default_timeout_seconds

    def check_availability(self) -> Dict[str, Any]:
        """Check availability of required runtime dependencies."""
        node_bin = shutil.which("node")
        runner_exists = self.runner_path.is_file()

        # Check Chrome/Chromium availability
        chrome_bin = os.getenv("CHROME_BIN") or os.getenv("PUPPETEER_EXECUTABLE_PATH")
        if not chrome_bin:
            common_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "/usr/bin/google-chrome",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
            for p in common_paths:
                if Path(p).is_file():
                    chrome_bin = p
                    break

        is_ready = bool(node_bin and runner_exists and chrome_bin)
        return {
            "ready": is_ready,
            "node_bin": node_bin,
            "runner_path": str(self.runner_path) if runner_exists else None,
            "chrome_bin": chrome_bin,
        }

    def is_available(self) -> bool:
        """Check if runner script and Node binary are available."""
        return self.runner_path.is_file() and bool(shutil.which("node"))

    def validate_output_path(self, file_path_str: str, allowed_root: Optional[Path] = None) -> Path:
        """Enforce strict output path containment security.

        Verifies that file_path_str resolves strictly inside the allowed workspace root.
        Rejects directory traversal, symlink escapes, and arbitrary absolute system paths.
        """
        if not file_path_str or not file_path_str.strip():
            raise StorageError("Empty or missing output file path from Prismo runner")

        target = Path(file_path_str).resolve()
        root = (allowed_root or self.workspace_dir).resolve()

        # Check path containment
        try:
            is_contained = target.is_relative_to(root)
        except AttributeError:
            # Python < 3.9 fallback
            is_contained = os.path.commonpath([str(root), str(target)]) == str(root)

        if not is_contained:
            raise StorageError(
                f"Security violation: Runner output path '{target}' escapes allowed workspace root '{root}'"
            )

        if not target.is_file() or target.stat().st_size == 0:
            raise StorageError(f"Prismo output file does not exist or is empty: '{target}'")

        return target

    def run_contract(
        self,
        contract: Dict[str, Any],
        timeout_seconds: Optional[float] = None,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        """Execute a Prismo design contract in an isolated subprocess with LimoModelProvider bridge.

        Args:
            contract: Generation parameters matching Prismo RunnerContract.
            timeout_seconds: Timeout before SIGTERM/kill.
            progress_callback: Optional progress listener.

        Returns:
            Structured execution result from runner.
        """
        if not self.is_available():
            raise PrismoExecutionError(
                f"Prismo runner or Node.js not available at {self.runner_path}",
                code="PRISMO_RUNNER_NOT_FOUND",
            )

        timeout = timeout_seconds or self.default_timeout

        # Ensure workspace directory and stock photo key pools are passed
        contract_data = dict(contract)
        contract_data["dataDir"] = str(self.workspace_dir)

        if "pexelsKeys" not in contract_data:
            contract_data["pexelsKeys"] = [
                k.strip() for k in [
                    os.getenv("PEXELS_KEY_1"),
                    os.getenv("PEXELS_KEY_2"),
                    os.getenv("PEXELS_KEY_3"),
                    os.getenv("PEXELS_API_KEY"),
                ] if k and k.strip()
            ]

        if "pixabayKeys" not in contract_data:
            contract_data["pixabayKeys"] = [
                k.strip() for k in [
                    os.getenv("PIXABAY_KEY_1"),
                    os.getenv("PIXABAY_KEY_2"),
                    os.getenv("PIXABAY_KEY_3"),
                    os.getenv("PIXABAY_API_KEY"),
                ] if k and k.strip()
            ]

        if "unsplashKeys" not in contract_data:
            contract_data["unsplashKeys"] = [
                k.strip() for k in [
                    os.getenv("UNSPLASH_ACCESS_KEY"),
                    os.getenv("UNSPLASH_KEY_1"),
                    os.getenv("UNSPLASH_KEY_2"),
                ] if k and k.strip()
            ]

        # Start ephemeral loopback LLM bridge server if mockProvider is not set
        bridge_server: Optional[HTTPServer] = None
        bridge_thread: Optional[threading.Thread] = None

        if not contract_data.get("mockProvider"):
            from ...agent.llm.manager import llm_provider_manager

            bridge_token = secrets.token_hex(16)

            class CustomHandler(_LLMBridgeHandler):
                token = bridge_token
                llm_manager = llm_provider_manager

            # Bind to ephemeral port on 127.0.0.1
            bridge_server = HTTPServer(("127.0.0.1", 0), CustomHandler)
            bridge_port = bridge_server.server_port
            contract_data["bridge"] = {
                "endpoint": f"http://127.0.0.1:{bridge_port}",
                "token": bridge_token,
            }

            bridge_thread = threading.Thread(target=bridge_server.serve_forever, daemon=True)
            bridge_thread.start()

        # Write contract to temporary JSON file
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(contract_data, f, indent=2)
            temp_contract_file = Path(f.name)

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            temp_output_file = Path(f.name)

        proc: Optional[subprocess.Popen] = None
        stderr_lines: List[str] = []

        try:
            node_bin = shutil.which("node") or "node"
            is_ts = self.runner_path.suffix.lower() == ".ts"

            cmd = [node_bin]
            if is_ts:
                cmd.append("--experimental-strip-types")
            cmd.extend([
                str(self.runner_path),
                "--contract",
                str(temp_contract_file),
                "--output-json",
                str(temp_output_file),
            ])

            logger.info("Executing Prismo runner: %s (action: %s, timeout: %ss)",
                        self.runner_path.name, contract_data.get("action"), timeout)

            if progress_callback:
                progress_callback("design_synthesis", "Designing visual composition")

            # Auto-detect Playwright Chromium for CHROME_BIN if not already set
            proc_env = dict(os.environ)
            if not proc_env.get("CHROME_BIN"):
                pw_chromium_candidates = [
                    # Playwright's default cache on Linux (Render)
                    Path.home() / ".cache" / "ms-playwright",
                    # Alternative path
                    Path("/opt/render/.cache/ms-playwright"),
                ]
                for pw_root in pw_chromium_candidates:
                    if pw_root.is_dir():
                        for chrome_path in sorted(pw_root.glob("chromium-*/chrome-linux/chrome"), reverse=True):
                            if chrome_path.is_file():
                                proc_env["CHROME_BIN"] = str(chrome_path)
                                logger.info("Auto-detected Playwright Chromium for CHROME_BIN: %s", chrome_path)
                                break
                    if proc_env.get("CHROME_BIN"):
                        break

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(self.runner_path.parent.parent),  # external/Prismo
                encoding="utf-8",
                errors="replace",
                env=proc_env,
            )

            # Stream stderr asynchronously for progress mapping
            def _read_stderr():
                if proc and proc.stderr:
                    try:
                        for line in iter(proc.stderr.readline, ""):
                            line_str = line.strip()
                            if line_str:
                                stderr_lines.append(line_str)
                                logger.debug("[prismo_runner] %s", line_str)
                                if progress_callback:
                                    if "generating" in line_str.lower():
                                        progress_callback("layout_generation", "Synthesizing poster layout")
                                    elif "exporting" in line_str.lower() or "chrome" in line_str.lower():
                                        progress_callback("raster_export", "Rendering high-resolution PNG")
                    except (ValueError, OSError):
                        pass

            err_thread = threading.Thread(target=_read_stderr, daemon=True)
            err_thread.start()

            stdout_data, _ = proc.communicate(timeout=timeout)
            err_thread.join(timeout=2.0)

            # Parse output JSON
            result_data: Optional[Dict[str, Any]] = None
            if temp_output_file.is_file() and temp_output_file.stat().st_size > 0:
                try:
                    result_data = json.loads(temp_output_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            if result_data is None and stdout_data.strip():
                try:
                    result_data = json.loads(stdout_data.strip())
                except Exception:
                    pass

            stderr_full = "\n".join(str(line) for line in stderr_lines)

            if proc.returncode != 0 or not (result_data and result_data.get("success")):
                err_info = (result_data or {}).get("error", {})
                err_code = err_info.get("code", "PRISMO_RUNNER_FAILED")
                err_msg = err_info.get("message", stderr_full or f"Process exited with code {proc.returncode}")
                raise PrismoExecutionError(
                    err_msg,
                    code=err_code,
                    details=result_data or {"stdout": stdout_data, "stderr": stderr_full},
                )

            return result_data

        except subprocess.TimeoutExpired as exc:
            logger.error("Prismo execution timed out after %s seconds, terminating runner", timeout)
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=3.0)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
            raise PrismoTimeoutError(
                f"Design generation timed out after {timeout} seconds",
                code="RUNNER_TIMEOUT",
            ) from exc

        finally:
            if bridge_server:
                bridge_server.shutdown()
                bridge_server.server_close()
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


# Singleton instance
prismo_client = PrismoClient()
