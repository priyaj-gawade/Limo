"""Automated test suite for D5.2 Multimodal Media Extractor.

Verifies:
1. Configurable inline vs. Files API routing (not hardcoded to 20 MB).
2. Transcript described as "transcript with timestamps" (not guaranteed verbatim).
3. ExtractedMediaItem.summary is None (evidence-first, summaries deferred to D5.4).
4. Proper SourceType mapping (VIDEO, AUDIO, FILE).
5. Clean Files API lifecycle (upload, poll state, generate, delete remote handle).
6. Live smoke test when Gemini API key is configured.
"""

import io
import os
from unittest.mock import AsyncMock, MagicMock, patch
from PIL import Image
import pytest

from app.config import settings
from app.exceptions import StorageError
from app.models.enums import SourceType
from app.services.extraction.media import MediaExtractor
from app.services.extraction.models import ExtractedDocument, ExtractedMediaItem


class TestMediaExtractorConfiguration:
    """Test suite verifying configurable thresholds and non-hardcoded routing."""

    def test_threshold_configurable_via_constructor(self):
        extractor_10mb = MediaExtractor(inline_threshold_bytes=10 * 1024 * 1024)
        assert extractor_10mb.inline_threshold_bytes == 10 * 1024 * 1024

        extractor_80mb = MediaExtractor(inline_threshold_bytes=80 * 1024 * 1024)
        assert extractor_80mb.inline_threshold_bytes == 80 * 1024 * 1024

    def test_can_handle_media_types(self):
        extractor = MediaExtractor()
        # Video
        assert extractor.can_handle("video/mp4", "lecture.mp4")
        assert extractor.can_handle("video/quicktime", "clip.mov")
        assert extractor.can_handle("video/webm", "recording.webm")

        # Audio
        assert extractor.can_handle("audio/mpeg", "podcast.mp3")
        assert extractor.can_handle("audio/wav", "voice.wav")
        assert extractor.can_handle("audio/m4a", "interview.m4a")

        # Images
        assert extractor.can_handle("image/png", "chart.png")
        assert extractor.can_handle("image/jpeg", "diagram.jpg")
        assert extractor.can_handle("image/webp", "photo.webp")

        # Disallowed / non-media
        assert not extractor.can_handle("application/pdf", "document.pdf")
        assert not extractor.can_handle("text/plain", "notes.txt")
        assert not extractor.can_handle("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "doc.docx")


class TestMediaExtractorPromptsAndModels:
    """Test suite verifying prompt guidelines and evidence-first extraction."""

    def test_video_prompt_requests_timestamps_not_verbatim(self):
        extractor = MediaExtractor()
        prompt = extractor._build_extraction_prompt("video", "conference.mp4")
        assert "transcript with timestamps" in prompt.lower()
        # Must not promise or require verbatim transcription
        assert "verbatim transcription" not in prompt.lower()

    def test_audio_prompt_requests_timestamps(self):
        extractor = MediaExtractor()
        prompt = extractor._build_extraction_prompt("audio", "recording.wav")
        assert "transcript with timestamps" in prompt.lower()

    def test_summary_is_none_preserving_raw_evidence(self):
        """ExtractedMediaItem.summary must be optional and None during D5.2 extraction."""
        item = ExtractedMediaItem(
            media_type="video_source",
            labels=["video", "mp4"],
            transcript="[00:01] Hello world",
            summary=None,
        )
        assert item.summary is None


class TestMediaExtractorMockedExecution:
    """Test suite verifying inline vs Files API dispatch logic and cleanup."""

    @pytest.mark.asyncio
    async def test_small_media_routes_inline(self):
        # 100-byte content with 500-byte threshold -> routes inline
        extractor = MediaExtractor(inline_threshold_bytes=500)
        content = b"Small video byte payload" * 4

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "[00:00] Intro segment\n[00:15] Key milestone reached"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("google.genai.Client", return_value=mock_client):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
                result = await extractor.extract(
                    source_id="src_inline_01",
                    filename="clip.mp4",
                    content=content,
                    metadata={"mime_type": "video/mp4"},
                )

        assert isinstance(result, ExtractedDocument)
        assert result.source_type == SourceType.VIDEO
        assert result.metadata["inline"] is True
        assert len(result.media_items) == 1
        assert result.media_items[0].summary is None
        assert result.media_items[0].transcript is not None
        assert result.media_items[0].metadata["routing"] == "inline"
        mock_client.aio.models.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_large_media_routes_files_api_with_cleanup(self):
        # 1000-byte content with 200-byte threshold -> routes to Files API
        extractor = MediaExtractor(inline_threshold_bytes=200)
        content = b"Large video byte payload" * 40

        mock_client = MagicMock()
        mock_file_handle = MagicMock()
        mock_file_handle.name = "files/test_handle_12345"
        mock_file_handle.state.name = "ACTIVE"

        mock_client.files.upload = MagicMock(return_value=mock_file_handle)
        mock_client.files.get = MagicMock(return_value=mock_file_handle)
        mock_client.files.delete = MagicMock()

        mock_response = MagicMock()
        mock_response.text = "[00:00] Full video analysis\n[01:30] Discussion concludes"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("google.genai.Client", return_value=mock_client):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
                result = await extractor.extract(
                    source_id="src_filesapi_01",
                    filename="large_lecture.mp4",
                    content=content,
                    metadata={"mime_type": "video/mp4"},
                )

        assert isinstance(result, ExtractedDocument)
        assert result.metadata["inline"] is False
        assert result.media_items[0].metadata["routing"] == "files_api"
        # Remote file handle must be deleted to avoid leaked storage
        mock_client.files.delete.assert_called_once_with(name="files/test_handle_12345")

    @pytest.mark.asyncio
    async def test_media_extractor_streams_from_disk_path(self, tmp_path):
        """When file_path is provided, MediaExtractor checks disk size and uploads path directly without RAM buffering."""
        extractor = MediaExtractor(inline_threshold_bytes=100)
        video_file = tmp_path / "large_record.mp4"
        video_file.write_bytes(b"Simulated heavy video data" * 20)  # > 100 bytes

        mock_client = MagicMock()
        mock_file_handle = MagicMock()
        mock_file_handle.name = "files/disk_handle_9999"
        mock_file_handle.state.name = "ACTIVE"

        mock_client.files.upload = MagicMock(return_value=mock_file_handle)
        mock_client.files.get = MagicMock(return_value=mock_file_handle)
        mock_client.files.delete = MagicMock()

        mock_response = MagicMock()
        mock_response.text = "[00:00] Direct disk stream complete"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("google.genai.Client", return_value=mock_client):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
                result = await extractor.extract(
                    source_id="src_disk_01",
                    filename="large_record.mp4",
                    file_path=video_file,
                    content=None,
                    metadata={"mime_type": "video/mp4"},
                )

        assert isinstance(result, ExtractedDocument)
        assert result.metadata["inline"] is False
        assert mock_client.files.upload.call_args.kwargs["file"] == str(video_file)
        mock_client.files.delete.assert_called_once_with(name="files/disk_handle_9999")

    @pytest.mark.asyncio
    async def test_audio_source_type_mapping(self):
        extractor = MediaExtractor(inline_threshold_bytes=1000)
        content = b"Audio bytes"

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "[00:00] Audio speaker 1"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        with patch("google.genai.Client", return_value=mock_client):
            with patch.dict(os.environ, {"GEMINI_API_KEY": "fake_test_key"}):
                result = await extractor.extract(
                    source_id="src_audio_01",
                    filename="briefing.mp3",
                    content=content,
                    metadata={"mime_type": "audio/mpeg"},
                )

        assert result.source_type == SourceType.AUDIO
        assert result.media_items[0].transcript is not None

    @pytest.mark.asyncio
    async def test_missing_api_key_raises_storage_error(self):
        extractor = MediaExtractor()
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(settings, "gemini_key_1", None):
                with patch.object(settings, "gemini_key_2", None):
                    with patch.object(settings, "gemini_key_3", None):
                        with pytest.raises(StorageError, match="Configured Gemini API key is required"):
                            await extractor.extract("src_err", "test.png", b"\x89PNG\r\n", {})


class TestMediaExtractorLiveSmoke:
    """Live smoke test executing real Gemini inference on image media when API key is available."""

    @pytest.mark.asyncio
    async def test_real_gemini_image_extraction(self):
        api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_key_1
        if not api_key:
            pytest.skip("No Gemini API key available in environment for live smoke test")

        # Generate a small valid red PNG
        img = Image.new("RGB", (32, 32), color="red")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        extractor = MediaExtractor()
        result = await extractor.extract(
            source_id="src_smoke_img",
            filename="red_square.png",
            content=png_bytes,
            metadata={"mime_type": "image/png"},
        )

        assert isinstance(result, ExtractedDocument)
        assert result.source_type == SourceType.FILE
        assert len(result.raw_text) > 0
        assert len(result.media_items) == 1
        assert result.media_items[0].summary is None
        assert result.media_items[0].metadata["routing"] == "inline"
