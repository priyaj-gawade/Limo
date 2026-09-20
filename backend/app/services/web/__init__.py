"""Limo Web & Research Services package (Phase D8.9).

Provides:
- Google Custom Search JSON API client
- YouTube Data API v3 client
- Standalone YouTube Transcript client
- Multi-source research orchestrator
"""

from .models import (
    ScrapeResult,
    WebSearchResult,
    WebSourceProvenance,
    YouTubeTranscriptResult,
    YouTubeVideoResult,
)
from .base import WebSearchClient, get_default_search_client
from .ddgs_search import DDGSWebSearchClient, ddgs_search_client
from .google_search import GoogleSearchClient, google_search_client
from .youtube_search import YouTubeSearchClient, youtube_search_client
from .youtube_transcript import YouTubeTranscriptClient, youtube_transcript_client
from .web_content_client import WebContentClient, web_content_client
from .research_orchestrator import WebResearchService, web_research_service

__all__ = [
    "ScrapeResult",
    "WebSearchResult",
    "YouTubeVideoResult",
    "YouTubeTranscriptResult",
    "WebSourceProvenance",
    "WebSearchClient",
    "get_default_search_client",
    "DDGSWebSearchClient",
    "ddgs_search_client",
    "GoogleSearchClient",
    "google_search_client",
    "YouTubeSearchClient",
    "youtube_search_client",
    "YouTubeTranscriptClient",
    "youtube_transcript_client",
    "WebContentClient",
    "web_content_client",
    "WebResearchService",
    "web_research_service",
]
