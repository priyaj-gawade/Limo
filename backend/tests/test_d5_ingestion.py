"""Tests for D5.1: Ingestion, Source Registration, Versioned Deduplication, and Redirect-Aware SSRF Protection."""

import io
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.db.init import init_db
from app.models.enums import SourceType
from app.exceptions import StorageError
from app.services.extraction.constants import EXTRACTION_VERSION, DEFAULT_CONFIG_HASH
from app.services.extraction.ssrf import (
    MAX_URL_DOWNLOAD_BYTES,
    SSRFProtectionError,
    fetch_url_ssrf_safe,
    is_ip_safe,
    validate_url,
)
from app.services.source_service import SourceService
from app.storage.service import StorageService
import ipaddress


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


class TestSSRFProtection:
    """Test suite verifying strict IP range rejection and redirect hop validation."""

    def test_blocks_private_ipv4(self):
        private_ips = [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",  # AWS/Cloud metadata
            "100.64.0.1",       # Carrier-grade NAT
            "0.0.0.0",
        ]
        for ip_str in private_ips:
            ip = ipaddress.ip_address(ip_str)
            assert not is_ip_safe(ip), f"IP {ip_str} should be marked unsafe"

    def test_blocks_private_and_loopback_ipv6(self):
        unsafe_v6 = [
            "::1",
            "fe80::1",
            "fc00::1",
            "::ffff:127.0.0.1",  # IPv4-mapped IPv6
            "::ffff:192.168.1.1",
        ]
        for ip_str in unsafe_v6:
            ip = ipaddress.ip_address(ip_str)
            assert not is_ip_safe(ip), f"IPv6 {ip_str} should be marked unsafe"

    def test_allows_public_ip(self):
        public_ips = [
            "8.8.8.8",
            "1.1.1.1",
            "142.250.190.46",
            "2607:f8b0:4005:805::200e",
        ]
        for ip_str in public_ips:
            ip = ipaddress.ip_address(ip_str)
            assert is_ip_safe(ip), f"Public IP {ip_str} should be marked safe"

    def test_rejects_disallowed_schemes(self):
        disallowed = [
            "file:///etc/passwd",
            "gopher://127.0.0.1:70",
            "ftp://files.example.com",
            "dict://127.0.0.1:11211",
        ]
        for url in disallowed:
            with pytest.raises(SSRFProtectionError, match="Unsupported URL scheme"):
                validate_url(url)

    def test_rejects_embedded_credentials(self):
        with pytest.raises(SSRFProtectionError, match="Embedded userinfo"):
            validate_url("https://admin:secret@example.com/test")

    def test_rejects_direct_private_ip_literal(self):
        with pytest.raises(SSRFProtectionError, match="Direct connection to private/restricted IP"):
            validate_url("http://127.0.0.1:8080/admin")
        with pytest.raises(SSRFProtectionError, match="Direct connection to private/restricted IP"):
            validate_url("http://192.168.1.50/metrics")

    @pytest.mark.asyncio
    async def test_redirect_to_private_ip_is_blocked(self):
        """Simulate a public URL that returns a 302 redirecting to an internal IP (SSRF via redirect)."""
        redirect_response = MagicMock(spec=httpx.Response)
        redirect_response.status_code = 302
        redirect_response.headers = {"Location": "http://127.0.0.1:8080/internal-api"}
        redirect_response.aclose = AsyncMock()

        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send, \
             patch("app.services.extraction.ssrf.validate_url") as mock_val:
            # First call validates initial URL; second call validates redirect target
            def side_effect(url):
                if "127.0.0.1" in url:
                    raise SSRFProtectionError("Direct connection to private/restricted IP '127.0.0.1' is blocked")
                return None

            mock_val.side_effect = side_effect
            mock_send.return_value = redirect_response

            with pytest.raises(SSRFProtectionError, match="Direct connection to private/restricted IP '127.0.0.1' is blocked"):
                await fetch_url_ssrf_safe("http://public-server.com/redirect-me")

    @pytest.mark.asyncio
    async def test_url_download_size_limit_content_length_aborts(self):
        """Content-Length header exceeding MAX_URL_DOWNLOAD_BYTES immediately aborts."""
        huge_response = MagicMock(spec=httpx.Response)
        huge_response.status_code = 200
        huge_response.headers = {"Content-Length": str(MAX_URL_DOWNLOAD_BYTES + 5000)}
        huge_response.aclose = AsyncMock()

        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send, \
             patch("app.services.extraction.ssrf.validate_url"):
            mock_send.return_value = huge_response
            with pytest.raises(StorageError, match="exceeds maximum limit"):
                await fetch_url_ssrf_safe("https://example.com/oversized.zip")

    @pytest.mark.asyncio
    async def test_url_download_size_limit_streamed_bytes_aborts(self):
        """Streaming chunk download that exceeds max_body_bytes aborts with StorageError."""
        stream_resp = MagicMock(spec=httpx.Response)
        stream_resp.status_code = 200
        stream_resp.headers = {}
        stream_resp.aclose = AsyncMock()

        async def chunk_generator():
            yield b"x" * 600
            yield b"y" * 600

        stream_resp.aiter_bytes = MagicMock(return_value=chunk_generator())

        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send, \
             patch("app.services.extraction.ssrf.validate_url"):
            mock_send.return_value = stream_resp
            with pytest.raises(StorageError, match="exceeded maximum allowed download size"):
                await fetch_url_ssrf_safe("https://example.com/chunked-bomb", max_body_bytes=1000)

    @pytest.mark.asyncio
    async def test_redirect_loop_exceeds_max_hops_aborts(self):
        """More than max_redirects hops raises SSRFProtectionError."""
        def make_redirect_resp(target):
            resp = MagicMock(spec=httpx.Response)
            resp.status_code = 302
            resp.headers = {"Location": target}
            resp.aclose = AsyncMock()
            return resp

        with patch("httpx.AsyncClient.send", new_callable=AsyncMock) as mock_send, \
             patch("app.services.extraction.ssrf.validate_url"):
            mock_send.side_effect = [
                make_redirect_resp(f"https://example.com/hop{i}") for i in range(1, 10)
            ]
            with pytest.raises(SSRFProtectionError, match="Exceeded maximum allowed redirects"):
                await fetch_url_ssrf_safe("https://example.com/hop0", max_redirects=5)


