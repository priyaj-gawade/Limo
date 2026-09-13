"""Context Retrieval Business Service (Phase D5.5).

Coordinates between AgentContext, SourceRepository, NormalizationService, and
the Section-Aware BM25Retriever.

Adheres strictly to the architectural principles:
- Zero raw-file re-reading: strictly consumes cached ExtractedDocument / NormalizedDocument.
- Primary retrieval layer is NormalizedDocument (retains exact wording and structure).
- Configurable dynamic token budgets from AgentContext.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional

from ...agent.context import AgentContext
from ...config import settings
from ...db.connection import get_connection
from ...db.repositories.source_repo import SourceRepository
from ...exceptions import EntityNotFoundError, StorageError
from ..extraction.models import ExtractedDocument
from ..normalization.models import NormalizedDocument
from ..normalization.service import NormalizationService, normalization_service
from .base import BaseRetriever
from .bm25 import BM25Retriever
from .models import RetrievalQuery, RetrievalResult

logger = logging.getLogger("limo.services.retrieval")


class RetrievalService:
    """High-level business service for targeted, budget-enforced context retrieval."""

    def __init__(
        self,
        retriever: Optional[BaseRetriever] = None,
        norm_service: Optional[NormalizationService] = None,
        data_dir: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        self.retriever = retriever or BM25Retriever(
            default_budget_tokens=getattr(settings, "default_retrieval_token_budget", 2000)
        )
        self.norm_service = norm_service or normalization_service
        self.data_dir = Path(data_dir or settings.data_dir)
        self.db_path = db_path or str(settings.db_path)
        self._normalized_cache: dict[str, NormalizedDocument] = {}

    def get_or_create_normalized_document(self, source_id: str) -> NormalizedDocument:
        """Load or produce NormalizedDocument from cached extraction without raw file re-reading."""
        if source_id in self._normalized_cache:
            return self._normalized_cache[source_id]

        # 1. Fetch extraction cache file
        ext_path = self.data_dir / "extractions" / f"{source_id}.json"
        if not ext_path.exists():
            raise EntityNotFoundError(f"Extraction cache for source '{source_id}' not found. Extract the source first.")

        try:
            with open(ext_path, "r", encoding="utf-8") as f:
                ext_dict = json.load(f)
            extracted_doc = ExtractedDocument(**ext_dict)
        except Exception as e:
            raise StorageError(f"Failed to read extraction cache for source '{source_id}': {e}")

        # 2. Normalize extracted content (deterministic, fast, zero I/O)
        norm_doc = self.norm_service.normalize(extracted_doc)
        self._normalized_cache[source_id] = norm_doc

        # 3. Pre-index in BM25 retriever (build once, query many)
        if not self.retriever.has_index(source_id):
            self.retriever.index_document(norm_doc)

        return norm_doc

    async def retrieve_context(
        self,
        query: str,
        source_id: Optional[str] = None,
        source_ids: Optional[List[str]] = None,
        max_tokens: Optional[int] = None,
        top_k: int = 10,
        context: Optional[AgentContext] = None,
    ) -> RetrievalResult:
        """Execute section-aware BM25 retrieval against target sources within budget."""
        # Determine budget: explicit parameter > context budget > settings default
        budget = (
            max_tokens
            or (context.retrieval_budget_tokens if context else None)
            or getattr(settings, "default_retrieval_token_budget", 2000)
        )

        target_sids: List[str] = []
        if source_id:
            target_sids.append(source_id)
        elif source_ids:
            target_sids.extend(source_ids)
        elif context and context.project_id:
            # If no sources specified, query all registered sources in the active project
            with get_connection(self.db_path) as conn:
                sources = SourceRepository.list_sources_by_project(conn, context.project_id)
                target_sids = [s.id for s in sources]

        if not target_sids:
            return RetrievalResult(
                query=query,
                chunks=[],
                total_chunks_found=0,
                total_tokens_returned=0,
                budget_exhausted=False,
            )

        # Ensure all target sources are indexed
        for sid in target_sids:
            try:
                self.get_or_create_normalized_document(sid)
            except Exception as e:
                logger.warning("Could not hydrate normalized doc for source '%s': %s", sid, e)

        retrieval_query = RetrievalQuery(
            query=query,
            source_ids=target_sids,
            max_tokens=budget,
            top_k=top_k,
        )

        return await self.retriever.retrieve(retrieval_query, max_tokens=budget)


# Default shared service instance
retrieval_service = RetrievalService()
