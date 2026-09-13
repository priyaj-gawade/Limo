"""Section-Aware Okapi BM25 Retriever with Pre-Indexing and Token Budgeting (Phase D5.5).

Implements:
- MUST-FIX #2: Builds and pre-indexes chunks once per NormalizedDocument. Multiple queries
  reuse the pre-computed inverted index and statistics without re-chunking.
- MUST-FIX #3: Configurable token budget slicing.
- MUST-FIX #4: Shared estimate_tokens heuristic from D4.2 context system.
- MUST-FIX #5: High-precision retrieval quality: title matching boosts, table row context,
  and page/timestamp anchor preservation.
"""

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

from ...agent.context import estimate_tokens
from ..normalization.models import NormalizedDocument, NormalizedSection, NormalizedTable
from .base import BaseRetriever
from .constants import STOPWORDS
from .models import RetrievalQuery, RetrievalResult, RetrievedChunk


def tokenize(text: str) -> List[str]:
    """Extract lowercase alphanumeric tokens, filtering single chars and stopwords."""
    tokens = re.findall(r"\b[a-zA-Z0-9_-]{2,}\b", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


class DocumentIndex:
    """Inverted index structure containing term frequencies and document lengths."""

    def __init__(self, doc: NormalizedDocument, k1: float = 1.5, b: float = 0.75):
        self.doc = doc
        self.k1 = k1
        self.b = b
        self.chunks: List[RetrievedChunk] = []
        self.tokenized_chunks: List[List[str]] = []
        self.chunk_lengths: List[int] = []
        self.avg_chunk_length: float = 0.0
        self.term_frequencies: List[Dict[str, int]] = []
        self.inverted_index: Dict[str, List[int]] = {}
        self.idf: Dict[str, float] = {}

        self._build_chunks(doc)
        self._build_index()

    def _build_chunks(self, doc: NormalizedDocument) -> None:
        """Segment NormalizedDocument sections and tables into grounded chunks."""
        chunk_idx = 0

        # 1. Chunk Sections
        for sec in doc.sections:
            content = (sec.content or "").strip()
            if not content:
                continue

            paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()] or [content]

            def emit_chunk(group: List[str]) -> None:
                nonlocal chunk_idx
                chunk_text = "\n\n".join(group)
                self.chunks.append(
                    RetrievedChunk(
                        chunk_id=f"{doc.source_id}_chunk_{chunk_idx}",
                        source_id=doc.source_id,
                        chunk_index=chunk_idx,
                        section_title=sec.title,
                        level=sec.level,
                        page_number=sec.page_number,
                        timestamp=sec.timestamp,
                        content=chunk_text,
                        estimated_tokens=estimate_tokens(chunk_text),
                    )
                )
                chunk_idx += 1

            current_group: List[str] = []
            current_len = 0
            for p in paragraphs:
                if current_len + len(p) > 1200 and current_group:
                    emit_chunk(current_group)
                    current_group = [p]
                    current_len = len(p)
                else:
                    current_group.append(p)
                    current_len += len(p)

            if current_group:
                emit_chunk(current_group)

        # 2. Chunk Tables (preserve table structure, headers, and name)
        for tbl in doc.tables:
            table_lines = []
            if tbl.name:
                table_lines.append(f"Table: {tbl.name}")
            if tbl.headers:
                table_lines.append(" | ".join(tbl.headers))
                table_lines.append("-" * 40)
            for row in tbl.rows:
                table_lines.append(" | ".join(str(c) for c in row))

            tbl_text = "\n".join(table_lines)
            chunk_id = f"{doc.source_id}_tbl_{chunk_idx}"
            self.chunks.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    source_id=doc.source_id,
                    chunk_index=chunk_idx,
                    section_title=tbl.name or "Tabular Data",
                    level=2,
                    page_number=None,
                    timestamp=None,
                    content=tbl_text,
                    estimated_tokens=estimate_tokens(tbl_text),
                    metadata={"source_reference": tbl.source_reference, "is_table": True},
                )
            )
            chunk_idx += 1

    def _build_index(self) -> None:
        """Tokenize chunks and calculate BM25 IDF and term frequency maps."""
        num_chunks = len(self.chunks)
        if num_chunks == 0:
            return

        inverted_map: Dict[str, List[int]] = defaultdict(list)
        total_length = 0

        for idx, chunk in enumerate(self.chunks):
            combined = f"{chunk.section_title or ''} {chunk.content}"
            tokens = tokenize(combined)
            self.tokenized_chunks.append(tokens)
            doc_len = len(tokens)
            self.chunk_lengths.append(doc_len)
            total_length += doc_len

            tf = Counter(tokens)
            self.term_frequencies.append(tf)

            for t in tf.keys():
                inverted_map[t].append(idx)

        self.inverted_index = dict(inverted_map)
        self.avg_chunk_length = total_length / num_chunks if num_chunks > 0 else 0.0

        for term, postings in self.inverted_index.items():
            doc_freq = len(postings)
            # Standard Okapi BM25 IDF with smoothing
            idf_val = math.log((num_chunks - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)
            self.idf[term] = max(0.01, idf_val)

    def score_query(self, query: str) -> List[Tuple[int, float]]:
        """Score all chunks against query terms using pre-indexed BM25 statistics."""
        q_tokens = tokenize(query)
        if not q_tokens or not self.chunks:
            return []

        scores: Dict[int, float] = {}

        for term in q_tokens:
            if term not in self.inverted_index:
                continue

            term_idf = self.idf.get(term, 0.0)
            postings = self.inverted_index[term]

            for chunk_idx in postings:
                tf = self.term_frequencies[chunk_idx].get(term, 0)
                doc_len = self.chunk_lengths[chunk_idx]

                # BM25 term weighting
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / (self.avg_chunk_length or 1.0)))
                bm25_score = term_idf * (numerator / denominator)

                # Quality boost: section title match
                chunk = self.chunks[chunk_idx]
                if chunk.section_title and term in chunk.section_title.lower():
                    bm25_score *= 1.35

                scores[chunk_idx] = scores.get(chunk_idx, 0.0) + bm25_score

        # Sort chunk indices by score descending
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)


