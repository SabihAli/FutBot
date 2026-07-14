import os

from fastapi import APIRouter, Depends, HTTPException

from futbot_common.responses import DataResponse
from services.retrieval.config import settings
from services.retrieval.deps import get_engine
from services.retrieval.engine import RetrievalEngine
from services.retrieval.schemas import (
    DeleteIndexResponse,
    IndexChunksRequest,
    IndexChunksResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunk,
)

router = APIRouter(tags=["retrieve"])


def _chunk_metadata(chunk) -> dict:
    meta = {
        "source_file": chunk.source_file,
        "section_heading": chunk.section_heading,
        "chunk_type": chunk.chunk_type,
        "chunk_index": chunk.chunk_index,
        "token_count": chunk.token_count,
        "page_number": chunk.page if chunk.page is not None else -1,
    }
    if chunk.sheet_name:
        meta["sheet_name"] = chunk.sheet_name
    return meta


@router.post("/retrieve", response_model=DataResponse[RetrieveResponse])
def retrieve(
    body: RetrieveRequest,
    engine: RetrievalEngine = Depends(get_engine),
) -> DataResponse[RetrieveResponse]:
    hits = engine.retrieve(body.query, top_k=body.top_k, project_id=body.project_id)
    return DataResponse(
        data=RetrieveResponse(chunks=[RetrievedChunk(**h) for h in hits])
    )


@router.post("/index/chunks", response_model=DataResponse[IndexChunksResponse])
def index_chunks(
    body: IndexChunksRequest,
    engine: RetrievalEngine = Depends(get_engine),
) -> DataResponse[IndexChunksResponse]:
    chunk_ids: list[str] = []
    documents: list[str] = []
    bm25_documents: list[str] = []
    metadatas: list[dict] = []

    for chunk in body.chunks:
        chunk_ids.append(chunk.chunk_id)
        documents.append(chunk.text)
        bm25_documents.append(chunk.bm25_text or chunk.text)
        metadatas.append(_chunk_metadata(chunk))

    indexed = engine.index_chunks(
        project_id=body.project_id,
        file_id=body.file_id,
        chunk_ids=chunk_ids,
        documents=documents,
        bm25_documents=bm25_documents,
        metadatas=metadatas,
    )
    os.makedirs(settings.data_dir, exist_ok=True)
    engine.bm25.save(settings.bm25_path)
    return DataResponse(data=IndexChunksResponse(indexed=indexed))


@router.delete("/index/{project_id}", response_model=DataResponse[DeleteIndexResponse])
def delete_project_index(
    project_id: str,
    engine: RetrievalEngine = Depends(get_engine),
) -> DataResponse[DeleteIndexResponse]:
    if project_id == "__global__":
        raise HTTPException(status_code=400, detail="Cannot delete global knowledge base.")
    removed = engine.delete_project_index(project_id)
    engine.bm25.save(settings.bm25_path)
    return DataResponse(data=DeleteIndexResponse(removed=removed))
