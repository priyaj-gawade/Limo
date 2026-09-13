"""Multimodal media extractor for Video, Audio, and Images using Google GenAI SDK."""

import asyncio
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types

from ...config import settings
from ...exceptions import StorageError
from ...models.enums import SourceType
from .base import BaseExtractor
from .models import (
    ExtractedDocument,
    ExtractedHeading,
    ExtractedMediaItem,
    ExtractedParagraph,
)

logger = logging.getLogger("limo.services.extraction.media")

# Configurable threshold: under this byte limit, send inline; over this limit, route via Files API
# Default: 50 MB (can be configured via LIMO_MEDIA_INLINE_MAX_BYTES up to 100 MB)
DEFAULT_MEDIA_INLINE_MAX_BYTES = int(
    os.getenv("LIMO_MEDIA_INLINE_MAX_BYTES", str(50 * 1024 * 1024))
)


class MediaExtractor(BaseExtractor):
    """Multimodal extractor for images, audio recordings, and video clips.

    Routes media by total size:
    - Small/medium media (<= inline threshold): Sent directly inline via GenAI byte parts.
    - Large media (> inline threshold): Uploaded via Gemini Files API, processed, and cleaned up.
    """

    def __init__(self, inline_threshold_bytes: int = DEFAULT_MEDIA_INLINE_MAX_BYTES):
        self.inline_threshold_bytes = inline_threshold_bytes

    def can_handle(self, mime_type: str, filename: str) -> bool:
        lower_name = filename.lower()
        lower_mime = mime_type.lower()
        media_extensions = (
            ".mp4", ".mov", ".avi", ".mkv", ".webm",
            ".mp3", ".wav", ".m4a", ".ogg", ".aac",
            ".png", ".jpg", ".jpeg", ".webp", ".gif",
        )
        return (
            lower_name.endswith(media_extensions)
            or any(t in lower_mime for t in ("image/", "audio/", "video/"))
        )

    def _infer_media_type(self, mime_type: str, filename: str) -> str:
        lower_mime = mime_type.lower()
        lower_name = filename.lower()
        if "video" in lower_mime or lower_name.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
            return "video"
        if "audio" in lower_mime or lower_name.endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac")):
            return "audio"
        return "image"

    async def extract(
        self,
        source_id: str,
        filename: str,
        content: Optional[bytes] = None,
        metadata: Optional[Dict[str, Any]] = None,
        file_path: Optional[Path] = None,
    ) -> ExtractedDocument:
        if isinstance(content, (Path, str)) and file_path is None:
            file_path = Path(content)
            content = None
        api_key = (
            os.getenv("GEMINI_API_KEY")
            or settings.gemini_key_1
            or settings.gemini_key_2
            or settings.gemini_key_3
        )
        if not api_key:
            raise StorageError("Configured Gemini API key is required for media extraction")

        client = genai.Client(api_key=api_key)
        meta = metadata or {}
        mime_type = meta.get("mime_type", "application/octet-stream")
        media_type = self._infer_media_type(mime_type, filename)

        prompt = self._build_extraction_prompt(media_type, filename)
        model_name = os.getenv("GEMINI_MODEL") or settings.primary_model

        # Calculate file size from disk if available to avoid memory bloat
        if file_path and file_path.exists():
            content_size = file_path.stat().st_size
        elif content is not None:
            content_size = len(content)
        else:
            raise StorageError(f"Cannot extract media for '{filename}': neither file_path nor content provided")

        is_inline = content_size <= self.inline_threshold_bytes
        logger.info(
            "Extracting %s media '%s' (%d bytes, routing=%s)",
            media_type,
            filename,
            content_size,
            "inline" if is_inline else "files_api",
        )

        extracted_text = ""
        if is_inline:
            # For small files sent inline, load bytes on demand
            inline_bytes = content if content is not None else file_path.read_bytes()
            extracted_text = await self._extract_inline(
                client, model_name, inline_bytes, mime_type, prompt
            )
        else:
            # For large files, stream directly from disk via Files API
            extracted_text = await self._extract_via_files_api(
                client=client,
                model_name=model_name,
                file_path=file_path,
                content=content,
                filename=filename,
                mime_type=mime_type,
                prompt=prompt,
            )

        # Parse sections and media item
        headings = [ExtractedHeading(text=f"Media Analysis: {filename}", level=1)]
        paragraphs = [
            ExtractedParagraph(text=p.strip(), section_title=f"Media Analysis: {filename}")
            for p in extracted_text.split("\n\n")
            if p.strip()
        ]

        media_item = ExtractedMediaItem(
            media_type=f"{media_type}_source",
            timestamp_or_bounds="00:00 - End",
            labels=[media_type, filename.split(".")[-1]],
            transcript=extracted_text if media_type in ("audio", "video") else None,
            summary=None,  # Evidence first; summaries belong in D5.4 canonicalization
            metadata={"size_bytes": content_size, "routing": "inline" if is_inline else "files_api"},
        )

        source_type_map = {
            "video": SourceType.VIDEO,
            "audio": SourceType.AUDIO,
            "image": SourceType.FILE,
        }

        return ExtractedDocument(
            source_id=source_id,
            source_name=filename,
            source_type=source_type_map.get(media_type, SourceType.FILE),
            mime_type=metadata.get("mime_type", "application/octet-stream"),
            headings=headings,
            paragraphs=paragraphs,
            media_items=[media_item],
            raw_text=extracted_text,
            metadata={"media_type": media_type, "size_bytes": content_size, "inline": is_inline},
        )

    def _build_extraction_prompt(self, media_type: str, filename: str) -> str:
        if media_type == "video":
            return (
                f"Analyze this video file '{filename}'. "
                "1. Provide a transcript with timestamps for spoken words (note: timestamps with dialogue or key phrases). "
                "2. List key chronological events and scene transitions with timestamps [MM:SS]. "
                "3. Extract all visible text, slides, diagrams, and signs shown on screen. "
                "4. Identify main topics, entities, and actions. "
                "Be thorough, grounded, and factual. Do not speculate."
            )
        elif media_type == "audio":
            return (
                f"Analyze this audio file '{filename}'. "
                "1. Provide a transcript with timestamps for speech segments [MM:SS]. "
                "2. Note speaker changes and key dialogue points. "
                "3. List core facts, numbers, dates, and names mentioned. "
                "Be thorough, grounded, and factual."
            )
        else:
            return (
                f"Analyze this image '{filename}'. "
                "1. Describe visual layout, figures, and elements in detail. "
                "2. Extract all readable text and numbers verbatim. "
                "3. If this is a chart or diagram, transcribe its data points, labels, and axes."
            )

    async def _extract_inline(
        self,
        client: genai.Client,
        model_name: str,
        content: bytes,
        mime_type: str,
        prompt: str,
    ) -> str:
        """Call Gemini generate_content with inline bytes Part."""
        part = types.Part.from_bytes(data=content, mime_type=mime_type)
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=[part, prompt],
        )
        return response.text or ""

    async def _extract_via_files_api(
        self,
        client: genai.Client,
        model_name: str,
        file_path: Optional[Path],
        content: Optional[bytes],
        filename: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        """Upload large file to Gemini Files API directly from disk or temp file, extract, and clean up remote handle."""
        temp_created = False
        upload_path = None

        if file_path and file_path.exists():
            upload_path = str(file_path)
        elif content is not None:
            suffix = os.path.splitext(filename)[1] or ".tmp"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_file:
                upload_path = tmp_file.name
                tmp_file.write(content)
            temp_created = True
        else:
            raise StorageError(f"No media content available to upload for '{filename}'")

        uploaded_file = None
        try:
            logger.info("Uploading large media file '%s' from path '%s' to Gemini Files API...", filename, upload_path)
            uploaded_file = await asyncio.to_thread(
                client.files.upload,
                file=upload_path,
                config=types.UploadFileConfig(mime_type=mime_type, display_name=filename),
            )

            # Wait for processing if video
            if "video" in mime_type.lower():
                while uploaded_file.state.name == "PROCESSING":
                    logger.info("Waiting for video processing on Gemini Files API...")
                    await asyncio.sleep(5)
                    uploaded_file = await asyncio.to_thread(client.files.get, name=uploaded_file.name)

                if uploaded_file.state.name == "FAILED":
                    raise StorageError(f"Gemini Files API failed to process video: {uploaded_file.error}")

            logger.info("Generating content from Gemini Files API handle '%s'...", uploaded_file.name)
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[uploaded_file, prompt],
            )
            return response.text or ""

        finally:
            # Clean up local temporary file only if it was created on-the-fly
            if temp_created and upload_path and os.path.exists(upload_path):
                try:
                    os.remove(upload_path)
                except Exception as e:
                    logger.warning("Failed to clean up temp file '%s': %s", upload_path, e)

            # Clean up remote file from Gemini Files API to avoid orphaned storage
            if uploaded_file and hasattr(uploaded_file, "name"):
                try:
                    await asyncio.to_thread(client.files.delete, name=uploaded_file.name)
                    logger.info("Cleaned up Gemini Files API handle '%s'", uploaded_file.name)
                except Exception as e:
                    logger.warning("Failed to delete remote file '%s': %s", uploaded_file.name, e)