class BM25Retriever(BaseRetriever):
    """Section-Aware BM25 Retriever maintaining pre-indexed document indices."""

    def __init__(self, default_budget_tokens: int = 2000):
        self._indices: Dict[str, DocumentIndex] = {}
        self.default_budget_tokens = default_budget_tokens

    def index_document(self, doc: NormalizedDocument) -> None:
        """Pre-index NormalizedDocument chunks once. Thread-safe cached index."""
        self._indices[doc.source_id] = DocumentIndex(doc)

    def has_index(self, source_id: str) -> bool:
        return source_id in self._indices

    def get_index(self, doc: NormalizedDocument) -> DocumentIndex:
        """Retrieve cached index or build once if not already indexed."""
        if doc.source_id not in self._indices:
            self.index_document(doc)
        return self._indices[doc.source_id]

    async def retrieve(
        self,
        query: RetrievalQuery,
        doc: Optional[NormalizedDocument] = None,
        max_tokens: Optional[int] = None,
    ) -> RetrievalResult:
        """Retrieve grounded, section-aware chunks strictly within token budget."""
        # Determine applicable indices
        indices_to_query: List[DocumentIndex] = []

        if doc is not None:
            indices_to_query.append(self.get_index(doc))
        elif query.source_ids:
            for sid in query.source_ids:
                if sid in self._indices:
                    indices_to_query.append(self._indices[sid])
        else:
            indices_to_query.extend(self._indices.values())

        if not indices_to_query:
            return RetrievalResult(
                query=query.query,
                chunks=[],
                total_chunks_found=0,
                total_tokens_returned=0,
                budget_exhausted=False,
            )

        # Collect and score across all candidate indices
        all_scored: List[Tuple[RetrievedChunk, float]] = []

        for index in indices_to_query:
            scored_tuples = index.score_query(query.query)
            for idx, score in scored_tuples:
                chunk = index.chunks[idx]
                all_scored.append((chunk, score))

        # Sort all scored chunks across sources by BM25 score descending
        all_scored.sort(key=lambda item: item[1], reverse=True)

        # Enforce budget slicing
        budget = max_tokens or query.max_tokens or self.default_budget_tokens
        selected_chunks: List[RetrievedChunk] = []
        tokens_used = 0
        budget_exhausted = False

        for chunk, score in all_scored:
            if len(selected_chunks) >= query.top_k:
                break

            chunk_tokens = chunk.estimated_tokens or estimate_tokens(chunk.content)

            # Strict budget check: never exceed budget
            if tokens_used + chunk_tokens > budget:
                budget_exhausted = True
                continue

            # Clone chunk with final relevance score
            chunk_copy = chunk.model_copy(deep=True)
            chunk_copy.relevance_score = round(score, 4)
            selected_chunks.append(chunk_copy)
            tokens_used += chunk_tokens

        return RetrievalResult(
            query=query.query,
            chunks=selected_chunks,
            total_chunks_found=len(all_scored),
            total_tokens_returned=tokens_used,
            budget_exhausted=budget_exhausted,
        )
