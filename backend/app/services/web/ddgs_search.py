"""Zero-configuration DDGS Web Search provider for Limo (Phase D8.9).

Implements the WebSearchClient protocol using the modern `ddgs` Python package.
Runs with zero mandatory configuration (no API keys, no CX ID, no OAuth),
executes safely off the async event loop via asyncio.to_thread, bounds all query
parameters, and enforces clean result normalization without duplicating research strategy.
"""

import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from .models import WebSearchResult

logger = logging.getLogger("limo.services.web.ddgs_search")

MAX_QUERY_LENGTH = 200
MAX_RESULTS_LIMIT = 10
DEFAULT_REGION = "in-en"
DEFAULT_TIMEOUT_SEC = 10.0


class DDGSWebSearchError(Exception):
    """Base exception for DDGS search provider failures."""
    pass


class DDGSWebSearchClient:
    """Zero-configuration web search provider backed by DDGS."""

    provider_name: str = "ddgs"

    def __init__(
        self,
        default_region: str = DEFAULT_REGION,
        default_timeout: float = DEFAULT_TIMEOUT_SEC,
        max_results_limit: int = MAX_RESULTS_LIMIT,
    ):
        self.default_region = default_region
        self.default_timeout = default_timeout
        self.max_results_limit = max_results_limit

    @property
    def is_available(self) -> bool:
        """Provider is available if the ddgs package is importable (offline-safe check)."""
        try:
            import ddgs  # noqa: F401
            return True
        except ImportError:
            return False

    async def search(
        self,
        query: str,
        max_results: int = 5,
        recency: Optional[str] = None,
        timeout: Optional[float] = None,
        region: Optional[str] = None,
        timelimit: Optional[str] = None,
        **kwargs: Any,
    ) -> List[WebSearchResult]:
        """Execute a text search via DDGS and return normalized WebSearchResult items.

        Args:
            query: User search string (bounded to MAX_QUERY_LENGTH).
            max_results: Max results to retrieve (bounded 1 to MAX_RESULTS_LIMIT).
            recency: Optional recency alias (if provided and timelimit omitted).
            timeout: Optional request timeout in seconds.
            region: Search region code (defaults to 'in-en').
            timelimit: Explicit time filter ('d', 'w', 'm', 'y') determined upstream.

        Returns:
            List of normalized WebSearchResult objects with exact duplicate URLs removed.

        Raises:
            ValueError: If query is blank.
            DDGSWebSearchError: If an unrecoverable search failure occurs.
        """
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Search query cannot be empty")

        if len(clean_query) > MAX_QUERY_LENGTH:
            clean_query = clean_query[:MAX_QUERY_LENGTH].strip()

        num = max(1, min(max_results, self.max_results_limit))
        search_region = region or self.default_region
        search_timelimit = timelimit or recency
        request_timeout = timeout or self.default_timeout

        logger.info(
            "Executing DDGS web search: query='%s', num=%d, region='%s', timelimit=%s",
            clean_query[:50],
            num,
            search_region,
            search_timelimit,
        )

        def _sync_search() -> List[Dict[str, Any]]:
            """Synchronous execution offloaded to a worker thread."""
            try:
                from ddgs import DDGS
                from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException

                with DDGS(timeout=int(request_timeout)) as ddgs_instance:
                    return ddgs_instance.text(
                        query=clean_query,
                        region=search_region,
                        safesearch="moderate",
                        timelimit=search_timelimit,
                        max_results=num,
                        backend="auto",
                    )
            except ImportError as ie:
                logger.error("ddgs package is not installed: %s", ie)
                raise DDGSWebSearchError("Search provider 'ddgs' is not installed.") from ie
            except TimeoutException as te:
                logger.warning("DDGS search timed out for query '%s': %s", clean_query, te)
                raise TimeoutError(f"DDGS search timed out after {request_timeout}s") from te
            except RatelimitException as re:
                logger.warning("DDGS rate limit encountered for query '%s': %s", clean_query, re)
                raise DDGSWebSearchError("Search engine rate limit reached. Please try again shortly.") from re
            except DDGSException as de:
                err_msg = str(de).lower()
                if "no results found" in err_msg or "not found" in err_msg:
                    logger.info("DDGS returned 0 results for query '%s'", clean_query)
                    return []
                logger.warning("DDGS search exception for query '%s': %s", clean_query, de)
                raise DDGSWebSearchError(f"DDGS search error: {de}") from de
            except Exception as ex:
                logger.error("Unexpected error in DDGS search: %s", ex, exc_info=True)
                raise DDGSWebSearchError(f"Unexpected search error: {ex}") from ex

        # Offload blocking DDGS call to thread pool.
        # Note on cancellation: if the awaiting coroutine is cancelled, Limo stops awaiting
        # and discards late results; the underlying thread finishes in the background.
        raw_items = await asyncio.to_thread(_sync_search)

        if not raw_items:
            return []

        results: List[WebSearchResult] = []
        seen_urls = set()

        for idx, item in enumerate(raw_items, 1):
            url = (item.get("href") or item.get("url") or "").strip()
            if not url:
                continue

            # Basic scheme validation
            if not (url.startswith("http://") or url.startswith("https://")):
                continue

            # Remove exact duplicate URLs from the raw result list
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Extract normalized domain
            try:
                parsed = urllib.parse.urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
            except Exception:
                domain = "unknown"

            title = (item.get("title") or "").strip()
            snippet = (item.get("body") or item.get("snippet") or "").strip()
            display_url = domain
            rank = len(results) + 1

            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    display_url=display_url,
                    snippet=snippet,
                    domain=domain,
                    rank=rank,
                )
            )

        logger.info("DDGS mapped %d search results for query '%s'", len(results), clean_query[:50])
        return results


# Global singleton instance
ddgs_search_client = DDGSWebSearchClient()
