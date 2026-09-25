"""Google Custom Search JSON API client for Limo (Phase D8.9) [DEPRECATED].

DEPRECATION NOTICE:
Google Custom Search JSON API is deprecated and disabled in Limo.
The project uses the modern zero-configuration `ddgs` provider as primary.
"""

import logging
import os
import urllib.parse
from typing import List, Optional
import warnings

import httpx

from .models import WebSearchResult

logger = logging.getLogger("limo.services.web.google_search")

GOOGLE_SEARCH_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
MAX_QUERY_LENGTH = 200
MAX_RESULTS_LIMIT = 10
DEFAULT_TIMEOUT_SEC = 10.0


class GoogleSearchConfigurationError(Exception):
    """Raised when Google Custom Search API credentials or project permissions are invalid."""
    pass


class GoogleSearchClient:
    """[DEPRECATED] Client for Google Custom Search JSON API.
    
    Use DDGSWebSearchClient (`ddgs`) instead.
    """

    provider_name: str = "google"

    def __init__(
        self,
        api_key: Optional[str] = None,
        cx: Optional[str] = None,
        search_engine_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
    ):
        self._api_key = api_key
        self._cx = cx or search_engine_id
        self.timeout = timeout

    @property
    def is_available(self) -> bool:
        """Check whether Google search credentials are fully configured."""
        return self.is_configured()

    @property
    def api_key(self) -> str:
        key = self._api_key or os.getenv("GOOGLE_SEARCH_API_KEY", "")
        return key.strip()

    @property
    def cx(self) -> str:
        cx_id = self._cx or os.getenv("GOOGLE_CSX_ID", "")
        return cx_id.strip()

    def is_configured(self) -> bool:
        """Check whether both API key and search engine ID are set."""
        return bool(self.api_key and self.cx)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        recency: Optional[str] = None,
        timeout: Optional[float] = None,
        region: Optional[str] = None,
        timelimit: Optional[str] = None,
        **kwargs,
    ) -> List[WebSearchResult]:
        """Perform a real search query against Google Custom Search JSON API.
        
        Args:
            query: User search string (bounded to MAX_QUERY_LENGTH).
            max_results: Number of results to return (1-10).
            recency: Optional Google dateRestrict (e.g. 'd7', 'w2', 'm1').
            timeout: Optional per-request timeout in seconds.
            
        Returns:
            List of structured WebSearchResult objects.
            
        Raises:
            GoogleSearchConfigurationError: If keys missing or project lacks API permission.
            ValueError: If query is blank.
        """
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Search query cannot be empty")

        if len(clean_query) > MAX_QUERY_LENGTH:
            clean_query = clean_query[:MAX_QUERY_LENGTH].strip()

        if not self.is_configured():
            raise GoogleSearchConfigurationError(
                "Google Custom Search is not configured. "
                "Set GOOGLE_SEARCH_API_KEY and GOOGLE_CSX_ID in .env."
            )

        num = max(1, min(max_results, MAX_RESULTS_LIMIT))
        request_timeout = timeout or self.timeout

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": clean_query,
            "num": num,
        }
        if recency:
            params["dateRestrict"] = recency.strip()

        logger.info("Executing Google Custom Search query '%s' (num=%d)", clean_query[:50], num)

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                resp = await client.get(GOOGLE_SEARCH_ENDPOINT, params=params)

                if resp.status_code == 403:
                    body = resp.text
                    logger.error("Google Custom Search returned 403 Forbidden: %s", body[:200])
                    raise GoogleSearchConfigurationError(
                        "Google Custom Search API returned 403 PERMISSION_DENIED. "
                        "The Custom Search JSON API must be enabled for this project in Google Cloud Console: "
                        "https://console.cloud.google.com/apis/library/customsearch.googleapis.com"
                    )

                if resp.status_code == 400:
                    logger.error("Google Custom Search returned 400 Bad Request: %s", resp.text[:200])
                    raise GoogleSearchConfigurationError(f"Invalid Google Search query or parameters: {resp.text[:150]}")

                resp.raise_for_status()
                data = resp.json()

        except httpx.TimeoutException as e:
            logger.warning("Google Custom Search timed out after %.1fs for query '%s'", request_timeout, clean_query)
            raise TimeoutError(f"Google Custom Search request timed out after {request_timeout}s") from e
        except (GoogleSearchConfigurationError, TimeoutError, ValueError):
            raise
        except Exception as e:
            logger.error("Google Custom Search request failed: %s", str(e))
            raise RuntimeError(f"Google Custom Search error: {str(e)}") from e

        items = data.get("items", [])
        results: List[WebSearchResult] = []

        for idx, item in enumerate(items, 1):
            url = item.get("link", "")
            if not url:
                continue

            # Extract domain cleanly
            try:
                parsed_url = urllib.parse.urlparse(url)
                domain = parsed_url.netloc.lower().replace("www.", "")
            except Exception:
                domain = "unknown"

            title = (item.get("title") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            display_url = (item.get("displayLink") or domain).strip()

            results.append(
                WebSearchResult(
                    title=title,
                    url=url,
                    display_url=display_url,
                    snippet=snippet,
                    domain=domain,
                    rank=idx,
                )
            )

        logger.info("Google Custom Search returned %d items for query '%s'", len(results), clean_query[:50])
        return results


# Global singleton instance
google_search_client = GoogleSearchClient()
