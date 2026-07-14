import httpx

from services.chat.config import settings


def run_pipeline_sync(
    *,
    session_id: str,
    query: str,
    context_messages: list[dict[str, str]],
    snapshot: str,
    snapshot_turn_count: int,
    project_id: str | None,
) -> dict:
    url = f"{settings.orchestrator_service_url.rstrip('/')}/pipeline/run"
    response = httpx.post(
        url,
        json={
            "session_id": session_id,
            "query": query,
            "context_messages": context_messages,
            "snapshot": snapshot,
            "snapshot_turn_count": snapshot_turn_count,
            "project_id": project_id,
        },
        timeout=300.0,
    )
    response.raise_for_status()
    return response.json()["data"]
