"""Lexical chunk retrieval abstraction avoiding full-document context dumps."""

from abc import ABC, abstractmethod
import math
import re
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RetrievedChunk(BaseModel):
    """Scoped text excerpt extracted from a source document."""
    source_id: str
    chunk_index: int
    text: str
    score: float = 0.0
    token_estimate: int = 0


class BaseRetriever(ABC):
    """Abstract retrieval provider interface."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        sources: Dict[str, str],
        max_tokens: int = 2000,
        top_k: int = 5,
    ) -> List[RetrievedChunk]:
        """Retrieve most relevant chunks within token budget."""
        pass


class LexicalRetriever(BaseRetriever):
    """BM25-style lexical chunk retriever with strict token budget enforcement."""

    def __init__(self, chunk_size_chars: int = 400, chunk_overlap_chars: int = 50):
        self.chunk_size = chunk_size_chars
        self.chunk_overlap = chunk_overlap_chars

    def _chunk_text(self, text: str) -> List[str]:
        """Split text into overlapping character slices."""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        chunks = []
        start = 0
        step = self.chunk_size - self.chunk_overlap
        while start < len(text):
            chunk = text[start : start + self.chunk_size].strip()
            if chunk:
                chunks.append(chunk)
            start += step
        return chunks

    def _score_chunk(self, query_terms: List[str], chunk_text: str) -> float:
        """Score term frequency in chunk."""
        lower_chunk = chunk_text.lower()
        score = 0.0
        for term in query_terms:
            count = len(re.findall(re.escape(term), lower_chunk))
            if count > 0:
                # Log-damped term frequency
                score += (1.0 + math.log(count)) * 2.0
        return score

    async def retrieve(
        self,
        query: str,
        sources: Dict[str, str],
        max_tokens: int = 2000,
        top_k: int = 5,
    ) -> List[RetrievedChunk]:
        """Index candidate chunks across sources and return top scored within token budget."""
        query_terms = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
        if not query_terms:
            return []

        all_candidates: List[RetrievedChunk] = []

        for src_id, full_text in sources.items():
            chunks = self._chunk_text(full_text)
            for idx, chunk_str in enumerate(chunks):
                score = self._score_chunk(query_terms, chunk_str)
                if score > 0:
                    token_est = max(1, len(chunk_str) // 4)
                    all_candidates.append(
                        RetrievedChunk(
                            source_id=src_id,
                            chunk_index=idx,
                            text=chunk_str,
                            score=score,
                            token_estimate=token_est,
                        )
                    )

        # Sort descending by relevance score
        all_candidates.sort(key=lambda c: c.score, reverse=True)

        # Enforce top_k and max_tokens budget
        results: List[RetrievedChunk] = []
        tokens_accumulated = 0
        for c in all_candidates[:top_k]:
            if tokens_accumulated + c.token_estimate > max_tokens:
                break
            results.append(c)
            tokens_accumulated += c.token_estimate

        return results
