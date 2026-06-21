from typing import List, Dict, Any, Optional
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from rank_bm25 import BM25Okapi


class ChromaRetriever:
    """
    Dense retrieval wrapper around ChromaDB.
    Uses an in-memory EphemeralClient so tests run without disk I/O.
    Swap to PersistentClient for production.
    """

    def __init__(self, collection_name: str = "football_knowledge"):
        self._client = chromadb.EphemeralClient()

        # Use ChromaDB's built-in DefaultEmbeddingFunction (all-MiniLM-L6-v2 via ONNX).
        # This ships with chromadb itself — no extra deps, no PyTorch required.
        self.embedding_fn = DefaultEmbeddingFunction()

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self,
        chunk_ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Embeds and stores documents in ChromaDB using default local embeddings."""
        self._collection.add(
            ids=chunk_ids,
            documents=documents,
            metadatas=metadatas,
        )

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Returns the top_k most semantically similar documents to the query.
        Each result dict contains: chunk_id, document, metadata, distance.
        """
        raw = self._collection.query(
            query_texts=[query_text],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        results = []
        if not raw["ids"] or not raw["ids"][0]:
            return results
            
        for i, chunk_id in enumerate(raw["ids"][0]):
            results.append({
                "chunk_id": chunk_id,
                "document": raw["documents"][0][i],
                "metadata": raw["metadatas"][0][i],
                "distance": raw["distances"][0][i],
            })
        return results


class BM25Retriever:
    """
    Sparse keyword retrieval wrapper around BM25Okapi.
    Tokenizes on whitespace — suitable for natural-language football match chunks.
    """

    def __init__(self):
        self._bm25: Optional[BM25Okapi] = None
        self._chunk_ids: List[str] = []
        self._corpus: List[str] = []

    def build_index(self, corpus: List[str], chunk_ids: List[str]) -> None:
        """Tokenizes and indexes the corpus for BM25 retrieval."""
        self._corpus = corpus
        self._chunk_ids = chunk_ids
        tokenized = [doc.lower().split() for doc in corpus]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Returns the top_k highest-scoring documents for the given query."""
        if self._bm25 is None:
            raise RuntimeError("BM25 index has not been built. Call build_index() first.")

        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)

        # Pair each score with its index, sort descending, take top_k
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        return [
            {
                "chunk_id": self._chunk_ids[idx],
                "document": self._corpus[idx],
                "score": float(score),
            }
            for idx, score in ranked
        ]


def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    top_k: int = 5,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Merges two ranked result lists using Reciprocal Rank Fusion.

    Score for each document:  sum( 1 / (k + rank) )  across all lists.
    Documents appearing in both lists receive a combined higher score.
    Deduplicates automatically — each chunk_id appears at most once.

    Args:
        dense_results:  Ranked list from ChromaDB (most similar first).
        sparse_results: Ranked list from BM25 (highest score first).
        top_k:          Maximum number of results to return.
        k:              RRF constant (default 60, per the original paper).

    Returns:
        A single merged, deduplicated, re-ranked list of result dicts.
    """
    scores: Dict[str, float] = {}
    docs: Dict[str, Dict[str, Any]] = {}

    for rank, result in enumerate(dense_results, start=1):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        docs[cid] = result

    for rank, result in enumerate(sparse_results, start=1):
        cid = result["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
        docs[cid] = result

    ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:top_k]

    return [
        {**docs[cid], "rrf_score": scores[cid]}
        for cid in ranked_ids
    ]
