"""Web reach and research tools for Limo Agent Infrastructure.

Provides typed agent tools for:
- web_search: Live web search via default search provider
- youtube_search: YouTube Data API v3 + standalone transcripts
- scrape_url: Direct webpage scraping with SSRF protection
- research_web_sources: Multi-source research with D5 canonicalization boundary ingestion
"""

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..context import AgentContext
from ..contracts import BaseTool, PermissionType, ToolResult
from ...services.extraction.ssrf import SSRFProtectionError
from ...services.web.base import WebSearchClient, get_default_search_client
from ...services.web.google_search import GoogleSearchClient, google_search_client
from ...services.web.research_orchestrator import WebResearchService, web_research_service
from ...services.web.web_content_client import WebContentClient, web_content_client
from ...services.web.youtube_search import YouTubeSearchClient, youtube_search_client

logger = logging.getLogger("limo.agent.tools.web")


# ---------------------------------------------------------------------------
# 1. Web Search Tool
# ---------------------------------------------------------------------------

class WebSearchArgs(BaseModel):
    query: str = Field(description="Search query string (maximum 200 characters)")
    num_results: Optional[int] = Field(default=5, description="Number of results to retrieve (1 to 10)")
    timelimit: Optional[str] = Field(default=None, description="Optional time filter ('d', 'w', 'm', 'y')")


class WebSearchTool(BaseTool):
    """Agent tool for querying the live web via WebSearchClient."""

    name: str = "web_search"
    description: str = (
        "Search the live web for recent information, facts, articles, and current events. "
        "Returns verified search result snippets with URLs and domains. Never returns mock data."
    )
    permission_type: PermissionType = PermissionType.EXTERNAL_DISPATCH

    def __init__(self, client: Optional[WebSearchClient] = None) -> None:
        self.client = client or get_default_search_client()

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return WebSearchArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        parsed = WebSearchArgs(**args)
        query = parsed.query.strip()
        if not query:
            return ToolResult.fail("Search query cannot be empty")

        num_results = max(1, min(parsed.num_results or 5, 10))
        provider_name = getattr(self.client, "provider_name", "web_search")

        try:
            results = await self.client.search(
                query=query,
                max_results=num_results,
                timelimit=parsed.timelimit,
            )
            results_data = [item.model_dump() for item in results]
            return ToolResult.ok(
                output={
                    "query": query,
                    "total_results": len(results_data),
                    "results": results_data,
                },
                metadata={"provider": provider_name, "count": len(results_data)},
            )
        except Exception as e:
            logger.warning("WebSearchTool execution failed for '%s': %s", query, e)
            return ToolResult.fail(f"Web search error: {e}", metadata={"query": query, "provider": provider_name})


# ---------------------------------------------------------------------------
# 2. YouTube Search Tool
# ---------------------------------------------------------------------------

class YouTubeSearchArgs(BaseModel):
    query: str = Field(description="Search query for videos on YouTube")
    max_results: Optional[int] = Field(default=5, description="Number of videos to retrieve (1 to 10)")
    include_transcript: Optional[bool] = Field(
        default=False,
        description="Whether to attempt retrieval of full grounded video transcript",
    )


class YouTubeSearchTool(BaseTool):
    """Agent tool for querying real YouTube videos and extracting video transcripts."""

    name: str = "youtube_search"
    description: str = (
        "Find relevant YouTube videos for educational, research, or instructional queries. "
        "Returns titles, creators, watch URLs, and thumbnail previews. "
        "Optionally retrieves grounded video transcripts (with zero hallucination)."
    )
    permission_type: PermissionType = PermissionType.EXTERNAL_DISPATCH

    def __init__(self, client: Optional[YouTubeSearchClient] = None) -> None:
        self.client = client or youtube_search_client

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return YouTubeSearchArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        parsed = YouTubeSearchArgs(**args)
        query = parsed.query.strip()
        if not query:
            return ToolResult.fail("YouTube search query cannot be empty")

        max_results = max(1, min(parsed.max_results or 5, 10))

        try:
            videos = await self.client.search(
                query=query,
                max_results=max_results,
            )
            videos_data = [item.model_dump() for item in videos]
            return ToolResult.ok(
                output=videos_data,
                metadata={"provider": "youtube_data_api_v3", "count": len(videos_data)},
            )
        except Exception as e:
            logger.exception("YouTubeSearchTool execution failed for '%s'", query)
            return ToolResult.fail(f"YouTube search execution failed: {e}")


