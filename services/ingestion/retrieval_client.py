import httpx

from services.ingestion.config import settings


def index_chunks(
    *,
    project_id: str,
    file_id: str,
    chunks: list[dict],
) -> int:
    url = f"{settings.retrieval_service_url.rstrip('/')}/index/chunks"
    response = httpx.post(
        url,
        json={"project_id": project_id, "file_id": file_id, "chunks": chunks},
        timeout=60.0,
    )
    response.raise_for_status()
    return int(response.json()["data"]["indexed"])
