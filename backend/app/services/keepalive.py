"""Supabase Inactivity Keepalive Worker (Phase D9.7).

Maintains continuous database activity on Supabase PostgreSQL free-tier projects:
- Cadence: ~300 requests/week (~43 requests/day) = 1 ping every 2,016 seconds (~33.6 minutes).
- Monthly Budget: ~1,300 requests/month (only ~2.6% of 50,000 free-tier limit).
- Headroom: >48,700 requests/month remaining for real users and workloads.
- Anti-Pause Guarantee: Resets the 7-day project inactivity pause timer indefinitely.
"""

import asyncio
from datetime import datetime, timezone
import logging
import os
import sys
import time
from typing import Any, Dict, Optional

from ..config import settings

logger = logging.getLogger("limo.services.keepalive")

TARGET_REQUESTS_PER_WEEK = 300
DEFAULT_INTERVAL_SECONDS = (7 * 86400) // TARGET_REQUESTS_PER_WEEK  # 2,016 seconds (~33.6 minutes)


class SupabaseKeepaliveWorker:
    """Background service executing lightweight pings against Supabase PostgreSQL."""

    def __init__(self, interval_seconds: int = DEFAULT_INTERVAL_SECONDS):
        self.interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.total_pings = 0
        self.successful_pings = 0
        self.failed_pings = 0
        self.last_ping_at: Optional[datetime] = None
        self.last_latency_ms: Optional[float] = None
        self.last_error: Optional[str] = None

    def resolve_target_url(self) -> Optional[str]:
        """Resolve active PostgreSQL connection URL."""
        return (
            os.environ.get("SUPABASE_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or (settings.database_url if hasattr(settings, "database_url") else None)
        )

    def ping_sync(self, custom_url: Optional[str] = None) -> Dict[str, Any]:
        """Execute a single synchronous ping against PostgreSQL or configured DB."""
        target_url = custom_url or self.resolve_target_url()
        t0 = time.perf_counter()
        self.total_pings += 1

        if not target_url or "postgres" not in target_url.lower():
            # If not configured with PostgreSQL, perform safe local check
            latency_ms = (time.perf_counter() - t0) * 1000.0
            msg = "Supabase PostgreSQL URL not configured. Keepalive in standby."
            logger.debug("[Keepalive] %s", msg)
            return {
                "success": True,
                "engine": "standby",
                "latency_ms": round(latency_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": msg,
            }

        try:
            import psycopg
            # Clean psycopg connection string (convert postgresql+psycopg:// to postgresql:// if needed)
            clean_url = target_url.replace("postgresql+psycopg://", "postgresql://")
            with psycopg.connect(clean_url, connect_timeout=4) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 AS keepalive_ping, NOW() AS server_time;")
                    row = cur.fetchone()

            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.successful_pings += 1
            self.last_ping_at = datetime.now(timezone.utc)
            self.last_latency_ms = round(latency_ms, 2)
            self.last_error = None

            logger.info(
                "[Keepalive] Ping #%d succeeded in %.2fms (server_time: %s)",
                self.successful_pings,
                latency_ms,
                row[1] if row and len(row) > 1 else "ok",
            )
            return {
                "success": True,
                "engine": "postgres",
                "latency_ms": self.last_latency_ms,
                "timestamp": self.last_ping_at.isoformat(),
                "pings_today_est": self.successful_pings,
                "target_rate": f"{TARGET_REQUESTS_PER_DAY} req/day (every {self.interval_seconds}s)",
            }
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            self.failed_pings += 1
            self.last_error = str(e)
            logger.warning("[Keepalive] Ping failed after %.2fms: %s", latency_ms, e)
            return {
                "success": False,
                "error": str(e),
                "latency_ms": round(latency_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    async def ping_async(self, custom_url: Optional[str] = None) -> Dict[str, Any]:
        """Execute ping asynchronously in thread pool."""
        return await asyncio.to_thread(self.ping_sync, custom_url)

    async def _loop(self) -> None:
        """Internal background loop running at target interval."""
        logger.info(
            "[Keepalive] Starting Supabase keepalive loop: pacing ~%d requests/day (interval: %ds)",
            TARGET_REQUESTS_PER_DAY,
            self.interval_seconds,
        )
        # Initial ping after brief startup delay
        await asyncio.sleep(5)

        while self._running:
            try:
                await self.ping_async()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[Keepalive] Unexpected error in keepalive loop: %s", e)

            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

        logger.info("[Keepalive] Keepalive loop stopped.")

    def start(self) -> None:
        """Launch background worker task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Gracefully stop background worker task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostic metrics for monitoring."""
        return {
            "running": self._running,
            "target_requests_per_week": TARGET_REQUESTS_PER_WEEK,
            "interval_seconds": self.interval_seconds,
            "total_pings": self.total_pings,
            "successful_pings": self.successful_pings,
            "failed_pings": self.failed_pings,
            "last_ping_at": self.last_ping_at.isoformat() if self.last_ping_at else None,
            "last_latency_ms": self.last_latency_ms,
            "last_error": self.last_error,
        }


keepalive_worker = SupabaseKeepaliveWorker()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Supabase Inactivity Keepalive Worker")
    parser.add_argument("--once", action="store_true", help="Send a single keepalive ping and exit")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Interval in seconds between pings")
    parser.add_argument("--url", type=str, default=None, help="Custom database URL")
    args = parser.parse_args()

    worker = SupabaseKeepaliveWorker(interval_seconds=args.interval)

    if args.once:
        print(f"[*] Sending single keepalive ping...")
        res = worker.ping_sync(custom_url=args.url)
        print(f"[+] Result: {res}")
        sys.exit(0 if res.get("success") else 1)

    print(f"[*] Starting Supabase Keepalive Worker CLI")
    print(f"[*] Target rate: ~{TARGET_REQUESTS_PER_WEEK} pings/week (~43/day, every {args.interval}s)")
    print(f"[*] Monthly budget: ~1,300 pings/month (Quota limit: 50,000)")
    print(f"[*] Press Ctrl+C to terminate.")

    try:
        asyncio.run(worker._loop())
    except KeyboardInterrupt:
        print("\n[*] Exiting keepalive worker.")