# ---------------------------------------------------------------------------
# 3. Scrape URL Tool
# ---------------------------------------------------------------------------

class ScrapeUrlArgs(BaseModel):
    url: str = Field(description="Remote webpage or article HTTP/HTTPS URL to read")
    formats: Optional[List[str]] = Field(default=["markdown"], description="Formats to request (default: markdown)")


class ScrapeUrlTool(BaseTool):
    """Agent tool for reading/scraping articles and webpages with SSRF safety."""

    name: str = "scrape_url"
    description: str = (
        "Read and extract clean markdown content from an article or webpage URL. "
        "Uses Trafilatura with dynamic Crawl4AI fallback and SSRF safety. "
        "Strictly reports whether content was extracted via 'trafilatura', 'crawl4ai', or 'fallback'."
    )
    permission_type: PermissionType = PermissionType.EXTERNAL_DISPATCH

    def __init__(self, client: Optional[WebContentClient] = None) -> None:
        self.client = client or web_content_client

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return ScrapeUrlArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        parsed = ScrapeUrlArgs(**args)
        url = parsed.url.strip()
        if not url:
            return ToolResult.fail("URL to scrape cannot be empty")

        try:
            scrape_res = await self.client.scrape(url=url)
            return ToolResult.ok(
                output=scrape_res.model_dump(),
                metadata={
                    "scrape_provider": scrape_res.scrape_provider,
                    "elapsed_seconds": scrape_res.elapsed_seconds,
                    "http_status": scrape_res.http_status,
                },
            )
        except SSRFProtectionError as se:
            logger.warning("SSRF blocked scrape attempt for '%s': %s", url, se)
            return ToolResult.fail(f"Access to URL was blocked by SSRF security policy: {se}")
        except Exception as e:
            logger.exception("ScrapeUrlTool execution failed for '%s'", url)
            return ToolResult.fail(f"Failed to scrape URL: {e}")


# ---------------------------------------------------------------------------
# 4. Multi-Source Web Research Tool
# ---------------------------------------------------------------------------

class ResearchWebSourcesArgs(BaseModel):
    query: str = Field(description="Research topic or search query")
    max_sources: Optional[int] = Field(default=3, description="Number of unique-domain sources to investigate (1 to 5)")
    project_id: Optional[str] = Field(default=None, description="Optional project ID to associate ingested sources with")
    scrape_content: Optional[bool] = Field(default=True, description="Whether to scrape full article content or snippets only")


class ResearchWebSourcesTool(BaseTool):
    """Agent tool for automated end-to-end multi-source web research with D5 canonical ingestion."""

    name: str = "research_web_sources"
    description: str = (
        "Execute comprehensive multi-source web research on a topic. "
        "Discovers sources across unique domains, scrapes full article content, "
        "ingests into Limo D5 source repository, and anchors provenance for deliverables."
    )
    permission_type: PermissionType = PermissionType.EXTERNAL_DISPATCH

    def __init__(self, service: Optional[WebResearchService] = None) -> None:
        self.service = service or web_research_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return ResearchWebSourcesArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        parsed = ResearchWebSourcesArgs(**args)
        query = parsed.query.strip()
        if not query:
            return ToolResult.fail("Research query cannot be empty")

        proj_id = parsed.project_id or (context.project_id if context else None)
        max_sources = max(1, min(parsed.max_sources or 3, 5))

        try:
            res = await self.service.research(
                query=query,
                max_sources=max_sources,
                project_id=proj_id,
                scrape_content=parsed.scrape_content if parsed.scrape_content is not None else True,
            )

            if res.get("error") and not res.get("search_results"):
                return ToolResult.fail(res["error"], metadata={"query": query})

            return ToolResult.ok(
                output=res,
                metadata={
                    "sources_ingested": res.get("sources_ingested", 0),
                    "query": query,
                },
            )
        except Exception as e:
            logger.exception("ResearchWebSourcesTool execution failed for '%s'", query)
            return ToolResult.fail(f"Web research workflow failed: {e}")