class TestVersionedDeduplication:
    """Test suite for source versioned deduplication and caching."""

    def test_deduplication_returns_cached_source(self, tmp_path):
        db_file = tmp_path / "dedup.db"
        init_db(db_file)
        service = SourceService(db_path=str(db_file), storage=StorageService(tmp_path))
        content = b"Exact identical source bytes for testing"

        # First registration
        source1 = service.register_file_source(
            filename="document.txt",
            content=content,
            mime_type="text/plain",
            project_id=None,
            metadata={"extraction_version": EXTRACTION_VERSION},
        )

        # Second registration with identical content and matching extraction_version
        source2 = service.register_file_source(
            filename="document.txt",
            content=content,
            mime_type="text/plain",
            project_id=None,
            metadata={"extraction_version": EXTRACTION_VERSION},
        )

        # Must return identical source ID without duplicate storage
        assert source1.id == source2.id
        assert source1.content_hash == source2.content_hash

    def test_content_mutation_creates_new_source(self, tmp_path):
        db_file = tmp_path / "dedup.db"
        init_db(db_file)
        service = SourceService(db_path=str(db_file), storage=StorageService(tmp_path))

        source1 = service.register_file_source(
            filename="report.txt",
            content=b"Original content v1",
            mime_type="text/plain",
        )
        source2 = service.register_file_source(
            filename="report.txt",
            content=b"Original content v2 (mutated)",
            mime_type="text/plain",
        )

        assert source1.id != source2.id
        assert source1.content_hash != source2.content_hash

    def test_versioned_deduplication_model_and_config_mutation(self, tmp_path):
        """Mutating model_id or config_hash must invalidate cache and create fresh source."""
        db_file = tmp_path / "dedup_model.db"
        init_db(db_file)
        service = SourceService(db_path=str(db_file), storage=StorageService(tmp_path))
        content = b"Configurable analysis data"

        source_base = service.register_file_source(
            filename="data.txt",
            content=content,
            mime_type="text/plain",
            metadata={"model_id": "gemini-3.5-flash-lite", "config_hash": "cfg_v1"},
        )

        # Same content, different model_id -> new source entity created
        source_model_diff = service.register_file_source(
            filename="data.txt",
            content=content,
            mime_type="text/plain",
            metadata={"model_id": "gemini-3.1-flash-lite", "config_hash": "cfg_v1"},
        )
        assert source_model_diff.id != source_base.id
        assert source_model_diff.metadata["composite_cache_key"] != source_base.metadata["composite_cache_key"]

        # Same content, different config_hash -> new source entity created
        source_cfg_diff = service.register_file_source(
            filename="data.txt",
            content=content,
            mime_type="text/plain",
            metadata={"model_id": "gemini-3.5-flash-lite", "config_hash": "cfg_v2"},
        )
        assert source_cfg_diff.id != source_base.id
        assert source_cfg_diff.metadata["composite_cache_key"] != source_base.metadata["composite_cache_key"]


