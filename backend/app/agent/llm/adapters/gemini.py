"""Official Google GenAI SDK Provider Adapter for Gemini models."""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from ..models import FunctionCallPayload, LLMResponse
from .base import (
    AuthenticationError,
    BaseProviderAdapter,
    ModelNotFoundError,
    ProviderServerError,
    RateLimitExceededError,
)

logger = logging.getLogger("limo.agent.llm.adapters.gemini")


class GeminiAdapter(BaseProviderAdapter):
    """Production provider adapter wrapping the official Google GenAI SDK."""

    provider_name = "gemini"

    def __init__(self):
        self._clients: Dict[Tuple[str, int], genai.Client] = {}

    def _get_client(self, api_key: str) -> genai.Client:
        """Cache client instance per (API key, event loop) so async sessions are never shared across event loops."""
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)
        except RuntimeError:
            loop_id = 0
        cache_key = (api_key, loop_id)
        if cache_key not in self._clients:
            # Disable SDK-internal tenacity retries so our LLMProviderManager
            # controls all retry/failover logic.  Without this the SDK silently
            # retries 503s for ~50 seconds before surfacing the error.
            no_retry_opts = types.HttpOptions(
                retry_options=types.HttpRetryOptions(attempts=0)
            )
            self._clients[cache_key] = genai.Client(
                api_key=api_key,
                http_options=no_retry_opts,
            )
        return self._clients[cache_key]

    async def generate(
        self,
        model_name: str,
        api_key: str,
        prompt: str,
        system_instruction: Optional[str] = None,
        tools_declarations: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        timeout_sec: float = 30.0,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Any] = None,
        media_parts: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Call official Google GenAI SDK generate_content with error mapping."""
        client = self._get_client(api_key)
        start_time = time.time()

        # Build GenerateContentConfig
        config_kwargs: Dict[str, Any] = {
            "temperature": temperature,
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction

        if tools_declarations:
            if (
                isinstance(tools_declarations, list)
                and tools_declarations
                and isinstance(tools_declarations[0], dict)
                and ("functionDeclarations" in tools_declarations[0] or "function_declarations" in tools_declarations[0])
            ):
                config_kwargs["tools"] = tools_declarations
            else:
                config_kwargs["tools"] = [{"function_declarations": tools_declarations}]

        if response_mime_type:
            config_kwargs["response_mime_type"] = response_mime_type

        if response_schema:
            config_kwargs["response_schema"] = response_schema

        config = types.GenerateContentConfig(**config_kwargs)

        # Build multimodal contents if native media parts are provided
        call_contents: Any = prompt
        if media_parts:
            contents_list: List[Any] = []
            for part_info in media_parts:
                data = part_info.get("data")
                mime_type = part_info.get("mime_type", "image/jpeg")
                file_path = part_info.get("file_path")
                if data and isinstance(data, bytes):
                    contents_list.append(types.Part.from_bytes(data=data, mime_type=mime_type))
                elif file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                    contents_list.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))

            if contents_list:
                contents_list.append(prompt)
                call_contents = contents_list

        try:
            # Enforce async timeout (SDK retries are disabled at client level,
            # so this timeout only covers a single network round-trip)
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=call_contents,
                    config=config,
                ),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError as e:
            logger.warning("Gemini request to model '%s' timed out after %.1fs", model_name, timeout_sec)
            raise TimeoutError(f"Gemini model request timed out after {timeout_sec}s") from e
        except genai_errors.APIError as e:
            code = getattr(e, "code", None)
            msg = getattr(e, "message", str(e))
            logger.warning("Gemini API error (%s) on model '%s': %s", code, model_name, msg)
            if code == 429 or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                raise RateLimitExceededError(msg, status_code=429) from e
            elif code in (401, 403) or "PERMISSION_DENIED" in msg:
                raise AuthenticationError(msg, status_code=code) from e
            elif code == 404 or "NOT_FOUND" in msg:
                raise ModelNotFoundError(msg, status_code=404) from e
            elif code and code >= 500:
                raise ProviderServerError(msg, status_code=code) from e
            raise ProviderServerError(f"Unexpected provider error: {msg}", status_code=code) from e
        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                raise RateLimitExceededError(err_str, status_code=429) from e
            logger.error("Unexpected error in GeminiAdapter: %s", err_str, exc_info=True)
            raise

        elapsed = time.time() - start_time

        # Extract token usage (MUST-FIX #5)
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0
            total_tokens = getattr(response.usage_metadata, "total_token_count", 0) or (input_tokens + output_tokens)

        # Extract function calls if any
        function_calls: List[FunctionCallPayload] = []
        if hasattr(response, "function_calls") and response.function_calls:
            for fc in response.function_calls:
                function_calls.append(
                    FunctionCallPayload(
                        name=fc.name,
                        args=dict(fc.args or {}),
                        id=getattr(fc, "id", None),
                    )
                )

        # Extract text content
        text_content = getattr(response, "text", None)

        # Guard against empty generation / malformed function call: trigger failover rotation
        if not text_content and not function_calls:
            candidates = getattr(response, "candidates", None) or []
            finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
            logger.warning(
                "Gemini model '%s' returned empty text and zero function calls (finish_reason=%s)",
                model_name,
                finish_reason,
            )
            raise ProviderServerError(
                f"Model '{model_name}' completed with empty text (finish_reason={finish_reason})",
                status_code=502,
            )

        return LLMResponse(
            text=text_content,
            function_calls=function_calls,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_sec=elapsed,
        )
