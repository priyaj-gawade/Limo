"""Abstract base class for Limo Context Retrievers (Phase D5.5).

Decouples agent orchestration and retrieval tools from specific indexing algorithms
(BM25, dense embeddings, or hybrid search).
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..normalization.models import NormalizedDocument
from .models import RetrievalQuery, RetrievalResult


class BaseRetriever(ABC):
    """Abstract retrieval contract for section-aware sub-document querying."""

    @abstractmethod
    def index_document(self, doc: NormalizedDocument) -> None:
        """Parse and pre-index chunks from a NormalizedDocument once."""
        pass

    @abstractmethod
    def has_index(self, source_id: str) -> bool:
        """Check if pre-indexed structures exist for the given source ID."""
        pass

    @abstractmethod
    async def retrieve(
        self,
        query: RetrievalQuery,
        doc: Optional[NormalizedDocument] = None,
        max_tokens: Optional[int] = None,
    ) -> RetrievalResult:
        """Execute a budget-bounded query against indexed documents or direct document."""
        pass
