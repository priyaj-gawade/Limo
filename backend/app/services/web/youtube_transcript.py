"""Standalone Limo YouTube Transcript Client (Phase D8.9).

Directly wraps youtube-transcript-api without any third-party framework coupling.
Strictly guarantees zero hallucination: returns transcript_available=False
when captions are unavailable.
"""

import logging
import re
from typing import Optional

from .models import YouTubeTranscriptResult, YouTubeTranscriptSegment

logger = logging.getLogger("limo.services.web.youtube_transcript")


class YouTubeTranscriptClient:
    """Standalone client for retrieving genuine YouTube closed captions / transcripts."""

    @staticmethod
    def extract_video_id(url_or_id: str) -> Optional[str]:
        """Extract an 11-character YouTube video ID from a URL or validate a bare ID."""
        clean = url_or_id.strip()
        if not clean:
            return None

        # Bare 11-character alphanumeric/underscore/dash ID
        if re.match(r"^[A-Za-z0-9_-]{11}$", clean):
            return clean

        # Standard YouTube URLs (watch, share, embed, shorts)
        patterns = [
            r"(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})",
            r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
            r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
            r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, clean)
            if match:
                return match.group(1)

        return None

    def _get_transcript_api(self):
        from youtube_transcript_api import YouTubeTranscriptApi
        return YouTubeTranscriptApi()

    async def get_transcript(self, url_or_id: str, languages: Optional[list[str]] = None) -> YouTubeTranscriptResult:
        """Fetch real closed captions for a YouTube video.
        
        Args:
            url_or_id: YouTube URL or 11-character video ID.
            languages: Preferred language codes (default: ['en', 'en-US']).
            
        Returns:
            YouTubeTranscriptResult indicating availability, text, and segments.
        """
        video_id = self.extract_video_id(url_or_id)
        if not video_id:
            return YouTubeTranscriptResult(
                video_id=url_or_id,
                transcript_available=False,
                error=f"Could not parse valid YouTube video ID from '{url_or_id}'",
            )

        lang_list = languages or ["en", "en-US", "en-GB"]

        try:
            from youtube_transcript_api import (
                YouTubeTranscriptApi,
                TranscriptsDisabled,
                NoTranscriptFound,
                VideoUnavailable,
            )

            ytt = self._get_transcript_api()
            try:
                fetched = ytt.fetch(video_id, languages=lang_list)
                raw_items = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else [dict(x) for x in fetched]
            except Exception:
                transcripts = ytt.list(video_id)
                first = next(iter(transcripts))
                fetched = first.fetch()
                raw_items = fetched.to_raw_data() if hasattr(fetched, "to_raw_data") else [dict(x) for x in fetched]

            transcript_data = raw_items

            segments = [
                YouTubeTranscriptSegment(
                    text=item.get("text", "").strip(),
                    start=round(float(item.get("start", 0.0)), 2),
                    duration=round(float(item.get("duration", 0.0)), 2),
                )
                for item in transcript_data
                if item.get("text", "").strip()
            ]
            aggregated_text = " ".join(s.text for s in segments)

            logger.info("Retrieved transcript for YouTube video '%s': %d segments", video_id, len(segments))
            return YouTubeTranscriptResult(
                video_id=video_id,
                transcript_available=True,
                language="en",
                text=aggregated_text,
                segments=segments,
            )

        except ImportError:
            logger.warning("youtube-transcript-api library not available in environment")
            return YouTubeTranscriptResult(
                video_id=video_id,
                transcript_available=False,
                error="youtube-transcript-api is not installed",
            )
        except Exception as e:
            # Captions disabled, unavailable, or restricted
            err_msg = str(e)
            logger.info("Transcript unavailable for YouTube video '%s': %s", video_id, err_msg[:120])
            return YouTubeTranscriptResult(
                video_id=video_id,
                transcript_available=False,
                error=f"Captions unavailable for this video: {err_msg[:100]}",
            )


# Global singleton instance
youtube_transcript_client = YouTubeTranscriptClient()
