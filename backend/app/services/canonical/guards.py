"""Deterministic Validation Guards for Canonicalization (Phase D5.4).

Adheres strictly to the 4 approved MUST-FIX items:
1. EvidenceGuard is non-destructive (flags unverified facts without deleting them).
2. Multi-anchor evidence validation (inspects section, page/timestamp, or table anchor first).
3. Consistency checks for chronology, data points, and entity deduplication.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ...models.content import (
    CanonicalClaim,
    CanonicalContent,
    CanonicalDataPoint,
    CanonicalEntity,
    CanonicalEvent,
    CanonicalFact,
    CanonicalIntent,
)
from ..normalization.models import NormalizedDocument, NormalizedSection, NormalizedTable
from ..retrieval.constants import STOPWORDS

logger = logging.getLogger("limo.services.canonical.guards")


class PydanticGuard:
    """Guard 3a: Schema validation and structured error formatting for repair loops."""

    @staticmethod
    def parse_and_validate_json(raw_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Parse raw model output into JSON dict, extracting from markdown code fences if present."""
        cleaned = raw_text.strip()
        # Strip markdown ```json ... ``` wrapper if present
        if cleaned.startswith("```"):
            fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
            if fence_match:
                cleaned = fence_match.group(1).strip()

        try:
            data = json.loads(cleaned)
            if not isinstance(data, dict):
                return None, f"Expected JSON root object/dict, got {type(data).__name__}"
            return data, None
        except json.JSONDecodeError as e:
            return None, f"Invalid JSON syntax at line {e.lineno}, col {e.colno}: {e.msg}"

    @staticmethod
    def validate_schema(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Verify required canonical schema keys exist and have correct types."""
        required_keys = ["title", "context", "intent"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            return None, f"Missing required canonical fields: {', '.join(missing)}"

        try:
            CanonicalIntent.model_validate(data.get("intent"))
        except Exception as e:
            return None, f"Invalid canonical intent schema: {e}"

        return data, None


class EvidenceGuard:
    """Guard 3b: Multi-anchor evidence validation with non-destructive verification."""

    @staticmethod
    def _extract_keywords(text: str) -> Set[str]:
        """Extract significant alphanumeric tokens for lexical grounding."""
        tokens = re.findall(r"\b[a-zA-Z0-9]{3,}\b", text.lower())
        return {t for t in tokens if t not in STOPWORDS}

    def _find_target_anchor_text(
        self,
        ref: Optional[str],
        doc: NormalizedDocument,
    ) -> Optional[str]:
        """Resolve specific target NormalizedSection or NormalizedTable matching ref anchor."""
        if not ref:
            return None

        clean_ref = ref.strip().lower()

        # 1. Match section title or timestamp
        for sec in doc.sections:
            if sec.title and sec.title.lower() in clean_ref:
                return sec.content
            if sec.timestamp and sec.timestamp in clean_ref:
                return sec.content
            if sec.page_number is not None and f"page {sec.page_number}" in clean_ref:
                return sec.content

        # 2. Match table name or headers
        for tbl in doc.tables:
            if tbl.name and tbl.name.lower() in clean_ref:
                rows_text = " ".join(" ".join(row) for row in tbl.rows)
                return f"{' '.join(tbl.headers)} {rows_text}"

        return None

    def validate_fact(self, fact: CanonicalFact, doc: NormalizedDocument) -> CanonicalFact:
        """Ground fact against target anchor or document text.
        
        Rules (User MUST-FIX):
        1. Model confidence (fact.confidence) is PRESERVED as the model's own assessment.
           Never overwrite LLM confidence with lexical overlap.
        2. Evidence status is recorded separately: 'verified', 'weak', or 'unverified'.
        3. Deterministic evidence score is recorded in fact.evidence_score.
        4. Inspect target anchor (section, page/timestamp, table) first before raw_text.
        """
        fact_tokens = self._extract_keywords(fact.statement)
        if not fact_tokens:
            fact.evidence_status = "unverified"
            fact.evidence_score = 0.0
            return fact

        # Target anchor text (section/page/table)
        anchor_text = self._find_target_anchor_text(fact.source_reference, doc)

        if anchor_text:
            anchor_tokens = self._extract_keywords(anchor_text)
            overlap = fact_tokens.intersection(anchor_tokens)
            ratio = len(overlap) / len(fact_tokens)

            if ratio >= 0.5 or any(phrase in anchor_text.lower() for phrase in [fact.statement.lower()[:30]]):
                # Strong evidence in targeted anchor
                fact.evidence_status = "verified"
                fact.evidence_score = round(max(ratio, 0.85), 2)
                return fact

        # Fall back to checking across the entire normalized document
        doc_tokens = self._extract_keywords(doc.raw_text)
        overlap = fact_tokens.intersection(doc_tokens)
        ratio = len(overlap) / len(fact_tokens) if fact_tokens else 0.0

        if ratio >= 0.6:
            fact.evidence_status = "verified"
            fact.evidence_score = round(ratio, 2)
        elif ratio >= 0.3:
            # Weak/paraphrased evidence: flag as weak, do NOT delete or touch LLM confidence
            fact.evidence_status = "weak"
            fact.evidence_score = round(ratio, 2)
        else:
            # No direct lexical evidence: flag as unverified, do NOT delete or touch LLM confidence
            fact.evidence_status = "unverified"
            fact.evidence_score = round(ratio, 2)

        return fact

    def validate_claim(self, claim: CanonicalClaim, doc: NormalizedDocument) -> CanonicalClaim:
        """Ground claim evidence against normalized source content."""
        if not claim.evidence:
            return claim

        evidence_tokens = self._extract_keywords(claim.evidence)
        if not evidence_tokens:
            return claim

        doc_tokens = self._extract_keywords(doc.raw_text)
        overlap = evidence_tokens.intersection(doc_tokens)
        ratio = len(overlap) / len(evidence_tokens) if evidence_tokens else 0.0

        if ratio < 0.3:
            logger.debug("Claim evidence '%s' has low lexical grounding (ratio=%.2f)", claim.evidence[:40], ratio)

        return claim

    def validate_canonical_evidence(
        self,
        canonical: CanonicalContent,
        doc: NormalizedDocument,
    ) -> CanonicalContent:
        """Execute non-destructive multi-anchor evidence validation across all facts and claims."""
        validated_facts = [self.validate_fact(f, doc) for f in canonical.facts]
        validated_claims = [self.validate_claim(c, doc) for c in canonical.claims]

        canonical.facts = validated_facts
        canonical.claims = validated_claims
        return canonical


class ConsistencyGuard:
    """Guard 3c: Deterministic consistency checks on events, data points, and entities."""

    @staticmethod
    def validate_events(events: List[CanonicalEvent]) -> Tuple[List[CanonicalEvent], Dict[str, Any]]:
        """Verify timeline event sanity; PRESERVE original source ordering.
        
        Rules (User MUST-FIX):
        - original_order is preserved. Do not blindly sort.
        - chronology_check is a separate validation result.
        """
        iso_dates = []
        for ev in events:
            if ev.timestamp_desc and re.match(r"^\d{4}-\d{2}-\d{2}", ev.timestamp_desc.strip()):
                iso_dates.append(ev.timestamp_desc.strip()[:10])

        is_chronological = True
        if len(iso_dates) > 1:
            is_chronological = all(iso_dates[i] <= iso_dates[i + 1] for i in range(len(iso_dates) - 1))

        chronology_report = {
            "is_chronological": is_chronological,
            "detected_iso_timestamps": iso_dates,
            "total_events": len(events),
        }
        return events, chronology_report

    @staticmethod
    def validate_data_points(
        data_points: List[CanonicalDataPoint],
        doc: NormalizedDocument,
    ) -> List[CanonicalDataPoint]:
        """Verify that quantitative metric values have sanity support in raw text or table cells."""
        validated: List[CanonicalDataPoint] = []
        raw_text = doc.raw_text

        for dp in data_points:
            # Check if numeric digits from value appear in source text or tables
            digits = "".join(c for c in dp.value if c.isdigit())
            if digits and (digits in raw_text or dp.value in raw_text):
                validated.append(dp)
            else:
                # If value is not directly in text, check tables
                found_in_table = False
                for tbl in doc.tables:
                    for row in tbl.rows:
                        if any(dp.value in cell for cell in row):
                            found_in_table = True
                            break
                    if found_in_table:
                        break

                if found_in_table or not digits:
                    validated.append(dp)
                else:
                    # Mark data point with context warning rather than dropping it
                    dp.context = f"{dp.context or ''} (value unconfirmed in text)".strip()
                    validated.append(dp)

        return validated

    @classmethod
    def deduplicate_entities(cls, entities: List[CanonicalEntity]) -> List[CanonicalEntity]:
        """Deduplicate entities with strong contextual matching.
        
        Rules (User MUST-FIX):
        - Do NOT merge solely by canonical name + category.
        - Require contextual/alias/source-reference evidence to merge.
        - If two entities have conflicting descriptions and different references, keep them separate.
        """
        deduped: List[CanonicalEntity] = []

        for candidate in entities:
            cand_name = candidate.name.strip().lower()
            cand_cat = candidate.category.strip().lower()
            cand_ref = (candidate.source_reference or "").strip().lower()
            cand_desc_tokens = EvidenceGuard._extract_keywords(candidate.description or "")
            cand_aliases = {a.strip().lower() for a in candidate.aliases}
            cand_aliases.add(cand_name)

            merged = False
            for existing in deduped:
                exist_name = existing.name.strip().lower()
                exist_cat = existing.category.strip().lower()
                exist_ref = (existing.source_reference or "").strip().lower()
                exist_aliases = {a.strip().lower() for a in existing.aliases}
                exist_aliases.add(exist_name)

                # Categories must match or be generic
                cat_compat = (cand_cat == exist_cat) or (cand_cat == "general") or (exist_cat == "general")
                if not cat_compat:
                    continue

                # Names or aliases must overlap
                name_overlap = bool(cand_aliases.intersection(exist_aliases))
                if not name_overlap:
                    continue

                # Contextual check:
                # 1. Matching source references
                ref_match = bool(cand_ref and exist_ref and cand_ref == exist_ref)
                # 2. Token overlap in description
                exist_desc_tokens = EvidenceGuard._extract_keywords(existing.description or "")
                desc_overlap = bool(cand_desc_tokens and exist_desc_tokens and cand_desc_tokens.intersection(exist_desc_tokens))
                # 3. No conflicting explicit descriptions
                no_desc_conflict = not (candidate.description and existing.description and not desc_overlap)

                if ref_match or desc_overlap or no_desc_conflict:
                    # Legitimate match: merge into existing
                    existing.relevance_score = max(existing.relevance_score, candidate.relevance_score)
                    if not existing.description and candidate.description:
                        existing.description = candidate.description
                    if not existing.source_reference and candidate.source_reference:
                        existing.source_reference = candidate.source_reference
                    # Combine aliases
                    combined_aliases = set(existing.aliases) | set(candidate.aliases)
                    if candidate.name != existing.name:
                        combined_aliases.add(candidate.name)
                    existing.aliases = sorted(list(combined_aliases))
                    merged = True
                    break

            if not merged:
                deduped.append(candidate)

        return deduped

    def validate_canonical_consistency(
        self,
        canonical: CanonicalContent,
        doc: NormalizedDocument,
    ) -> CanonicalContent:
        """Run all consistency checks on canonical content."""
        events, chronology_report = self.validate_events(canonical.events)
        canonical.events = events
        canonical.metadata["chronology_validation"] = chronology_report
        canonical.data_points = self.validate_data_points(canonical.data_points, doc)
        canonical.entities = self.deduplicate_entities(canonical.entities)
        return canonical
