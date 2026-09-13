"""Unit tests for Native Output Adapters (Phase D6.3).

Verifies:
- NativeMarkdownAdapter: Physical .md file, data points table, citations, exact SHA-256
- NativeHtmlAdapter: Physical .html file, valid HTML5 structure, embedded CSS styling
- NativeSocialAdapter (LinkedIn): Hook, bulleted takeaways, hashtags, strictly grounded in canonical
- NativeSocialAdapter (Twitter): Strict <= 280-char limit per tweet, valid thread JSON
- NativeInfographicAdapter: Standalone valid vector SVG (1200x800), well-formed XML
"""

from datetime import datetime, timezone
import json
import xml.etree.ElementTree as ET
import pytest

from app.models.content import (
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEntity,
    CanonicalFact,
    CanonicalIntent,
    CanonicalReference,
)
from app.models.enums import OutputFormat
from app.models.generation_config import GenerationConfig
from app.models.transformation import EngineRoute, EngineType, PlannedDeliverable
from app.services.artifact_service import artifact_service
from app.services.project_service import project_service
from app.services.transformation.adapters.infographic_adapter import NativeInfographicAdapter
from app.services.transformation.adapters.markdown_adapter import (
    NativeHtmlAdapter,
    NativeMarkdownAdapter,
)
from app.services.transformation.adapters.social_adapter import NativeSocialAdapter
from app.storage.service import storage_service


@pytest.fixture
def test_context():
    """Setup project, storage, and grounded CanonicalContent."""
    proj = project_service.create_project("D6.3 Adapters Project")

    canonical = CanonicalContent(
        source_ids=["src_adapter_001"],
        title="Zero-Trust Edge Security Assessment",
        context="Comprehensive architectural audit of perimeter telemetry devices across enterprise cloud regions.",
        intent=CanonicalIntent(
            primary_purpose="Educate engineering directors on zero-trust migration requirements",
            target_audiences=["Security Architects", "DevOps Directors"],
            core_narrative="Perimeter gateways must transition from implicit trust to certificate-bound mutual TLS.",
        ),
        entities=[
            CanonicalEntity(name="Envoy Proxy", category="System"),
            CanonicalEntity(name="Zero-Trust Architecture", category="Framework"),
        ],
        facts=[
            CanonicalFact(
                statement="Legacy edge nodes use static API tokens that bypass mutual TLS.",
                confidence=0.96,
                evidence_status="verified",
                source_reference="Audit Report Page 12",
            ),
            CanonicalFact(
                statement="Credential leakage was identified in 4 staging environments.",
                confidence=0.88,
                evidence_status="weak",
                source_reference="Incident Log 441",
            ),
        ],
        data_points=[
            CanonicalDataPoint(metric="Vulnerable Endpoints", value="512", unit="endpoints", context="Staging & Prod"),
            CanonicalDataPoint(metric="Mean Time to Detection", value="4.2", unit="hours", context="Q3 benchmark"),
        ],
        recommendations=[
            "Revoke all legacy static API tokens within 7 days.",
            "Enforce SPIFFE/SPIRE workload identities globally.",
        ],
        references=[
            CanonicalReference(citation_key="[NIST-800-207]", title="Zero Trust Architecture Guidelines"),
        ],
        content_hash="b" * 64,
        created_at=datetime.now(timezone.utc),
    )

    return {"project": proj, "canonical": canonical}


def test_markdown_adapter_produces_real_file(test_context):
    """D6.3: NativeMarkdownAdapter creates a real .md file, registers Artifact, and validates SHA-256."""
    proj = test_context["project"]
    canonical = test_context["canonical"]

    deliv = PlannedDeliverable(
        deliverable_id="del_md_001",
        format=OutputFormat.MARKDOWN,
        title="Zero-Trust Assessment Executive Brief",
        route=EngineRoute(
            format=OutputFormat.MARKDOWN,
            engine_type=EngineType.NATIVE_MARKDOWN,
            target_extension=".md",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
        ),
    )
    cfg = GenerationConfig(audience="Security Architects", tone="authoritative")

    adapter = NativeMarkdownAdapter(storage=storage_service, artifact_svc=artifact_service)
    artifact = adapter.execute(
        canonical=canonical,
        deliverable=deliv,
        config=cfg,
        project_id=proj.id,
    )

    # 1. Verify Artifact record
    assert artifact.id.startswith("art_")
    assert artifact.file_format == ".md"
    assert artifact.title == "Zero-Trust Assessment Executive Brief"
    assert artifact.size_bytes > 0
    assert artifact.metadata["canonical_id"] == canonical.id
    assert artifact.metadata["canonical_hash"] == canonical.content_hash

    # 2. Verify physical file on disk
    disk_path = storage_service.safe_resolve(artifact.storage_ref)
    assert disk_path.is_file()
    file_bytes = disk_path.read_bytes()
    assert len(file_bytes) == artifact.size_bytes
    assert storage_service.compute_sha256(file_bytes) == artifact.content_hash

    # 3. Verify grounded content in Markdown text
    content_text = file_bytes.decode("utf-8")
    assert "# Zero-Trust Assessment Executive Brief" in content_text
    assert canonical.intent.core_narrative in content_text
    assert "Legacy edge nodes use static API tokens" in content_text
    assert "| Metric | Value | Unit | Context |" in content_text
    assert "Vulnerable Endpoints" in content_text
    assert "[NIST-800-207]" in content_text


