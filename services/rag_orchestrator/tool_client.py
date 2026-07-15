import httpx

from services.rag_orchestrator.config import settings

WEB_SEARCH_TOOL = "web_search"
WEB_SEARCH_SKIPPED_NOTICE = (
    "Web search was needed for this answer but is disabled. "
    "Enable web search for broader coverage."
)
MCP_UNAVAILABLE_NOTICE = (
    "Live football data services are unavailable. Answering from your knowledge base only."
)


def mcp_tools_available() -> bool:
    url = f"{settings.tools_service_url.rstrip('/')}/tools/health"
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
        return bool(response.json()["data"]["mcp_available"])
    except Exception:
        return False


def fetch_tool_catalog() -> list[dict]:
    url = f"{settings.tools_service_url.rstrip('/')}/tools"
    response = httpx.get(url, timeout=10.0)
    response.raise_for_status()
    return response.json()["data"]


def execute_tool(
    *,
    tool: str,
    arguments: dict,
    web_search_enabled: bool,
    session_id: str = "",
    run_id: int | None = None,
) -> dict:
    url = f"{settings.tools_service_url.rstrip('/')}/tools/execute"
    response = httpx.post(
        url,
        json={
            "tool": tool,
            "arguments": arguments,
            "web_search_enabled": web_search_enabled,
            "session_id": session_id,
            "run_id": run_id,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()["data"]
