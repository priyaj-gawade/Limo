"""Canonicalization Service (Phase D5.4).

Deterministic business service implementing the approved 4-step canonicalization pipeline:
ExtractedDocument -> NormalizedDocument -> Local Candidates -> Gemini Structured Output ->
Deterministic Guards (Pydantic, Evidence, Consistency) -> SHA-256 Hash + SQLite Persistence.

Preserves the D4/D5 boundary: strictly a business service, NOT an autonomous agent loop.
Does NOT re-read raw source files; consumes already-extracted evidence.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ...agent.llm.manager import LLMProviderManager, llm_provider_manager
from ...config import settings
from ...core.ids import generate_canonical_id
from ...db.connection import get_connection
from ...db.repositories.job_repo import JobRepository
from ...db.repositories.source_repo import SourceRepository
from ...exceptions import StorageError
from ...models.content import (
    CanonicalClaim,
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEntity,
    CanonicalEvent,
    CanonicalFact,
    CanonicalIntent,
    CanonicalReference,
)
from ..normalization.models import NormalizedDocument
from .guards import ConsistencyGuard, EvidenceGuard, PydanticGuard
from .local_extractor import LocalExtractionCandidates, LocalStructuredExtractor, local_structured_extractor

logger = logging.getLogger("limo.services.canonical")

CANONICALIZATION_VERSION = "ccm_v1.0.0"
DEFAULT_CONFIG_HASH = hashlib.sha256(b"limo_default_canonical_config_v1").hexdigest()[:16]


def compute_canonical_hash(
    canonical_dict: Dict[str, Any],
    canonicalization_version: str = CANONICALIZATION_VERSION,
    model_id: str = "default",
    config_hash: str = DEFAULT_CONFIG_HASH,
) -> str:
    """Compute deterministic cryptographic SHA-256 hash over canonical content.
    
    MUST-FIX #3: Includes canonicalization configuration, model_id, and normalized content.
    Excludes non-deterministic runtime fields (id, created_at, content_hash).
    """
    stable_payload = {
        "canonicalization_version": str(canonicalization_version),
        "model_id": str(model_id),
        "config_hash": str(config_hash),
        "title": canonical_dict.get("title", ""),
        "context": canonical_dict.get("context", ""),
        "intent": canonical_dict.get("intent", {}),
        "entities": sorted(canonical_dict.get("entities", []), key=lambda e: e.get("name", "")),
        "facts": sorted(canonical_dict.get("facts", []), key=lambda f: f.get("statement", "")),
        "claims": sorted(canonical_dict.get("claims", []), key=lambda c: c.get("claim", "")),
        "events": sorted(canonical_dict.get("events", []), key=lambda ev: ev.get("title", "")),
        "data_points": sorted(canonical_dict.get("data_points", []), key=lambda dp: dp.get("metric", "")),
        "recommendations": canonical_dict.get("recommendations", []),
        "references": canonical_dict.get("references", []),
    }
    encoded = json.dumps(stable_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class CanonicalService:
    """Deterministic canonicalization service executing the approved D5.4 pipeline."""

    def __init__(
        self,
        llm_manager: Optional[LLMProviderManager] = None,
        db_path: Optional[str] = None,
        local_extractor: Optional[LocalStructuredExtractor] = None,
    ):
        self.llm_manager = llm_manager or llm_provider_manager
        self.db_path = str(db_path or settings.db_path)
        self.local_extractor = local_extractor or local_structured_extractor
        self.pydantic_guard = PydanticGuard()
        self.evidence_guard = EvidenceGuard()
        self.consistency_guard = ConsistencyGuard()

    def _build_prompt(
        self,
        doc: NormalizedDocument,
        candidates: LocalExtractionCandidates,
    ) -> Tuple[str, str]:
        """Construct system instruction and grounded prompt incorporating candidate signals."""
        system_instruction = (
            "You are Limo's Grounded Canonicalization Engine. Your mission is to convert normalized "
            "source evidence into the structured Canonical Content Model (CCM). "
            "You MUST adhere to strict grounding: only extract facts, metrics, claims, and entities "
            "that are genuinely supported by the provided source document. Do NOT hallucinate. "
            "You are provided with advisory candidate signals (dates, metrics, entities) extracted by local rules; "
            "treat them strictly as helpful hints and candidate cues, not ground truth. "
            "Return a valid JSON object matching the exact CanonicalContent schema."
        )

        # Build clean section summary for context
        sections_overview = []
        for s in doc.sections[:30]:
            anchor = f"Page {s.page_number}" if s.page_number else (f"[{s.timestamp}]" if s.timestamp else "")
            sec_header = f"[{anchor}] {s.title}" if anchor and s.title else (s.title or anchor or "Section")
            sections_overview.append(f"### {sec_header}\n{s.content[:500]}")

        prompt = (
            f"Source Name: {doc.source_name}\n"
            f"Source Type: {doc.source_type.value}\n"
            f"MIME Type: {doc.mime_type}\n\n"
            f"--- ADVISORY CANDIDATE SIGNALS (USE AS HINTS, NOT ABSOLUTE TRUTH) ---\n"
            f"Candidate Dates: {json.dumps(candidates.dates[:15])}\n"
            f"Candidate Metrics: {json.dumps(candidates.metrics[:15])}\n"
            f"Candidate Entities: {json.dumps(candidates.entities[:15])}\n\n"
            f"--- SOURCE DOCUMENT CONTENT ---\n"
            f"{doc.raw_text[:12000]}\n\n"
            f"--- REQUIRED OUTPUT SCHEMA (JSON) ---\n"
            f"Provide a single JSON object with these exact keys:\n"
            f"- 'title': Overall synthesis title (string)\n"
            f"- 'context': Broad situational background and environmental setting (string)\n"
            f"- 'intent': {{ 'primary_purpose': string, 'target_audiences': [string], 'core_narrative': string, 'urgency_level': string }}\n"
            f"- 'entities': [ {{ 'name': string, 'category': string, 'description': string, 'relevance_score': float (0.0-1.0) }} ]\n"
            f"- 'facts': [ {{ 'statement': string, 'source_reference': string, 'confidence': float (0.0-1.0) }} ]\n"
            f"- 'claims': [ {{ 'claim': string, 'claimant': string, 'evidence': string }} ]\n"
            f"- 'events': [ {{ 'title': string, 'timestamp_desc': string, 'significance': string }} ]\n"
            f"- 'data_points': [ {{ 'metric': string, 'value': string, 'unit': string, 'context': string }} ]\n"
            f"- 'recommendations': [ string ]\n"
            f"- 'references': [ {{ 'citation_key': string, 'title': string, 'uri_or_location': string }} ]\n"
        )

        return system_instruction, prompt

    async def canonicalize(
        self,
        norm_doc: NormalizedDocument,
        model_id: Optional[str] = None,
        config_hash: Optional[str] = None,
    ) -> CanonicalContent:
        """Execute approved 4-step canonicalization pipeline on a NormalizedDocument.
        
        Guarantees:
        1. Local structured candidate extraction.
        2. Gemini structured output request (temperature=0.0 for deterministic stability).
        3. Deterministic guards with bounded repair loop (max 2 retries).
        4. Multi-anchor non-destructive evidence validation.
        5. Consistency validation (chronology, metric sanity, entity deduplication).
        6. Deterministic SHA-256 hash calculation and SQLite persistence.
        """
        model_attr = getattr(self.llm_manager, "primary_model", "default")
        chosen_model = str(model_id or (model_attr if isinstance(model_attr, str) else "default"))
        chosen_config_hash = config_hash or DEFAULT_CONFIG_HASH

        # Step 1: Local Structured Extraction (Candidates, not absolute truth)
        candidates = self.local_extractor.extract_candidates(norm_doc)

        # Step 2: Formulate prompt & call Gemini Structured Output
        system_instruction, prompt = self._build_prompt(norm_doc, candidates)

        # Step 3a: Call LLM with Bounded Repair Loop (max 2 retries)
        max_repair_retries = 2
        raw_json_dict: Optional[Dict[str, Any]] = None
        last_error_msg = ""

        current_prompt = prompt
        for attempt in range(max_repair_retries + 1):
            logger.info(
                "Requesting canonical extraction for '%s' (attempt: %d/%d)",
                norm_doc.source_name,
                attempt + 1,
                max_repair_retries + 1,
            )
            response = await self.llm_manager.generate(
                prompt=current_prompt,
                system_instruction=system_instruction,
                temperature=0.0,  # Maximize deterministic stability
                response_mime_type="application/json",
            )

            parsed, err = self.pydantic_guard.parse_and_validate_json(response.text)
            if not err and parsed is not None:
                validated_data, schema_err = self.pydantic_guard.validate_schema(parsed)
                if not schema_err and validated_data is not None:
                    raw_json_dict = validated_data
                    break
                else:
                    last_error_msg = schema_err or "Schema validation failed"
            else:
                last_error_msg = err or "JSON decode failed"

            logger.warning("Canonical output schema validation failed (attempt %d): %s", attempt + 1, last_error_msg)
            # Feed exact validation error back for bounded repair
            current_prompt = (
                f"{prompt}\n\n"
                f"ATTENTION: Your previous response had a schema/formatting error:\n{last_error_msg}\n"
                f"Please fix the error and output valid JSON following the schema precisely."
            )

        if raw_json_dict is None:
            raise StorageError(f"Canonicalization failed after {max_repair_retries} repair retries: {last_error_msg}")

        # Step 3b: Construct CanonicalContent model
        canonical_id = generate_canonical_id()

        # Build sub-models safely
        intent_dict = raw_json_dict.get("intent", {})
        intent = CanonicalIntent(
            primary_purpose=intent_dict.get("primary_purpose", "Information synthesis"),
            target_audiences=intent_dict.get("target_audiences", []),
            core_narrative=intent_dict.get("core_narrative", norm_doc.source_name),
            urgency_level=intent_dict.get("urgency_level", "Informational"),
        )

        entities = [
            CanonicalEntity(
                name=e.get("name", "Unknown"),
                category=e.get("category", "General"),
                description=e.get("description"),
                relevance_score=float(e.get("relevance_score", 1.0)),
            )
            for e in raw_json_dict.get("entities", [])
            if e.get("name")
        ]

        facts = [
            CanonicalFact(
                statement=f.get("statement", ""),
                source_id=norm_doc.source_id,
                source_reference=f.get("source_reference"),
                confidence=float(f.get("confidence", 1.0)),
            )
            for f in raw_json_dict.get("facts", [])
            if f.get("statement")
        ]

        claims = [
            CanonicalClaim(
                claim=c.get("claim", ""),
                claimant=c.get("claimant"),
                evidence=c.get("evidence"),
            )
            for c in raw_json_dict.get("claims", [])
            if c.get("claim")
        ]

        events = [
            CanonicalEvent(
                title=ev.get("title", ""),
                timestamp_desc=ev.get("timestamp_desc"),
                significance=ev.get("significance"),
            )
            for ev in raw_json_dict.get("events", [])
            if ev.get("title")
        ]

        data_points = [
            CanonicalDataPoint(
                metric=dp.get("metric", ""),
                value=str(dp.get("value", "")),
                unit=dp.get("unit"),
                context=dp.get("context"),
            )
            for dp in raw_json_dict.get("data_points", [])
            if dp.get("metric") and dp.get("value")
        ]

        references = [
            CanonicalReference(
                citation_key=r.get("citation_key", f"[REF-{idx+1}]"),
                title=r.get("title", norm_doc.source_name),
                uri_or_location=r.get("uri_or_location"),
            )
            for idx, r in enumerate(raw_json_dict.get("references", []))
            if r.get("title")
        ]

        canonical = CanonicalContent(
            id=canonical_id,
            source_ids=[norm_doc.source_id],
            title=raw_json_dict.get("title", norm_doc.source_name),
            context=raw_json_dict.get("context", norm_doc.raw_text[:300]),
            intent=intent,
            entities=entities,
            facts=facts,
            claims=claims,
            events=events,
            data_points=data_points,
            recommendations=raw_json_dict.get("recommendations", []),
            references=references,
            content_hash="0" * 64,  # Temporary placeholder before hash calculation
            created_at=datetime.now(timezone.utc),
            metadata={
                "canonicalization_version": CANONICALIZATION_VERSION,
                "model_id": chosen_model,
                "config_hash": chosen_config_hash,
                "source_id": norm_doc.source_id,
            },
        )

        # Step 3c: Multi-Anchor Non-Destructive Evidence Validation (MUST-FIX #1 & #2)
        canonical = self.evidence_guard.validate_canonical_evidence(canonical, norm_doc)

        # Step 3d: Consistency Checks (MUST-FIX #4: Chronology, data points, entity dedup)
        canonical = self.consistency_guard.validate_canonical_consistency(canonical, norm_doc)

        # Step 4: Compute deterministic SHA-256 hash (MUST-FIX #3)
        raw_dict_for_hash = canonical.model_dump()
        canonical.content_hash = compute_canonical_hash(
            canonical_dict=raw_dict_for_hash,
            canonicalization_version=CANONICALIZATION_VERSION,
            model_id=chosen_model,
            config_hash=chosen_config_hash,
        )

        # Step 5: Persist to SQLite database
        try:
            with get_connection(self.db_path) as conn:
                JobRepository.save_canonical_content(conn, canonical)
                # Link to Source metadata
                source_record = SourceRepository.get_source(conn, norm_doc.source_id)
                if source_record:
                    updated_meta = {
                        **source_record.metadata,
                        "canonical_id": canonical.id,
                        "canonical_hash": canonical.content_hash,
                        "canonicalized_at": datetime.now(timezone.utc).isoformat(),
                    }
                    SourceRepository.update_source_metadata(conn, norm_doc.source_id, updated_meta)
        except Exception as e:
            logger.warning("Failed to persist CanonicalContent for '%s' to database: %s", norm_doc.source_id, e)

        return canonical

    def get_canonical_by_source_id(self, source_id: str) -> Optional[CanonicalContent]:
        """Retrieve CanonicalContent associated with a given Source ID."""
        with get_connection(self.db_path) as conn:
            # Query canonical_contents where source_ids_json contains source_id
            sql = """
                SELECT id FROM canonical_contents
                WHERE id IN (
                    SELECT json_extract(metadata_json, '$.canonical_id')
                    FROM sources
                    WHERE id = ?
                )
                LIMIT 1
            """
            row = conn.execute(sql, (source_id,)).fetchone()
            if row:
                return JobRepository.get_canonical_content(conn, row["id"])
            return None


canonical_service = CanonicalService()
