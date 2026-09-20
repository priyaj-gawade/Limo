"""YouTube Data API v3 Search Client for Limo (Phase D8.9).

Performs authentic searches against YouTube Data API v3.
Optionally integrates with YouTubeTranscriptClient for genuine caption retrieval.
Never hallucinates video data or summaries.
"""

import html
import logging
import os
from typing import List, Optional

import httpx

from .models import YouTubeTranscriptResult, YouTubeVideoResult
from .youtube_transcript import YouTubeTranscriptClient, youtube_transcript_client

logger = logging.getLogger("limo.services.web.youtube_search")

YOUTUBE_SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
MAX_QUERY_LENGTH = 150
MAX_RESULTS_LIMIT = 10
DEFAULT_TIMEOUT_SEC = 10.0


class YouTubeConfigurationError(Exception):
    """Raised when YouTube Data API credentials are not configured or invalid."""
    pass


class YouTubeSearchClient:
    """Client for YouTube Data API v3."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        transcript_client: Optional[YouTubeTranscriptClient] = None,
        timeout: float = DEFAULT_TIMEOUT_SEC,
    ):
        self._api_key = api_key
        self.transcript_client = transcript_client or youtube_transcript_client
        self.timeout = timeout

    @property
    def api_key(self) -> str:
        key = self._api_key or os.getenv("YOUTUBE_API_KEY", "")
        return key.strip()

    def is_configured(self) -> bool:
        """Check whether YOUTUBE_API_KEY is available."""
        return bool(self.api_key)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        order: str = "relevance",
        timeout: Optional[float] = None,
    ) -> List[YouTubeVideoResult]:
        """Search YouTube for videos matching query string.
        
        Args:
            query: Topic or search terms (bounded to MAX_QUERY_LENGTH).
            max_results: Number of results (1-10, default 5).
            order: 'relevance' | 'date' | 'viewCount'.
            timeout: Optional request timeout in seconds.
            
        Returns:
            List of structured YouTubeVideoResult items.
            
        Raises:
            YouTubeConfigurationError: If YOUTUBE_API_KEY is missing.
            ValueError: If query is blank.
        """
        clean_query = query.strip()
        if not clean_query:
            raise ValueError("YouTube search query cannot be empty")

        if len(clean_query) > MAX_QUERY_LENGTH:
            clean_query = clean_query[:MAX_QUERY_LENGTH].strip()

        if not self.is_configured():
            raise YouTubeConfigurationError(
                "YouTube Data API is not configured. Set YOUTUBE_API_KEY in .env."
            )

        num = max(1, min(max_results, MAX_RESULTS_LIMIT))
        request_timeout = timeout or self.timeout

        params = {
            "key": self.api_key,
            "q": clean_query,
            "part": "snippet",
            "type": "video",
            "maxResults": num,
            "order": order,
        }

        logger.info("Executing YouTube Search query '%s' (maxResults=%d)", clean_query[:50], num)

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                resp = await client.get(YOUTUBE_SEARCH_ENDPOINT, params=params)

                if resp.status_code == 403:
                    logger.error("YouTube Data API returned 403: %s", resp.text[:200])
                    raise YouTubeConfigurationError(
                        "YouTube Data API returned 403 Forbidden. Verify YOUTUBE_API_KEY is active "
                        "and has YouTube Data API v3 enabled in Google Cloud Console."
                    )

                if resp.status_code == 400:
                    logger.error("YouTube Data API returned 400 Bad Request: %s", resp.text[:200])
                    raise YouTubeConfigurationError(f"Invalid YouTube search parameters: {resp.text[:150]}")

                resp.raise_for_status()
                data = resp.json()

        except httpx.TimeoutException as e:
            logger.warning("YouTube search request timed out after %.1fs", request_timeout)
            raise TimeoutError(f"YouTube search request timed out after {request_timeout}s") from e
        except (YouTubeConfigurationError, TimeoutError, ValueError):
            raise
        except Exception as e:
            logger.error("YouTube search request failed: %s", str(e))
            raise RuntimeError(f"YouTube search error: {str(e)}") from e

        items = data.get("items", [])
        results: List[YouTubeVideoResult] = []

        for item in items:
            vid_id = item.get("id", {}).get("videoId", "")
            if not vid_id:
                continue

            snippet = item.get("snippet", {})
            raw_title = snippet.get("title", "")
            clean_title = html.unescape(raw_title).strip()
            channel = html.unescape(snippet.get("channelTitle", "")).strip()
            published_at = snippet.get("publishedAt")
            desc = html.unescape(snippet.get("description", "")).strip()

            # Best available thumbnail
            thumbs = snippet.get("thumbnails", {})
            thumb_url = (
                thumbs.get("high", {}).get("url")
                or thumbs.get("medium", {}).get("url")
                or thumbs.get("default", {}).get("url")
            )

            results.append(
                YouTubeVideoResult(
                    title=clean_title,
                    channel=channel,
                    video_id=vid_id,
                    url=f"https://www.youtube.com/watch?v={vid_id}",
                    thumbnail_url=thumb_url,
                    published_at=published_at,
                    description_snippet=desc,
                )
            )

        logger.info("YouTube search returned %d videos for '%s'", len(results), clean_query[:50])
        return results

    def get_video_transcript(self, url_or_id: str) -> YouTubeTranscriptResult:
        """Fetch transcript for a specific YouTube video."""
        return self.transcript_client.get_transcript(url_or_id)


# Global singleton instance
youtube_search_client = YouTubeSearchClient()