def test_html_adapter_produces_real_file(test_context):
    """D6.3: NativeHtmlAdapter creates standalone, valid HTML5 with responsive CSS."""
    proj = test_context["project"]
    canonical = test_context["canonical"]

    deliv = PlannedDeliverable(
        deliverable_id="del_html_001",
        format=OutputFormat.HTML,
        title="Zero-Trust Migration Report",
        route=EngineRoute(
            format=OutputFormat.HTML,
            engine_type=EngineType.NATIVE_MARKDOWN,
            target_extension=".html",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
        ),
    )
    cfg = GenerationConfig()

    adapter = NativeHtmlAdapter(storage=storage_service, artifact_svc=artifact_service)
    artifact = adapter.execute(
        canonical=canonical,
        deliverable=deliv,
        config=cfg,
        project_id=proj.id,
    )

    # 1. Verify physical file
    disk_path = storage_service.safe_resolve(artifact.storage_ref)
    assert disk_path.is_file()
    file_bytes = disk_path.read_bytes()
    assert len(file_bytes) == artifact.size_bytes

    # 2. Verify HTML5 structure and styling
    html_text = file_bytes.decode("utf-8")
    assert "<!DOCTYPE html>" in html_text
    assert "<html" in html_text
    assert "<style>" in html_text
    assert "Zero-Trust Migration Report" in html_text
    assert "metric-card" in html_text
    assert "512" in html_text
    assert canonical.content_hash in html_text


def test_linkedin_adapter_produces_real_post(test_context):
    """D6.3: NativeSocialAdapter generates a hook-driven, grounded LinkedIn post draft."""
    proj = test_context["project"]
    canonical = test_context["canonical"]

    deliv = PlannedDeliverable(
        deliverable_id="del_linkedin_001",
        format=OutputFormat.LINKEDIN,
        title="Zero-Trust Edge Security Priorities",
        route=EngineRoute(
            format=OutputFormat.LINKEDIN,
            engine_type=EngineType.NATIVE_SOCIAL,
            target_extension=".md",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
        ),
    )
    cfg = GenerationConfig()

    adapter = NativeSocialAdapter(storage=storage_service, artifact_svc=artifact_service)
    artifact = adapter.execute(
        canonical=canonical,
        deliverable=deliv,
        config=cfg,
        project_id=proj.id,
    )

    disk_path = storage_service.safe_resolve(artifact.storage_ref)
    post_text = disk_path.read_text(encoding="utf-8")

    assert "Zero-Trust Edge Security Priorities" in post_text
    assert canonical.intent.core_narrative in post_text
    assert "Vulnerable Endpoints" in post_text
    assert "#Leadership" in post_text
    assert "#EnvoyProxy" in post_text or "#ZeroTrustArchitecture" in post_text


def test_twitter_adapter_strict_280_character_limit(test_context):
    """D6.3: NativeSocialAdapter generates an X/Twitter thread with strictly <= 280 chars per tweet."""
    proj = test_context["project"]
    canonical = test_context["canonical"]

    deliv = PlannedDeliverable(
        deliverable_id="del_twitter_001",
        format=OutputFormat.TWITTER,
        title="Zero-Trust Architecture Breakdown",
        route=EngineRoute(
            format=OutputFormat.TWITTER,
            engine_type=EngineType.NATIVE_SOCIAL,
            target_extension=".json",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
        ),
    )
    cfg = GenerationConfig()

    adapter = NativeSocialAdapter(storage=storage_service, artifact_svc=artifact_service)
    artifact = adapter.execute(
        canonical=canonical,
        deliverable=deliv,
        config=cfg,
        project_id=proj.id,
    )

    disk_path = storage_service.safe_resolve(artifact.storage_ref)
    thread_data = json.loads(disk_path.read_text(encoding="utf-8"))

    assert "tweets" in thread_data
    assert thread_data["total_tweets"] >= 3
    assert len(thread_data["tweets"]) == thread_data["total_tweets"]

    # Strictly check the 280-character boundary on EVERY single tweet
    for tweet in thread_data["tweets"]:
        assert len(tweet["text"]) <= 280, f"Tweet {tweet['tweet_number']} exceeded 280 characters: {len(tweet['text'])}"
        assert tweet["char_count"] == len(tweet["text"])
        assert f"/{thread_data['total_tweets']}" in tweet["text"]


def test_infographic_adapter_produces_valid_svg(test_context):
    """D6.3: NativeInfographicAdapter produces a valid, well-formed vector SVG infographic."""
    proj = test_context["project"]
    canonical = test_context["canonical"]

    deliv = PlannedDeliverable(
        deliverable_id="del_info_001",
        format=OutputFormat.INFOGRAPHIC,
        title="Zero-Trust Architecture Infographic",
        route=EngineRoute(
            format=OutputFormat.INFOGRAPHIC,
            engine_type=EngineType.NATIVE_INFOGRAPHIC,
            target_extension=".svg",
            is_implemented=True,
            target_phase="D6.3 (Native Adapters)",
        ),
    )
    cfg = GenerationConfig()

    adapter = NativeInfographicAdapter(storage=storage_service, artifact_svc=artifact_service)
    artifact = adapter.execute(
        canonical=canonical,
        deliverable=deliv,
        config=cfg,
        project_id=proj.id,
    )

    disk_path = storage_service.safe_resolve(artifact.storage_ref)
    svg_bytes = disk_path.read_bytes()

    # Verify well-formed XML parsing without syntax errors
    root = ET.fromstring(svg_bytes)
    assert root.tag.endswith("svg")
    assert root.attrib["viewBox"] == "0 0 1200 800"

    svg_text = svg_bytes.decode("utf-8")
    assert "Zero-Trust Architecture Infographic" in svg_text
    assert canonical.content_hash in svg_text
    assert "Vulnerable Endpoints" in svg_text or "512" in svg_text
