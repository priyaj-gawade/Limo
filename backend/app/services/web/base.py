"""Provider-neutral Web Search Client interface and factory for Limo (Phase D8.9).

Enforces the abstract WebSearchClient contract across search providers (DDGS, Google, etc.).
Agent tools and research orchestrators depend on this neutral contract, keeping external
provider implementations completely decoupled from Limo's core logic.
"""

import logging
import os
from typing import List, Optional, Protocol, runtime_checkable

from .models import WebSearchResult

logger = logging.getLogger("limo.services.web.base")


@runtime_checkable
class WebSearchClient(Protocol):
    """Abstract protocol for external web search providers."""

    provider_name: str

    @property
    def is_available(self) -> bool:
        """Check whether provider is ready/configured without network calls."""
        ...

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
        """Execute a web search and return normalized WebSearchResult items."""
        ...


def get_default_search_client() -> WebSearchClient:
    """Resolve the active WebSearchClient according to configuration.

    Defaults strictly to DDGS (zero-configuration). Google Custom Search is only used
    if explicitly configured via WEB_SEARCH_PROVIDER=google and valid credentials exist.
    """
    provider = os.getenv("WEB_SEARCH_PROVIDER", "ddgs").strip().lower()

    if provider == "google":
        from .google_search import google_search_client
        if google_search_client.is_configured():
            return google_search_client
        logger.warning(
            "WEB_SEARCH_PROVIDER=google requested but Google credentials are missing/invalid. "
            "Falling back to zero-config DDGS provider."
        )

    from .ddgs_search import ddgs_search_client
    return ddgs_search_client
