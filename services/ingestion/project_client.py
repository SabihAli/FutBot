import httpx

from services.ingestion.config import settings


def update_file_status(
    *,
    project_id: str,
    file_id: str,
    status: str,
    error_message: str | None = None,
) -> None:
    url = (
        f"{settings.project_service_url.rstrip('/')}"
        f"/projects/{project_id}/files/{file_id}/status"
    )
    response = httpx.patch(
        url,
        json={"status": status, "error_message": error_message},
        timeout=10.0,
    )
    response.raise_for_status()
