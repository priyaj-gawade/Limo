"""Unit tests for Phase D4.6: LexicalRetriever chunk indexing and token budget enforcement."""

import pytest
from app.agent.retrieval.retriever import LexicalRetriever


@pytest.mark.asyncio
async def test_lexical_retriever_ranking_and_chunking():
    retriever = LexicalRetriever(chunk_size_chars=200, chunk_overlap_chars=30)
    sources = {
        "src_financial": (
            "In fiscal year 2025, company revenue surged by 45% due to cloud platform expansion. "
            "Net income margins reached record highs of 28% across North American enterprise clients. "
            "Capital expenditures for semiconductor fabrication grew to $4.2 billion."
        ),
        "src_biology": (
            "Cellular mitosis occurs in four distinct phases: prophase, metaphase, anaphase, and telophase. "
            "Chromosomes align along the equatorial plane during metaphase."
        ),
    }

    results = await retriever.retrieve(query="revenue cloud expansion", sources=sources, max_tokens=500, top_k=3)
    assert len(results) > 0
    assert results[0].source_id == "src_financial"
    assert "revenue" in results[0].text.lower()
    assert results[0].score > 0


@pytest.mark.asyncio
async def test_lexical_retriever_budget_ceiling():
    retriever = LexicalRetriever(chunk_size_chars=100, chunk_overlap_chars=10)
    long_text = "Data analysis and reporting metrics. " * 30
    sources = {"src_long": long_text}

    # Restrict token budget to a very small ceiling (e.g. 50 tokens)
    results = await retriever.retrieve(query="data metrics", sources=sources, max_tokens=50, top_k=10)
    total_tokens = sum(c.token_estimate for c in results)
    assert total_tokens <= 50
