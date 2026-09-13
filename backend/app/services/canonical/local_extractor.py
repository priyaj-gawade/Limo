"""Local Structured Extractor (Phase D5.4 Step 1).

Extracts advisory candidate signals (dates, metrics, entities) deterministically.
These candidates are strictly advisory cues passed to Gemini, NOT ground truth.
"""

import importlib.util
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..normalization.models import NormalizedDocument
from ..retrieval.constants import STOPWORDS

logger = logging.getLogger("limo.services.canonical.local_extractor")

DOC_EXCLUSIONS = frozenset({"table", "page", "section", "chapter", "document", "summary", "report"})


class LocalExtractionCandidates(BaseModel):
    """Advisory candidate signals extracted via local deterministic rules / optional GLiNER."""
    dates: List[str] = Field(default_factory=list, description="Extracted date candidates")
    metrics: List[Dict[str, str]] = Field(default_factory=list, description="Extracted numerical metric candidates")
    entities: List[Dict[str, str]] = Field(default_factory=list, description="Extracted entity candidates")


class LocalStructuredExtractor:
    """Extracts advisory candidate signals from NormalizedDocument using regex and heuristic rules."""

    def __init__(self, enable_gliner: bool = True):
        self.enable_gliner = enable_gliner
        self._gliner = None
        if enable_gliner and importlib.util.find_spec("gliner") is not None:
            try:
                from gliner import GLiNER
                self._gliner = GLiNER.from_pretrained("urchade/gliner_small-v2.1")
            except Exception as e:
                logger.debug("Optional GLiNER initialization skipped: %s", e)

    def extract_dates(self, text: str) -> List[str]:
        """Extract candidate dates using robust regex patterns."""
        patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",  # ISO 2026-09-12
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b",
            r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b",
            r"\bQ[1-4]\s+\d{4}\b",  # Q1 2026
            r"\bFY\s*(?:\d{4}|\d{2})\b",   # FY26, FY27, FY2026, or FY2027
        ]
        found = set()
        for pat in patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                found.add(m.group(0).strip())
        return sorted(list(found))

    def extract_metrics(self, doc: NormalizedDocument) -> List[Dict[str, str]]:
        """Extract numerical, financial, and percentage candidates from sections and tables."""
        metrics: List[Dict[str, str]] = []
        seen = set()

        # 1. Regex over section contents
        patterns = [
            # Currency: $1.2M, $500,000, $45.50
            (r"\$[\d,]+(?:\.\d+)?(?:\s*[MBKmbk])?", "currency"),
            # Percentages: 15%, 99.9%
            (r"\b\d+(?:\.\d+)?%", "percentage"),
            # Technical metrics: 50ms, 2000req/s, 100GB, 42 FTEs
            (r"\b\d+(?:\.\d+)?\s*(?:ms|seconds|minutes|hours|MB|GB|TB|req/s|TPS|FTEs|users|incidents)\b", "quantity"),
        ]

        for sec in doc.sections:
            for pat, kind in patterns:
                for match in re.finditer(pat, sec.content):
                    val = match.group(0).strip()
                    if val not in seen:
                        seen.add(val)
                        # Derive context window
                        start = max(0, match.start() - 30)
                        end = min(len(sec.content), match.end() + 30)
                        context_snippet = sec.content[start:end].replace("\n", " ").strip()
                        metrics.append({
                            "metric": f"{kind} candidate",
                            "value": val,
                            "context": context_snippet,
                            "source_reference": sec.title or (f"Page {sec.page_number}" if sec.page_number else "Document"),
                        })

        # 2. Extract structured metrics from table columns
        for tbl in doc.tables:
            if not tbl.headers or not tbl.rows:
                continue
            for col_idx, header in enumerate(tbl.headers):
                # Check if this column has numerical values
                num_count = 0
                for row in tbl.rows[:10]:
                    if col_idx < len(row) and re.search(r"\d", row[col_idx]):
                        num_count += 1
                if num_count >= 1:
                    for row in tbl.rows[:5]:
                        if col_idx < len(row):
                            val = row[col_idx].strip()
                            first_col = row[0] if row else ""
                            key = f"{header}:{val}:{first_col}"
                            if key not in seen and val:
                                seen.add(key)
                                metrics.append({
                                    "metric": f"{header} ({first_col})".strip(),
                                    "value": val,
                                    "context": f"Table: {tbl.name or 'Data'}",
                                    "source_reference": tbl.source_reference or "Table",
                                })

        return metrics[:25]  # Cap candidates to avoid prompt bloat

    def extract_entities(self, doc: NormalizedDocument) -> List[Dict[str, str]]:
        """Extract entity candidates using rule-based proper noun patterns or optional GLiNER."""
        entities: List[Dict[str, str]] = []
        seen = set()

        # Heuristic regex: Capitalized multi-word phrases or prominent identifiers
        pattern = r"\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z][a-zA-Z0-9]*)*\b"
        for sec in doc.sections:
            for match in re.finditer(pattern, sec.content):
                phrase = match.group(0).strip()
                words = phrase.split()
                if len(words) >= 1 and words[0].lower() not in STOPWORDS and words[0].lower() not in DOC_EXCLUSIONS and len(phrase) > 2:
                    if phrase.lower() not in seen:
                        seen.add(phrase.lower())
                        entities.append({
                            "name": phrase,
                            "category": "Candidate",
                            "source_reference": sec.title or (f"Page {sec.page_number}" if sec.page_number else "Document"),
                        })
                if len(entities) >= 20:
                    break
            if len(entities) >= 20:
                break

        return entities

    def extract_candidates(self, doc: NormalizedDocument) -> LocalExtractionCandidates:
        """Execute all local candidate extractors on NormalizedDocument."""
        dates = self.extract_dates(doc.raw_text)
        metrics = self.extract_metrics(doc)
        entities = self.extract_entities(doc)

        logger.debug(
            "Extracted local candidates for '%s': %d dates, %d metrics, %d entities",
            doc.source_name,
            len(dates),
            len(metrics),
            len(entities),
        )

        return LocalExtractionCandidates(
            dates=dates,
            metrics=metrics,
            entities=entities,
        )


local_structured_extractor = LocalStructuredExtractor()
