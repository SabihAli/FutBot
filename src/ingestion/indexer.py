from services.retrieval.indexer import chunked_to_index_payload


def index_blocks(*_args, **_kwargs) -> int:
    raise NotImplementedError("Indexing moved to retrieval service; wired in Phase 5 ingestion.")