class TestUrlIngestionEndpoint:
    """Test API endpoint POST /api/v1/sources/url."""

    def test_url_ingestion_api(self, client):
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = b"<html><head><title>Test Article</title></head><body><h1>Article Title</h1><p>Article body content.</p></body></html>"
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        with patch("app.services.source_service.fetch_url_ssrf_safe", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response

            payload = {"url": "https://example.com/tech-news"}
            res = client.post("/api/v1/sources/url", json=payload)
            assert res.status_code == 201
            data = res.json()
            assert data["name"] == "tech-news.html"
            assert data["mime_type"] == "text/html"
            assert data["metadata"]["source_url"] == "https://example.com/tech-news"
            assert data["metadata"]["http_status"] == 200


class TestLightweightExtractionApi:
    """Test suite for lightweight POST /extract and full GET /extracted endpoints."""

    def test_lightweight_extract_endpoint_and_full_extracted_endpoint(self, client):
        # 1. Register a text source
        text_payload = {
            "name": "architecture_overview.md",
            "text": "# Architecture\n\nHigh-level system design overview.\n\n## Subsystems\n\n- Ingestion\n- Storage\n",
        }
        create_res = client.post("/api/v1/sources/text", json=text_payload)
        assert create_res.status_code == 201
        source_id = create_res.json()["id"]

        # 2. First extract request: must return lightweight summary response with cache_hit=False
        extract_res1 = client.post(f"/api/v1/sources/{source_id}/extract")
        assert extract_res1.status_code == 200
        data1 = extract_res1.json()

        assert data1["source_id"] == source_id
        assert data1["extraction_id"] == f"ext_{source_id}"
        assert data1["status"] == "completed"
        assert data1["cache_hit"] is False
        assert "metrics" in data1
        assert data1["metrics"]["heading_count"] == 2
        assert "summary" in data1

        # 3. Second extract request: must return cached summary with cache_hit=True
        extract_res2 = client.post(f"/api/v1/sources/{source_id}/extract")
        assert extract_res2.status_code == 200
        data2 = extract_res2.json()
        assert data2["cache_hit"] is True

        # 4. Detail request: GET /extracted retrieves full ExtractedDocument with all headings/paragraphs
        detail_res = client.get(f"/api/v1/sources/{source_id}/extracted")
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert detail_data["source_id"] == source_id
        assert len(detail_data["headings"]) == 2
        assert detail_data["headings"][0]["text"] == "Architecture"
        assert "raw_text" in detail_data
