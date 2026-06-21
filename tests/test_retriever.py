import pytest
from src.retriever import (
    ChromaRetriever,
    BM25Retriever,
    reciprocal_rank_fusion,
)

# ---------------------------------------------------------------------------
# ChromaDB — Dense Retrieval
# ---------------------------------------------------------------------------

def test_chroma_add_and_query(mocker):
    """Documents added to ChromaDB should be retrievable by semantic query."""
    # Mock the DefaultEmbeddingFunction so we don't need a real model loaded
    fake_vector = [0.1] * 384  # all-MiniLM-L6-v2 produces 384-dim vectors
    mocker.patch(
        "chromadb.utils.embedding_functions.DefaultEmbeddingFunction.__call__",
        return_value=[fake_vector],
    )

    retriever = ChromaRetriever(collection_name="test_collection")
    retriever.add_documents(
        chunk_ids=["chunk_001", "chunk_002"],
        documents=["Messi scored twice against Real Madrid.", "Ronaldo won the Champions League."],
        metadatas=[
            {"url": "https://bbc.com/1", "title": "Messi scores", "source": "bbc", "date": ""},
            {"url": "https://bbc.com/2", "title": "Ronaldo wins UCL", "source": "bbc", "date": ""},
        ],
    )

    results = retriever.query(query_text="Who scored against Real Madrid?", top_k=1)

    assert len(results) == 1
    assert results[0]["chunk_id"] in ("chunk_001", "chunk_002")
    assert "document" in results[0]
    assert "metadata" in results[0]


# ---------------------------------------------------------------------------
# BM25 — Sparse Retrieval
# ---------------------------------------------------------------------------

def test_bm25_index_and_search():
    """BM25 should return ranked results based on keyword overlap."""
    corpus = [
        "Messi scored twice against Real Madrid.",
        "Ronaldo won the Champions League.",
        "Messi assists helped Barcelona win the title.",
    ]
    chunk_ids = ["chunk_001", "chunk_002", "chunk_003"]

    retriever = BM25Retriever()
    retriever.build_index(corpus=corpus, chunk_ids=chunk_ids)

    results = retriever.search(query="Messi scored", top_k=2)

    assert len(results) == 2
    # chunk_001 has "Messi" AND "scored" — should rank first
    assert results[0]["chunk_id"] == "chunk_001"


def test_bm25_returns_correct_top_k():
    """BM25 should respect top_k parameter."""
    corpus = [f"Document about player {i}" for i in range(10)]
    chunk_ids = [f"chunk_{i:03d}" for i in range(10)]

    retriever = BM25Retriever()
    retriever.build_index(corpus=corpus, chunk_ids=chunk_ids)

    results = retriever.search(query="player", top_k=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# RRF — Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def test_rrf_merges_two_lists():
    """RRF should merge dense and sparse results into a single ranked list."""
    dense_results = [
        {"chunk_id": "chunk_001", "document": "Doc A"},
        {"chunk_id": "chunk_002", "document": "Doc B"},
        {"chunk_id": "chunk_003", "document": "Doc C"},
    ]
    sparse_results = [
        {"chunk_id": "chunk_002", "document": "Doc B"},
        {"chunk_id": "chunk_001", "document": "Doc A"},
        {"chunk_id": "chunk_004", "document": "Doc D"},
    ]

    merged = reciprocal_rank_fusion(dense_results, sparse_results, top_k=4)

    assert len(merged) == 4
    # chunk_001 and chunk_002 appear in both lists — they should rank highest
    top_ids = [r["chunk_id"] for r in merged[:2]]
    assert "chunk_001" in top_ids
    assert "chunk_002" in top_ids


def test_rrf_top_k_respected():
    """RRF should not return more results than top_k."""
    dense  = [{"chunk_id": f"d{i}", "document": f"Dense doc {i}"} for i in range(5)]
    sparse = [{"chunk_id": f"s{i}", "document": f"Sparse doc {i}"} for i in range(5)]

    merged = reciprocal_rank_fusion(dense, sparse, top_k=3)
    assert len(merged) == 3


def test_rrf_deduplicates():
    """Documents appearing in both lists should only appear once in the output."""
    dense  = [{"chunk_id": "chunk_001", "document": "Doc A"}]
    sparse = [{"chunk_id": "chunk_001", "document": "Doc A"}]

    merged = reciprocal_rank_fusion(dense, sparse, top_k=5)
    ids = [r["chunk_id"] for r in merged]
    assert ids.count("chunk_001") == 1
