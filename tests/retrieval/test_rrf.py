from services.retrieval.rrf import reciprocal_rank_fusion


def test_rrf_merges_two_lists():
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
    top_ids = {r["chunk_id"] for r in merged[:2]}
    assert top_ids == {"chunk_001", "chunk_002"}


def test_rrf_top_k_respected():
    dense = [{"chunk_id": f"d{i}", "document": f"Dense doc {i}"} for i in range(5)]
    sparse = [{"chunk_id": f"s{i}", "document": f"Sparse doc {i}"} for i in range(5)]

    merged = reciprocal_rank_fusion(dense, sparse, top_k=3)
    assert len(merged) == 3


def test_rrf_deduplicates():
    dense = [{"chunk_id": "chunk_001", "document": "Doc A"}]
    sparse = [{"chunk_id": "chunk_001", "document": "Doc A"}]

    merged = reciprocal_rank_fusion(dense, sparse, top_k=5)
    ids = [r["chunk_id"] for r in merged]
    assert ids.count("chunk_001") == 1
