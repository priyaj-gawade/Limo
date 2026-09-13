"""Data models for Phase D5.5: Context Retrieval & Token Budget Slicing.

Carries section titles, hierarchy levels, page numbers, and timestamps to ensure
every retrieved snippet has rock-solid evidence grounding.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ...agent.context import estimate_tokens


class RetrievedChunk(BaseModel):
    """A grounded sub-document snippet returned by the retrieval engine."""

    chunk_id: str = Field(description="Unique ID for this chunk within the retrieval result")
    source_id: str = Field(description="Originating Source ID")
    chunk_index: int = Field(description="Sequential index of the chunk within the indexed document")
    section_title: Optional[str] = Field(default=None, description="Title of the parent section")
    level: int = Field(default=1, description="Heading level (1 for H1, 2 for H2, etc.)")
    page_number: Optional[int] = Field(default=None, description="Physical document page number if available")
    timestamp: Optional[str] = Field(default=None, description="Media timestamp (e.g., '01:45') if available")
    content: str = Field(description="Textual content of the chunk")
    relevance_score: float = Field(default=0.0, description="BM25 or similarity relevance score")
    estimated_tokens: int = Field(default=0, description="Estimated token count via shared D4.2 heuristic")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary anchor metadata")

    def model_post_init(self, __context: Any) -> None:
        if not self.estimated_tokens and self.content:
            self.estimated_tokens = estimate_tokens(self.content)


class RetrievalQuery(BaseModel):
    """Specification of an informational query to retrieve grounded context."""

    query: str = Field(min_length=1, description="Search terms or user question")
    source_ids: Optional[List[str]] = Field(default=None, description="Target source IDs (if None, all sources in context)")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="Maximum token budget for returned chunks")
    top_k: int = Field(default=10, ge=1, le=50, description="Maximum number of candidate chunks to consider")


class RetrievalResult(BaseModel):
    """Budget-bounded collection of retrieved grounded chunks."""

    query: str
    chunks: List[RetrievedChunk] = Field(default_factory=list)
    total_chunks_found: int = Field(default=0)
    total_tokens_returned: int = Field(default=0)
    budget_exhausted: bool = Field(default=False)
