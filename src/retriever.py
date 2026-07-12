from typing import List, Dict, Any, Optional
import os
import pickle
import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from rank_bm25 import BM25Okapi
import logging

logger = logging.getLogger(__name__)

# Directory where both ChromaDB and BM25 data are persisted
DATA_DIR = os.environ.get("DATA_DIR", "data")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma_db")
BM25_PATH = os.path.join(DATA_DIR, "bm25_index.pkl")


class ChromaRetriever:
    """
    Dense retrieval wrapper around ChromaDB.
    Uses PersistentClient so the index survives container restarts.
    """

    def __init__(self, collection_name: str = "football_knowledge"):
        os.makedirs(CHROMA_PATH, exist_ok=True)
        self._client = chromadb.PersistentClient(path=CHROMA_PATH)

        # Use ChromaDB's built-in DefaultEmbeddingFunction (all-MiniLM-L6-v2 via ONNX).
        self.embedding_fn = DefaultEmbeddingFunction()

        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        """Returns the number of documents currently stored."""
        return self._collection.count()

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
            logger.debug(f"DEBUG [ChromaDB]: No results found for query '{query_text}'")
            return results

        logger.debug(f"DEBUG [ChromaDB]: Found {len(raw['ids'][0])} results for '{query_text}'")
        for i, chunk_id in enumerate(raw["ids"][0]):
            distance = raw["distances"][0][i]
            logger.debug(f"  -> Rank {i+1} | ID: {chunk_id} | Distance: {distance:.4f}")
            results.append({
                "chunk_id": chunk_id,
                "document": raw["documents"][0][i],
                "metadata": raw["metadatas"][0][i],
                "distance": distance,
            })
        return results


class BM25Retriever:
    """
    Sparse keyword retrieval wrapper around BM25Okapi.
    Index can be saved to and loaded from disk via pickle.
    """

    def __init__(self):
        self._bm25: Optional[BM25Okapi] = None
        self._chunk_ids: List[str] = []
        self._corpus: List[str] = []

    def is_loaded(self) -> bool:
        return self._bm25 is not None

    @property
    def corpus(self) -> List[str]:
        return self._corpus

    @property
    def chunk_ids(self) -> List[str]:
        return self._chunk_ids

    def build_index(self, corpus: List[str], chunk_ids: List[str]) -> None:
        """Tokenizes and indexes the corpus for BM25 retrieval."""
        self._corpus = corpus
        self._chunk_ids = chunk_ids
        tokenized = [doc.lower().split() for doc in corpus]
        self._bm25 = BM25Okapi(tokenized)

    def save(self, path: str = BM25_PATH) -> None:
        """Serializes the BM25 index, corpus, and chunk_ids to disk."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump({
                "bm25": self._bm25,
                "chunk_ids": self._chunk_ids,
                "corpus": self._corpus,
            }, f)
        logger.debug(f"DEBUG [BM25]: Index saved to {path}")

    def load(self, path: str = BM25_PATH) -> bool:
        """Loads the BM25 index from disk. Returns True if successful."""
        if not os.path.exists(path):
            return False
        with open(path, "rb") as f:
            data = pickle.load(f)
        self._bm25 = data["bm25"]
        self._chunk_ids = data["chunk_ids"]
        self._corpus = data["corpus"]
        logger.debug(f"DEBUG [BM25]: Index loaded from {path} ({len(self._corpus)} docs)")
        return True

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Returns the top_k highest-scoring documents for the given query."""
        if self._bm25 is None:
            raise RuntimeError("BM25 index has not been built. Call build_index() first.")

        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)

        # Pair each score with its index, sort descending, take top_k
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        logger.debug(f"DEBUG [BM25]: Found {len(ranked)} top results for '{query}'")
        results = []
        for rank_idx, (idx, score) in enumerate(ranked):
            chunk_id = self._chunk_ids[idx]
            logger.debug(f"  -> Rank {rank_idx+1} | ID: {chunk_id} | Score: {score:.4f}")
            results.append({
                "chunk_id": chunk_id,
                "document": self._corpus[idx],
                "score": float(score),
            })

        return results


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

    logger.debug(f"\nDEBUG [RRF]: Fusing {len(dense_results)} Dense + {len(sparse_results)} Sparse results.")
    final_results = []
    for rank_idx, cid in enumerate(ranked_ids):
        rrf_score = scores[cid]
        logger.debug(f"  -> Final Rank {rank_idx+1} | ID: {cid} | RRF Score: {rrf_score:.4f}")
        final_results.append({**docs[cid], "rrf_score": rrf_score})

    return final_results
