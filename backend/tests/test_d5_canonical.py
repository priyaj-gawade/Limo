"""Unit and integration tests for Phase D5.4: Understanding & Approved Canonicalization Pipeline.

Tests all 4 MUST-FIX items:
1. EvidenceGuard is non-destructive (flags unverified facts without deleting them).
2. Multi-anchor evidence validation (inspects section, page/timestamp, or table anchor first).
3. Controlled deterministic canonical hashing (same input + same config -> identical SHA-256).
4. Local regex extraction treated as candidate extraction, not truth.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from app.agent.llm.models import LLMResponse
from app.main import app
from app.models.content import (
    CanonicalClaim,
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEntity,
    CanonicalEvent,
    CanonicalFact,
    CanonicalIntent,
)
from app.models.enums import SourceType
from app.services.canonical.guards import ConsistencyGuard, EvidenceGuard, PydanticGuard
from app.services.canonical.local_extractor import LocalStructuredExtractor
from app.services.canonical.service import (
    CANONICALIZATION_VERSION,
    DEFAULT_CONFIG_HASH,
    CanonicalService,
    compute_canonical_hash,
)
from app.services.normalization.models import (
    NormalizedDocument,
    NormalizedSection,
    NormalizedTable,
)


@pytest.fixture
def sample_norm_doc():
    return NormalizedDocument(
        source_id="src_test_canonical_01",
        source_name="incident_briefing.pdf",
        source_type=SourceType.FILE,
        mime_type="application/pdf",
        sections=[
            NormalizedSection(
                title="Executive Overview",
                level=1,
                content="On 2026-04-15, telemetry nodes detected unauthorized buffer alterations. Revenue impact is estimated at $2.4M across Q2 2026.",
                page_number=1,
            ),
            NormalizedSection(
                title="Technical Remediation",
                level=2,
                content="Core gateway latency dropped to 45ms after deploying emergency patch v1.4.2. CyberDefend systems verified 99.8% traffic integrity.",
                page_number=2,
            ),
        ],
        tables=[
            NormalizedTable(
                name="SLA Metrics",
                headers=["Service", "Target Latency", "Observed Latency"],
                rows=[
                    ["Gateway", "50ms", "45ms"],
                    ["Auth Service", "20ms", "18ms"],
                ],
                source_reference="Page 2",
            )
        ],
        raw_text=(
            "Executive Overview: On 2026-04-15, telemetry nodes detected unauthorized buffer alterations. "
            "Revenue impact is estimated at $2.4M across Q2 2026.\n\n"
            "Technical Remediation: Core gateway latency dropped to 45ms after deploying emergency patch v1.4.2. "
            "CyberDefend systems verified 99.8% traffic integrity."
        ),
    )


class TestLocalStructuredExtractor:
    """Test suite for candidate signal extraction (MUST-FIX #4: Candidates only)."""

    def test_extract_dates(self):
        extractor = LocalStructuredExtractor(enable_gliner=False)
        text = "Meeting on 2026-04-15 and follow-up on January 20, 2026. Target for Q3 2026 and FY27."
        dates = extractor.extract_dates(text)
        assert "2026-04-15" in dates
        assert "January 20, 2026" in dates
        assert "Q3 2026" in dates
        assert "FY27" in dates

    def test_extract_metrics_from_text_and_tables(self, sample_norm_doc):
        extractor = LocalStructuredExtractor(enable_gliner=False)
        metrics = extractor.extract_metrics(sample_norm_doc)
        values = [m["value"] for m in metrics]

        assert any("$2.4M" in v for v in values)
        assert any("45ms" in v for v in values)
        assert any("99.8%" in v for v in values)

    def test_extract_candidate_entities_avoids_stopwords(self, sample_norm_doc):
        extractor = LocalStructuredExtractor(enable_gliner=False)
        entities = extractor.extract_entities(sample_norm_doc)
        names = [e["name"] for e in entities]

        assert "CyberDefend" in names or any("CyberDefend" in n for n in names)
        # Ensure common stopwords like "The", "This" are not captured as entities
        assert "The" not in names
        assert "This" not in names


class TestDeterministicGuards:
    """Test suite for Pydantic, non-destructive Evidence, and Consistency guards."""

    def test_pydantic_guard_markdown_code_fence_stripping(self):
        raw_json_in_markdown = "```json\n{\n  \"title\": \"Security Briefing\",\n  \"context\": \"Context info\",\n  \"intent\": {\"primary_purpose\": \"Alert\", \"core_narrative\": \"Breach remediation\"}\n}\n```"
        data, err = PydanticGuard.parse_and_validate_json(raw_json_in_markdown)
        assert err is None
        assert data["title"] == "Security Briefing"

    def test_pydantic_guard_detects_malformed_json(self):
        malformed = "{\"title\": \"Broken JSON... missing braces"
        data, err = PydanticGuard.parse_and_validate_json(malformed)
        assert data is None
        assert "Invalid JSON syntax" in err

    def test_pydantic_guard_detects_missing_required_fields(self):
        incomplete = {"title": "Missing Intent"}
        data, err = PydanticGuard.validate_schema(incomplete)
        assert data is None
        assert "Missing required canonical fields" in err

    def test_evidence_guard_multi_anchor_matching(self, sample_norm_doc):
        """Verify multi-anchor check, non-destructive verification, and LLM confidence separation."""
        guard = EvidenceGuard()

        # Fact 1: Strongly supported in specific section anchor
        fact_strong = CanonicalFact(
            statement="Telemetry nodes detected unauthorized buffer alterations.",
            source_reference="Executive Overview",
            confidence=0.95,
        )
        checked_strong = guard.validate_fact(fact_strong, sample_norm_doc)
        # Model confidence is preserved as model assessment; evidence status/score recorded separately
        assert checked_strong.confidence == 0.95
        assert checked_strong.evidence_status == "verified"
        assert checked_strong.evidence_score >= 0.85

        # Fact 2: Paraphrased fact with partial overlap -> flag as weak/unverified, NEVER delete, DO NOT touch LLM confidence
        fact_paraphrased = CanonicalFact(
            statement="Financial losses were projected around two million dollars.",
            source_reference="Executive Overview",
            confidence=0.90,
        )
        checked_para = guard.validate_fact(fact_paraphrased, sample_norm_doc)
        assert checked_para.statement == fact_paraphrased.statement
        assert checked_para.confidence == 0.90  # Untouched LLM confidence!
        assert checked_para.evidence_status in ["weak", "unverified"]
        assert checked_para.evidence_score is not None

        # Fact 3: Fact supported by table cell anchor
        fact_table = CanonicalFact(
            statement="Gateway latency observed reached 45ms.",
            source_reference="SLA Metrics",
            confidence=0.99,
        )
        checked_table = guard.validate_fact(fact_table, sample_norm_doc)
        assert checked_table.confidence == 0.99
        assert checked_table.evidence_status == "verified"
        assert checked_table.evidence_score >= 0.85

    def test_consistency_guard_preserves_event_order_and_reports_chronology(self, sample_norm_doc):
        """Verify events preserve original source order and chronology check is a separate diagnostic."""
        guard = ConsistencyGuard()

        events = [
            CanonicalEvent(title="Later event", timestamp_desc="2026-05-01"),
            CanonicalEvent(title="Earlier event", timestamp_desc="2026-04-15"),
            CanonicalEvent(title="Undated milestone", timestamp_desc=None),
        ]
        preserved_events, chronology_report = guard.validate_events(events)
        # Original order is preserved
        assert preserved_events[0].title == "Later event"
        assert preserved_events[1].title == "Earlier event"
        assert preserved_events[2].title == "Undated milestone"
        # Chronology check is a separate diagnostic report
        assert chronology_report["is_chronological"] is False
        assert chronology_report["total_events"] == 3

    def test_consistency_guard_strong_entity_deduplication(self):
        """Verify entity deduplication uses strong contextual/alias matching and avoids false merges."""
        guard = ConsistencyGuard()

        # Case 1: Same entity with shared context and alias -> merged
        entities_matching = [
            CanonicalEntity(name="CyberDefend", category="System", description="Endpoint security platform", relevance_score=0.8),
            CanonicalEntity(name="CyberDefend", category="System", description=None, relevance_score=0.95),
        ]
        deduped = guard.deduplicate_entities(entities_matching)
        assert len(deduped) == 1
        assert deduped[0].relevance_score == 0.95
        assert deduped[0].description == "Endpoint security platform"

        # Case 2: Entities sharing a common name but distinctly different contexts/references -> NOT merged
        entities_conflicting = [
            CanonicalEntity(name="Phoenix", category="System", description="Main server cluster in US-East", source_reference="infra.docx", relevance_score=0.8),
            CanonicalEntity(name="Phoenix", category="System", description="Autonomous drone vehicle platform", source_reference="hardware.pdf", relevance_score=0.85),
        ]
        deduped_conflicting = guard.deduplicate_entities(entities_conflicting)
        assert len(deduped_conflicting) == 2


class TestCanonicalServiceExecution:
    """Test suite for CanonicalService orchestration, bounded repair loop, and hashing."""

    @pytest.mark.asyncio
    async def test_bounded_repair_loop_recovers_from_syntax_error(self, sample_norm_doc):
        """Simulate model generating invalid JSON on attempt 1 and valid JSON on attempt 2."""
        mock_llm = MagicMock()

        valid_json = json.dumps({
            "title": "Remediation Report",
            "context": "Broad background on telemetry anomaly",
            "intent": {
                "primary_purpose": "Security alert",
                "target_audiences": ["Executives", "SRE"],
                "core_narrative": "Telemetry patch applied successfully",
                "urgency_level": "Immediate",
            },
            "entities": [{"name": "CyberDefend", "category": "System", "description": "Security software", "relevance_score": 0.9}],
            "facts": [{"statement": "Patch v1.4.2 lowered latency to 45ms.", "source_reference": "Technical Remediation", "confidence": 1.0}],
            "claims": [{"claim": "Traffic integrity is restored.", "claimant": "CyberDefend", "evidence": "99.8% integrity verified"}],
            "events": [{"title": "Patch applied", "timestamp_desc": "2026-04-15", "significance": "Remediation"}],
            "data_points": [{"metric": "Latency", "value": "45ms", "unit": "ms", "context": "Gateway"}],
            "recommendations": ["Maintain monitoring"],
            "references": [{"citation_key": "[REF-1]", "title": "incident_briefing.pdf"}],
        })

        # Attempt 1: Invalid JSON; Attempt 2: Valid JSON
        mock_llm.generate = AsyncMock(
            side_effect=[
                LLMResponse(text="INVALID { NON-JSON ...", input_tokens=100, output_tokens=20),
                LLMResponse(text=valid_json, input_tokens=150, output_tokens=250),
            ]
        )

        service = CanonicalService(llm_manager=mock_llm)
        canonical = await service.canonicalize(sample_norm_doc)

        assert isinstance(canonical, CanonicalContent)
        assert canonical.title == "Remediation Report"
        assert len(canonical.facts) == 1
        # Bounded repair loop must have attempted twice
        assert mock_llm.generate.call_count == 2

    def test_deterministic_canonical_hash_stability(self):
        """MUST-FIX #3: Same canonical data + same configuration produces exact bit-for-bit identical SHA-256."""
        data_a = {
            "title": "Deterministic Test",
            "context": "Context statement",
            "intent": {"primary_purpose": "Verification", "core_narrative": "Consistent hashing"},
            "entities": [{"name": "Alpha"}, {"name": "Beta"}],
            "facts": [{"statement": "Fact 1"}, {"statement": "Fact 2"}],
            "claims": [],
            "events": [],
            "data_points": [{"metric": "Uptime", "value": "99.9%"}],
            "recommendations": ["Replicate"],
            "references": [],
        }

        # Entities in different order in data_b: sorting in hash computation ensures stability
        data_b = {
            "title": "Deterministic Test",
            "context": "Context statement",
            "intent": {"primary_purpose": "Verification", "core_narrative": "Consistent hashing"},
            "entities": [{"name": "Beta"}, {"name": "Alpha"}],
            "facts": [{"statement": "Fact 2"}, {"statement": "Fact 1"}],
            "claims": [],
            "events": [],
            "data_points": [{"metric": "Uptime", "value": "99.9%"}],
            "recommendations": ["Replicate"],
            "references": [],
        }

        hash_a = compute_canonical_hash(data_a, canonicalization_version="ccm_v1.0.0", model_id="test_model", config_hash="cfg_01")
        hash_b = compute_canonical_hash(data_b, canonicalization_version="ccm_v1.0.0", model_id="test_model", config_hash="cfg_01")

        assert hash_a == hash_b
        assert len(hash_a) == 64

        # Changing model_id or config_hash must change the hash
        hash_diff_model = compute_canonical_hash(data_a, canonicalization_version="ccm_v1.0.0", model_id="different_model", config_hash="cfg_01")
        assert hash_a != hash_diff_model


class TestCanonicalApiEndpoints:
    """Test suite for POST /canonicalize and GET /canonical REST endpoints."""

    def test_canonical_api_flow(self):
        client = TestClient(app)

        # 1. Ingest text source
        text_payload = {
            "name": "incident_summary.md",
            "text": "# Security Alert\n\nUnauthorized network probing detected on 2026-03-01.",
        }
        res_src = client.post("/api/v1/sources/text", json=text_payload)
        assert res_src.status_code == 201
        source_id = res_src.json()["id"]

        valid_canonical_json = json.dumps({
            "title": "Security Alert Synthesis",
            "context": "Network probing detected",
            "intent": {
                "primary_purpose": "Incident notification",
                "target_audiences": ["SecOps"],
                "core_narrative": "Unauthorized probing investigated",
                "urgency_level": "High",
            },
            "entities": [{"name": "Network", "category": "Infrastructure", "description": "Probed gateway", "relevance_score": 1.0}],
            "facts": [{"statement": "Probing detected on 2026-03-01.", "source_reference": "Security Alert", "confidence": 1.0}],
            "claims": [],
            "events": [{"title": "Probing detected", "timestamp_desc": "2026-03-01", "significance": "Initial alert"}],
            "data_points": [],
            "recommendations": ["Audit firewall rules"],
            "references": [{"citation_key": "[REF-1]", "title": "incident_summary.md"}],
        })

        mock_llm_response = LLMResponse(text=valid_canonical_json, input_tokens=100, output_tokens=200)

        with patch("app.agent.llm.manager.llm_provider_manager.generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = mock_llm_response

            # 2. Call POST /canonicalize
            res_canon = client.post(f"/api/v1/sources/{source_id}/canonicalize")
            assert res_canon.status_code == 200
            data = res_canon.json()

            assert data["id"].startswith("can_")
            assert data["title"] == "Security Alert Synthesis"
            assert len(data["facts"]) == 1
            assert len(data["content_hash"]) == 64

            # 3. Call GET /canonical to retrieve persisted canonical content
            res_get = client.get(f"/api/v1/sources/{source_id}/canonical")
            assert res_get.status_code == 200
            get_data = res_get.json()
            assert get_data["id"] == data["id"]
            assert get_data["content_hash"] == data["content_hash"]
