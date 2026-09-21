"""Quota tracker managing independent per-route accounting, sliding windows, and cooldowns."""

import logging
import time
from typing import Any, Dict, List, Optional

from .models import ModelQuota, RouteKey, UsageRecord

logger = logging.getLogger("limo.agent.llm.quota")

# Initial observations from user's active quota charts (configurable and updateable, MUST-FIX #2)
DEFAULT_MODEL_QUOTAS: Dict[str, ModelQuota] = {
    "gemini-3.5-flash-lite": ModelQuota(rpm=15, tpm=250000, rpd=500, safety_margin=1.0),
    "gemini-3.1-flash-lite": ModelQuota(rpm=15, tpm=250000, rpd=500, safety_margin=1.0),
}


class QuotaTracker:
    """Preflight scheduler and authoritative cooldown tracker per (project, credential, model).
    
    Addresses MUST-FIX #1, #2, #3, and #5:
    - Route identity = project + credential + model.
    - Configured quota + provider feedback + cooldown.
    - Local capacity preflight with safety margin; real 429 overrides and triggers cooldown.
    - Distinguishes input_tokens, output_tokens, and total_tokens.
    """

    def __init__(self, initial_quotas: Optional[Dict[str, ModelQuota]] = None):
        self._quotas: Dict[str, ModelQuota] = dict(DEFAULT_MODEL_QUOTAS)
        if initial_quotas:
            self._quotas.update(initial_quotas)

        # Sliding window usage history per RouteKey
        self._history: Dict[RouteKey, List[UsageRecord]] = {}
        # Cooldown expiration timestamps per RouteKey
        self._cooldowns: Dict[RouteKey, float] = {}

    def configure_quota(self, model_name: str, quota: ModelQuota) -> None:
        """Update quota configuration for a model dynamically (MUST-FIX #2)."""
        self._quotas[model_name] = quota
        logger.info("Updated quota configuration for model '%s': rpm=%d, rpd=%d", model_name, quota.rpm, quota.rpd)

    def get_quota(self, model_name: str) -> ModelQuota:
        """Retrieve quota for model with fallback default."""
        return self._quotas.get(model_name, ModelQuota(rpm=5, tpm=100000, rpd=20, safety_margin=0.9))

    def record_rate_limit(self, route: RouteKey, cooldown_sec: float = 60.0) -> None:
        """Authorize provider 429 feedback to override local capacity and engage cooldown (MUST-FIX #3)."""
        expires_at = time.time() + cooldown_sec
        self._cooldowns[route] = expires_at
        logger.warning(
            "Engaged cooldown on route [%s] for %.1fs (expires at %.1f)",
            route.to_string(),
            cooldown_sec,
            expires_at,
        )

    def is_in_cooldown(self, route: RouteKey) -> bool:
        """Check if route is currently in cooldown."""
        expires_at = self._cooldowns.get(route, 0.0)
        return time.time() < expires_at

    def get_cooldown_remaining(self, route: RouteKey) -> float:
        """Get seconds remaining in active cooldown, or 0.0 if not cooling down."""
        expires_at = self._cooldowns.get(route, 0.0)
        remaining = expires_at - time.time()
        return max(0.0, remaining)

    def _prune_history(self, route: RouteKey, now: float) -> List[UsageRecord]:
        """Prune records older than 24 hours."""
        records = self._history.get(route, [])
        cutoff_24h = now - 86400.0
        active = [r for r in records if r.timestamp >= cutoff_24h]
        self._history[route] = active
        return active

    def has_capacity(self, route: RouteKey, estimated_tokens: int = 500) -> bool:
        """Preflight scheduling check with safety margin (MUST-FIX #3).
        
        Returns False if:
        - Route is in active cooldown
        - Sliding 1-minute RPM exceeds safe_rpm
        - Sliding 1-minute TPM exceeds safe_tpm
        - Sliding 24-hour RPD exceeds safe_rpd
        """
        now = time.time()

        # 1. Cooldown check
        if self.is_in_cooldown(route):
            return False

        # 2. Prune old records
        active = self._prune_history(route, now)

        quota = self.get_quota(route.model_name)
        cutoff_1m = now - 60.0

        # Compute sliding 1m and 24h usage
        rpm_1m = sum(1 for r in active if r.timestamp >= cutoff_1m)
        tpm_1m = sum(r.total_tokens for r in active if r.timestamp >= cutoff_1m)
        rpd_24h = len(active)

        if rpm_1m >= quota.safe_rpm:
            logger.debug("Route [%s] exceeded safe RPM (%d >= %d)", route, rpm_1m, quota.safe_rpm)
            return False

        if (tpm_1m + estimated_tokens) >= quota.safe_tpm:
            logger.debug("Route [%s] exceeded safe TPM (%d >= %d)", route, tpm_1m + estimated_tokens, quota.safe_tpm)
            return False

        if rpd_24h >= quota.safe_rpd:
            logger.debug("Route [%s] exceeded safe RPD (%d >= %d)", route, rpd_24h, quota.safe_rpd)
            return False

        return True

    def record_usage(
        self,
        route: RouteKey,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record completed request tokens distinguishing input and output (MUST-FIX #5)."""
        now = time.time()
        total_tokens = input_tokens + output_tokens
        rec = UsageRecord(
            timestamp=now,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

        if route not in self._history:
            self._history[route] = []
        self._history[route].append(rec)
        logger.debug(
            "Recorded usage for [%s]: input=%d, output=%d, total=%d",
            route,
            input_tokens,
            output_tokens,
            total_tokens,
        )

    def get_route_metrics(self, route: RouteKey) -> Dict[str, Any]:
        """Compute live window metrics for a route."""
        now = time.time()
        active = self._prune_history(route, now)
        quota = self.get_quota(route.model_name)
        cutoff_1m = now - 60.0

        records_1m = [r for r in active if r.timestamp >= cutoff_1m]
        rpm_1m = len(records_1m)
        input_tpm = sum(r.input_tokens for r in records_1m)
        output_tpm = sum(r.output_tokens for r in records_1m)
        total_tpm = input_tpm + output_tpm
        rpd_24h = len(active)

        return {
            "route": route.to_string(),
            "rpm_1m": rpm_1m,
            "rpm_limit": quota.rpm,
            "input_tpm_1m": input_tpm,
            "output_tpm_1m": output_tpm,
            "total_tpm_1m": total_tpm,
            "tpm_limit": quota.tpm,
            "rpd_24h": rpd_24h,
            "rpd_limit": quota.rpd,
            "in_cooldown": self.is_in_cooldown(route),
            "cooldown_remaining_sec": round(self.get_cooldown_remaining(route), 1),
        }
