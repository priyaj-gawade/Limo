"""Pydantic data models for Limo Web, Research, and Video Subsystems (Phase D8.9)."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class WebSearchResult(BaseModel):
    """Normalized web search result item from Google Custom Search JSON API."""
    title: str = Field(description="Webpage headline or article title")
    url: str = Field(description="Destination target URL")
    display_url: Optional[str] = Field(default=None, description="Formatted domain/path display URL")
    snippet: str = Field(default="", description="Search engine descriptive summary snippet")
    domain: str = Field(description="Normalized domain hostname (e.g. en.wikipedia.org)")
    rank: int = Field(default=1, description="1-based search relevance position")


class YouTubeVideoResult(BaseModel):
    """Structured YouTube video item retrieved via YouTube Data API v3."""
    title: str = Field(description="Video title")
    channel: str = Field(description="Channel or creator name")
    video_id: str = Field(description="11-character YouTube video identifier")
    url: str = Field(description="Full watch URL (https://www.youtube.com/watch?v=...)")
    thumbnail_url: Optional[str] = Field(default=None, description="Video thumbnail image URL")
    published_at: Optional[str] = Field(default=None, description="ISO timestamp of video publication")
    duration: Optional[str] = Field(default=None, description="Video playback duration if available")
    description_snippet: str = Field(default="", description="Video description snippet")


class YouTubeTranscriptSegment(BaseModel):
    """Timestamped caption slice from YouTube transcript."""
    text: str
    start: float
    duration: float


class YouTubeTranscriptResult(BaseModel):
    """Grounded transcript result for a YouTube video."""
    video_id: str
    transcript_available: bool = Field(default=False, description="True if captions exist and were retrieved")
    language: Optional[str] = Field(default=None, description="Caption language code")
    text: str = Field(default="", description="Full aggregated transcript text")
    segments: List[YouTubeTranscriptSegment] = Field(default_factory=list, description="Timestamped segments")
    error: Optional[str] = Field(default=None, description="Diagnostic error if transcript unavailable")


class ScrapeResult(BaseModel):
    """Cleaned article or webpage content returned from web extraction."""
    url: str = Field(description="Canonical source URL")
    title: str = Field(default="", description="Page or article title")
    content: str = Field(description="Cleaned extracted Markdown or plain text content")
    content_type: str = Field(default="article", description="'article' | 'page' | 'document' | 'unknown'")
    scrape_provider: str = Field(
        description="Strictly 'trafilatura' | 'crawl4ai' | 'fallback'. Provider provenance is never obfuscated."
    )
    http_status: int = Field(default=200, description="Upstream HTTP status code")
    elapsed_seconds: float = Field(default=0.0, description="Retrieval latency in seconds")
    source_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata tags, author, date, etc.")


class WebSourceProvenance(BaseModel):
    """Cryptographically anchored provenance for external web evidence used in reasoning or D6."""
    url: str = Field(description="Origin web URL")
    title: str = Field(description="Page or article title")
    domain: str = Field(description="Domain host")
    retrieval_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="UTC ISO timestamp of retrieval",
    )
    source_type: str = Field(default="web_article", description="'web_article' | 'web_page' | 'youtube_video'")
    source_id: Optional[str] = Field(default=None, description="Linked D5 Source entity ID in Limo DB")
    query: Optional[str] = Field(default=None, description="Discovery query that identified this source")
    search_provider: Optional[str] = Field(default=None, description="'ddgs' | 'google' | None")
    scrape_provider: Optional[str] = Field(default=None, description="'trafilatura' | 'crawl4ai' | 'fallback' | None")
    content_hash: Optional[str] = Field(default=None, description="SHA-256 hash of extracted source content")
