"""Web Research Orchestrator for Multi-Source Information Gathering (Phase D8.9).

Coordinates:
1. Google Custom Search JSON API queries
2. Deterministic domain-deduplicated result selection (3-5 max)
3. Direct web scraping (Trafilatura / Crawl4AI / fallback) with SSRF pre-validation
4. D5 Ingestion boundary (source_service -> extraction_service -> normalization_service -> canonical_service)
5. WebSourceProvenance generation for UnifiedInputContext and D6 deliverables
"""

import hashlib
import logging
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...exceptions import StorageError
from ...models.enums import SourceType
from ...models.content import CanonicalContent
from ..extraction.ssrf import SSRFProtectionError
from .models import ScrapeResult, WebSearchResult, WebSourceProvenance

logger = logging.getLogger("limo.services.web.research")

MAX_RESEARCH_SOURCES = 5
DEFAULT_RESEARCH_SOURCES = 3


def _slugify(text: str, max_len: int = 40) -> str:
    """Generate a filesystem-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]+", "_", text).strip("_")
    return cleaned[:max_len] if cleaned else "web_source"


class WebResearchService:
    """Orchestrator for automated web discovery, scraping, and D5 canonical ingestion."""

    def __init__(
        self,
        search_client=None,
        scraper_client=None,
        src_service=None,
        ext_service=None,
        norm_service=None,
        canon_service=None,
    ):
        self._search_client = search_client
        self._scraper_client = scraper_client
        self._src_service = src_service
        self._ext_service = ext_service
        self._norm_service = norm_service
        self._canon_service = canon_service

    @property
    def search_client(self):
        if self._search_client is None:
            from .base import get_default_search_client
            self._search_client = get_default_search_client()
        return self._search_client

    @property
    def scraper_client(self):
        if self._scraper_client is None:
            from .web_content_client import web_content_client
            self._scraper_client = web_content_client
        return self._scraper_client

    @property
    def source_service(self):
        if self._src_service is None:
            from ..source_service import source_service
            self._src_service = source_service
        return self._src_service

    @property
    def extraction_service(self):
        if self._ext_service is None:
            from ..extraction.service import extraction_service
            self._ext_service = extraction_service
        return self._ext_service

    @property
    def normalization_service(self):
        if self._norm_service is None:
            from ..normalization.service import normalization_service
            self._norm_service = normalization_service
        return self._norm_service

    @property
    def canonical_service(self):
        if self._canon_service is None:
            from ..canonical.service import canonical_service
            self._canon_service = canonical_service
        return self._canon_service

    async def research(
        self,
        query: str,
        max_sources: int = DEFAULT_RESEARCH_SOURCES,
        project_id: Optional[str] = None,
        scrape_content: bool = True,
        canonicalize: bool = False,
        timelimit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute end-to-end multi-source web research.

        Workflow:
        1. Search web with deterministic bounds.
        2. Filter top unique-domain search results (up to max_sources, bounded 1-5).
        3. Scrape each target via Trafilatura/Crawl4AI (with SSRF validation and fallback).
        4. Ingest into D5 source repository and run extraction/normalization.
        5. Generate WebSourceProvenance records for agent grounding.
        """
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("Research query cannot be empty")

        bounded_max = max(1, min(max_sources, MAX_RESEARCH_SOURCES))
        start_time = datetime.now(timezone.utc)

        # 1. Execute Web Search with Multi-Provider Cascade
        try:
            results = await self.search_client.search(
                query=clean_query,
                max_results=min(10, bounded_max * 3),
                timelimit=timelimit,
            )
            all_results = results if isinstance(results, list) else results.get("results", [])
            search_error = None
        except Exception as e:
            logger.warning("Primary research search failed for '%s': %s", clean_query, e)
            all_results = []
            search_error = str(e)

        # Fallback to secondary provider if primary returned 0 results or errored
        if not all_results:
            try:
                from .base import get_fallback_search_client
                fallback_client = get_fallback_search_client(current_provider=getattr(self.search_client, "provider_name", "ddgs"))
                if fallback_client:
                    logger.info("Retrying web search for '%s' using fallback provider '%s'", clean_query, fallback_client.provider_name)
                    fb_results = await fallback_client.search(
                        query=clean_query,
                        max_results=min(10, bounded_max * 3),
                        timelimit=timelimit,
                    )
                    all_results = fb_results if isinstance(fb_results, list) else fb_results.get("results", [])
                    if all_results:
                        search_error = None
            except Exception as fe:
                logger.warning("Fallback search also failed for '%s': %s", clean_query, fe)

        if not all_results and search_error:
            return {
                "query": clean_query,
                "error": search_error,
                "search_results": [],
                "scraped_sources": [],
                "provenance": [],
                "canonical_contents": [],
                "summary": f"Web search could not be completed: {search_error}",
            }

        # 2. Select Unique Domains Deterministically
        seen_domains = set()
        selected_results: List[WebSearchResult] = []

        for item in all_results:
            domain = item.domain.lower()
            if domain not in seen_domains:
                seen_domains.add(domain)
                selected_results.append(item)
            if len(selected_results) >= bounded_max:
                break

        # If strict unique domain filter yields fewer than requested, allow secondary paths from remaining
        if len(selected_results) < bounded_max:
            for item in all_results:
                if item not in selected_results:
                    selected_results.append(item)
                if len(selected_results) >= bounded_max:
                    break

        logger.info(
            "Selected %d unique sources for research on '%s'",
            len(selected_results),
            clean_query,
        )

        scraped_sources: List[ScrapeResult] = []
        provenance_records: List[WebSourceProvenance] = []
        canonical_records: List[CanonicalContent] = []
        search_prov_name = getattr(self.search_client, "provider_name", "ddgs")

        # 3. Scrape and Ingest into D5
        for res in selected_results:
            if not scrape_content:
                # Metadata-only mode
                prov = WebSourceProvenance(
                    url=res.url,
                    title=res.title,
                    domain=res.domain,
                    retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                    source_type="web_page",
                    query=clean_query,
                    search_provider=search_prov_name,
                    scrape_provider=None,
                )
                provenance_records.append(prov)
                continue

            try:
                # Scrape via direct content client (Trafilatura / Crawl4AI / fallback)
                scrape_res = await self.scraper_client.scrape(res.url)
                scraped_sources.append(scrape_res)

                content_bytes = scrape_res.content.encode("utf-8")
                content_hash = hashlib.sha256(content_bytes).hexdigest()

                # Derive clean filename for D5 storage
                slug = _slugify(scrape_res.title or res.title)
                filename = f"web_{slug}.md"

                # Register as Source entity in D5
                source_meta = {
                    "source_url": res.url,
                    "title": scrape_res.title or res.title,
                    "domain": res.domain,
                    "search_provider": search_prov_name,
                    "scrape_provider": scrape_res.scrape_provider,
                    "scrape_elapsed_seconds": scrape_res.elapsed_seconds,
                    "research_query": clean_query,
                    "content_type": scrape_res.content_type,
                    "http_status": scrape_res.http_status,
                }

                source_record = self.source_service.register_file_source(
                    filename=filename,
                    content=content_bytes,
                    mime_type="text/markdown",
                    project_id=project_id,
                    source_type=SourceType.URL,
                    metadata=source_meta,
                )

                # Execute D5 extraction and normalization
                extracted_doc = await self.extraction_service.extract_source(
                    source=source_record,
                    content=content_bytes,
                )
                norm_doc = self.normalization_service.normalize_extracted_document(extracted_doc)

                # Optional canonicalization if requested
                if canonicalize:
                    try:
                        canon = await self.canonical_service.canonicalize(norm_doc)
                        canonical_records.append(canon)
                    except Exception as ce:
                        logger.warning("Canonicalization failed for '%s': %s", res.url, ce)

                prov = WebSourceProvenance(
                    url=res.url,
                    title=scrape_res.title or res.title,
                    domain=res.domain,
                    retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                    source_type="web_article",
                    source_id=source_record.id,
                    query=clean_query,
                    search_provider=search_prov_name,
                    scrape_provider=scrape_res.scrape_provider,
                    content_hash=content_hash,
                )
                provenance_records.append(prov)

            except SSRFProtectionError as se:
                logger.warning("SSRF blocked URL '%s': %s", res.url, se)
            except Exception as e:
                logger.warning("Failed to scrape/ingest '%s': %s", res.url, e)

        return {
            "query": clean_query,
            "search_results": [r.model_dump() for r in selected_results],
            "scraped_sources": [s.model_dump() for s in scraped_sources],
            "provenance": [p.model_dump() for p in provenance_records],
            "canonical_contents": [c.model_dump() for c in canonical_records],
            "sources_ingested": len(provenance_records),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Global singleton instance
web_research_service = WebResearchService()
