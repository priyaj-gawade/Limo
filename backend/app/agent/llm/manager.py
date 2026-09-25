"""Centralized LLM Provider Manager coordinating routing, quotas, failover, and resilience."""

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, List, Optional, Set

from ...config import settings
from .adapters.base import (
    AuthenticationError,
    BaseProviderAdapter,
    ModelNotFoundError,
    ProviderServerError,
    RateLimitExceededError,
)
from .adapters.gemini import GeminiAdapter
from .models import LLMResponse, ModelQuota, ProviderCredential, RouteKey
from .quota import DEFAULT_MODEL_QUOTAS, QuotaTracker

logger = logging.getLogger("limo.agent.llm.manager")


class AllRoutesExhaustedError(Exception):
    """Raised when all configured models and credentials have exhausted quota or are in cooldown."""
    pass


class LLMProviderManager:
    """Centralized LLM Provider Manager coordinating resilient multi-credential routing.
    
    Adheres strictly to all Phase D4.7 requirements and MUST-FIX items:
    - Route identity = project + credential + model (MUST-FIX #1).
    - Configured quota + provider feedback + authoritative cooldown (MUST-FIX #2 & #3).
    - Preflight capacity scheduler with safety margin (MUST-FIX #3).
    - ProviderAdapter architecture keeping SDK details encapsulated (MUST-FIX #4).
    - Distinguishes input_tokens, output_tokens, and total_tokens (MUST-FIX #5).
    - Exponential backoff with jitter on transient 429/5xx, bounded by max_retries.
    - Zero private prompt or secret API key logging (keys strictly masked).
    """

    def __init__(
        self,
        credentials: Optional[List[ProviderCredential]] = None,
        primary_model: Optional[str] = None,
        fallback_models: Optional[List[str]] = None,
        adapter: Optional[BaseProviderAdapter] = None,
        quota_tracker: Optional[QuotaTracker] = None,
        max_retries: Optional[int] = None,
        cooldown_duration_sec: Optional[float] = None,
        timeout_sec: Optional[float] = None,
    ):
        self.primary_model = primary_model or settings.primary_model
        self.fallback_models = list(fallback_models or settings.fallback_models)
        self.max_retries = max_retries or settings.llm_max_retries
        self.cooldown_duration_sec = cooldown_duration_sec or settings.llm_cooldown_duration_sec
        self.timeout_sec = timeout_sec or settings.llm_timeout_sec

        self.adapter = adapter or GeminiAdapter()
        self.quota_tracker = quota_tracker or QuotaTracker()

        # Load credentials from settings if not passed explicitly
        if credentials is not None:
            self._credentials = list(credentials)
        else:
            self._credentials = self._load_credentials_from_settings()

        # Round-robin index for fair load balancing across credentials (ponytail: simple integer pointer)
        self._rr_index: int = 0

        # Cumulative execution metrics
        self._total_requests: int = 0
        self._total_retries: int = 0
        self._total_failovers: int = 0
        self._total_failures: int = 0

    def _load_credentials_from_settings(self) -> List[ProviderCredential]:
        """Load configured Gemini credentials securely from settings or environment."""
        creds = []
        raw_keys = []

        # 1. Numbered keys from settings or os.environ
        for proj, cid, key_val in [
            ("project_1", "cred_1", getattr(settings, "gemini_key_1", None) or os.environ.get("GEMINI_KEY_1")),
            ("project_2", "cred_2", getattr(settings, "gemini_key_2", None) or os.environ.get("GEMINI_KEY_2")),
            ("project_3", "cred_3", getattr(settings, "gemini_key_3", None) or os.environ.get("GEMINI_KEY_3")),
        ]:
            if key_val and key_val.strip():
                raw_keys.append((proj, cid, key_val.strip()))

        # 2. Fallback to comma-separated GEMINI_API_KEYS or single GEMINI_API_KEY
        if not raw_keys:
            comma_keys = os.environ.get("GEMINI_API_KEYS") or getattr(settings, "gemini_api_keys", None)
            if comma_keys:
                for idx, k in enumerate(comma_keys.split(","), 1):
                    if k.strip():
                        raw_keys.append((f"project_{idx}", f"cred_{idx}", k.strip()))
            single_key = os.environ.get("GEMINI_API_KEY") or getattr(settings, "gemini_api_key", None)
            if single_key and single_key.strip() and not raw_keys:
                raw_keys.append(("project_1", "cred_1", single_key.strip()))

        for proj, cid, key in raw_keys:
            creds.append(
                ProviderCredential(
                    id=cid,
                    project_id=proj,
                    api_key=key,
                )
            )

        if not creds:
            logger.warning("No Gemini API credentials found in configuration or environment.")
        else:
            logger.info("Loaded %d Gemini credential(s) across authorized projects.", len(creds))
        return creds

    @property
    def credentials(self) -> List[ProviderCredential]:
        """Return credentials, dynamically refreshing from environment if currently empty."""
        if not self._credentials:
            self._credentials = self._load_credentials_from_settings()
        return self._credentials

    def list_credentials(self) -> List[ProviderCredential]:
        """List configured credentials (keys masked in representation)."""
        return list(self.credentials)

    def get_model_chain(self) -> List[str]:
        """Return the prioritized model hierarchy (primary followed by fallbacks)."""
        chain = [self.primary_model]
        for m in self.fallback_models:
            if m not in chain:
                chain.append(m)
        return chain

    def get_all_routes(self) -> List[RouteKey]:
        """Generate all permutations of (project, credential, model)."""
        routes = []
        for model in self.get_model_chain():
            for cred in self.credentials:
                if cred.is_active:
                    routes.append(
                        RouteKey(
                            project_id=cred.project_id,
                            credential_id=cred.id,
                            model_name=model,
                        )
                    )
        return routes

    def select_route(
        self,
        estimated_tokens: int = 500,
        exclude_routes: Optional[Set[RouteKey]] = None,
    ) -> Optional[RouteKey]:
        """Select the highest-priority available route using balanced least-loaded credential routing.
        
        Evaluates models in priority order (primary -> fallback).
        Within each model:
        1. Filters out credentials in cooldown or excluded this turn.
        2. Sorts candidates by:
           - Lowest 1-minute RPM across the credential (least loaded first)
           - Round-robin offset tiebreaker for fair distribution among equal loads
        3. Returns the first route with available quota capacity.
        """
        active_creds = [c for c in self.credentials if c.is_active]
        if not active_creds:
            return None

        excluded = exclude_routes or set()
        n = len(active_creds)

        for model in self.get_model_chain():
            candidates = []
            for i, cred in enumerate(active_creds):
                route = RouteKey(project_id=cred.project_id, credential_id=cred.id, model_name=model)
                if route in excluded:
                    continue
                if not self.quota_tracker.has_capacity(route, estimated_tokens=estimated_tokens):
                    continue
                rpm = self.quota_tracker.get_credential_rpm(cred.id)
                rr_tiebreaker = (i - self._rr_index) % n
                candidates.append((rpm, rr_tiebreaker, cred, route))

            if candidates:
                candidates.sort(key=lambda x: (x[0], x[1]))
                best_cand = candidates[0]
                best_route = best_cand[3]
                best_cred_idx = active_creds.index(best_cand[2])
                self._rr_index = (best_cred_idx + 1) % n
                return best_route

        return None

    def has_available_route(
        self,
        estimated_tokens: int = 500,
        exclude_routes: Optional[Set[RouteKey]] = None,
    ) -> bool:
        """Check if an alternate route is available WITHOUT advancing round-robin index."""
        active_creds = [c for c in self.credentials if c.is_active]
        if not active_creds:
            return False
        excluded = exclude_routes or set()
        for model in self.get_model_chain():
            for cred in active_creds:
                route = RouteKey(project_id=cred.project_id, credential_id=cred.id, model_name=model)
                if route in excluded:
                    continue
                if self.quota_tracker.has_capacity(route, estimated_tokens=estimated_tokens):
                    return True
        return False

    def _get_credential_for_route(self, route: RouteKey) -> ProviderCredential:
        """Find the credential object matching a RouteKey."""
        for c in self.credentials:
            if c.id == route.credential_id and c.project_id == route.project_id:
                return c
        raise KeyError(f"Credential not found for route: {route.to_string()}")

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        tools_declarations: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        estimated_input_tokens: int = 500,
        response_mime_type: Optional[str] = None,
        response_schema: Optional[Any] = None,
        media_parts: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        """Execute a resilient LLM inference call with preflight scheduling, retry, and failover.
        
        Guarantees:
        - Never loops indefinitely (bounded by max_retries or available routes).
        - Exponential backoff with jitter on transient errors when all routes need cooldown.
        - Immediate failover without latency sleep if alternative fresh routes are available.
        - Automatic multi-key round-robin rotation across active credentials.
        - Clear error messaging when credentials are missing.
        """
        self._total_requests += 1
        retries_used = 0
        attempt = 0
        last_error: Optional[Exception] = None

        if not self.credentials:
            self._total_failures += 1
            raise AllRoutesExhaustedError(
                "No Gemini API credentials configured. Set GEMINI_KEY_1, GEMINI_KEY_2, GEMINI_KEY_3 or GEMINI_API_KEYS in environment."
            )

        all_routes = self.get_all_routes()
        max_attempts = max(self.max_retries * 3, len(all_routes) + 6)
        attempted_routes: Set[RouteKey] = set()

        while attempt < max_attempts:
            attempt += 1

            # 1. Preflight route selection (prefer unattempted routes this turn)
            route = self.select_route(estimated_tokens=estimated_input_tokens, exclude_routes=attempted_routes)
            if not route:
                # If all unattempted routes are cooling down, check if any route has recovered
                route = self.select_route(estimated_tokens=estimated_input_tokens)

            if not route:
                # If all routes are temporarily cooling down with a remaining timer, pause for recovery
                min_remaining = min(
                    (self.quota_tracker.get_cooldown_remaining(r) for r in all_routes),
                    default=0.0,
                )
                if 0.0 < min_remaining <= 15.0 and attempt < max_attempts:
                    sleep_sec = min_remaining + 0.3
                    logger.info("All routes cooling down. Pausing %.2fs for route recovery...", sleep_sec)
                    await asyncio.sleep(sleep_sec)
                    route = self.select_route(estimated_tokens=estimated_input_tokens)

            if not route:
                self._total_failures += 1
                raise AllRoutesExhaustedError(
                    f"All configured LLM routes ({len(all_routes)}) are currently in cooldown or quota exhausted. "
                    f"Last error: {last_error}"
                )

            attempted_routes.add(route)
            cred = self._get_credential_for_route(route)
            logger.info(
                "Dispatching LLM request to route [%s] (key: %s, attempt: %d/%d)",
                route.to_string(),
                cred.masked_key,
                attempt,
                max_attempts,
            )

            # 2. Invoke provider adapter
            try:
                response = await self.adapter.generate(
                    model_name=route.model_name,
                    api_key=cred.api_key,
                    prompt=prompt,
                    system_instruction=system_instruction,
                    tools_declarations=tools_declarations,
                    temperature=temperature,
                    timeout_sec=self.timeout_sec,
                    response_mime_type=response_mime_type,
                    response_schema=response_schema,
                    media_parts=media_parts,
                )

                # 3. Success: Record usage with input/output token distinction (MUST-FIX #5)
                self.quota_tracker.record_usage(
                    route=route,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
                response.route_key = route.to_string()
                response.retries_used = retries_used

                logger.info(
                    "LLM request succeeded on route [%s] in %.2fs (tokens: %d in, %d out, %d total)",
                    route.to_string(),
                    response.latency_sec,
                    response.input_tokens,
                    response.output_tokens,
                    response.total_tokens,
                )
                return response

            except RateLimitExceededError as e:
                # Provider 429 rate-limit received on route: engage credential cooldown
                logger.warning("Provider 429 rate-limit received on route [%s]: engaging credential-wide cooldown", route.to_string())
                self.quota_tracker.record_rate_limit(route, cooldown_sec=self.cooldown_duration_sec, credential_wide=True)
                self._total_retries += 1
                self._total_failovers += 1
                retries_used += 1
                last_error = e

                # Pace failover to respect provider RPM limits
                if self.has_available_route(estimated_tokens=estimated_input_tokens, exclude_routes=attempted_routes):
                    await asyncio.sleep(2.5)
                    continue

            except (ProviderServerError, TimeoutError) as e:
                # Transient 5xx or timeout: engage route-specific cooldown
                # Avoid model-wide lockout on a single 503 so other credentials and fresh models remain available
                is_high_demand_503 = isinstance(e, ProviderServerError) and (
                    getattr(e, "status_code", None) == 503 or "high demand" in str(e).lower()
                )
                cooldown_sec = 20.0 if is_high_demand_503 else 10.0
                logger.warning(
                    "Transient error on route [%s]: %s (engaging %.1fs route cooldown)",
                    route.to_string(),
                    str(e),
                    cooldown_sec,
                )
                self.quota_tracker.record_rate_limit(
                    route,
                    cooldown_sec=cooldown_sec,
                    model_wide=False,
                )
                self._total_retries += 1
                self._total_failovers += 1
                retries_used += 1
                last_error = e

                # Pace failover by 2.5s to avoid hammering provider endpoints during demand spikes
                if self.has_available_route(estimated_tokens=estimated_input_tokens, exclude_routes=attempted_routes):
                    await asyncio.sleep(2.5)
                    continue

            except ModelNotFoundError as e:
                # Model is deprecated or unavailable: put route in long cooldown
                logger.error("Model '%s' not available for route [%s]: %s", route.model_name, route.to_string(), str(e))
                self.quota_tracker.record_rate_limit(route, cooldown_sec=3600.0)
                self._total_failovers += 1
                last_error = e

                if self.has_available_route(estimated_tokens=estimated_input_tokens, exclude_routes=attempted_routes):
                    continue

            except AuthenticationError as e:
                # Invalid credential: deactivate this credential
                logger.error("Authentication failure on route [%s]: %s", route.to_string(), str(e))
                cred.is_active = False
                self._total_failovers += 1
                last_error = e

                if self.has_available_route(estimated_tokens=estimated_input_tokens, exclude_routes=attempted_routes):
                    continue

            # If all immediate routes are cooling down, sleep with exponential backoff and jitter
            if attempt < max_attempts:
                backoff_base = 0.5 * (2 ** min(attempt - 1, 4))
                jitter = random.uniform(0.1, 0.4)
                sleep_duration = min(backoff_base + jitter, 5.0)
                logger.info("All immediate routes busy. Retrying in %.2fs (backoff + jitter)...", sleep_duration)
                await asyncio.sleep(sleep_duration)

        # Max retries exhausted
        self._total_failures += 1
        raise last_error or RuntimeError(f"LLM request failed after {max_attempts} attempts")

    def get_diagnostics(self) -> Dict[str, Any]:
        """Report live health diagnostics, masked credentials, and active route metrics."""
        routes_metrics = []
        for route in self.get_all_routes():
            routes_metrics.append(self.quota_tracker.get_route_metrics(route))

        return {
            "provider": self.adapter.provider_name,
            "primary_model": self.primary_model,
            "fallback_models": self.fallback_models,
            "credentials_count": len(self._credentials),
            "credentials": [
                {"id": c.id, "project": c.project_id, "masked_key": c.masked_key, "active": c.is_active}
                for c in self._credentials
            ],
            "total_requests": self._total_requests,
            "total_retries": self._total_retries,
            "total_failovers": self._total_failovers,
            "total_failures": self._total_failures,
            "routes": routes_metrics,
        }


# Global singleton instance initialized from settings
llm_provider_manager = LLMProviderManager()
