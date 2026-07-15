import logging
from typing import Any

import httpx

from services.tools.config import settings
from services.tools.errors import ToolExecutionError
from services.tools.registry import WEB_SEARCH_TOOL, register_tool
from services.tools.schemas import ToolDefinition, ToolParameter

logger = logging.getLogger(__name__)


def _normalize_tavily(data: dict[str, Any]) -> dict[str, Any]:
    snippets = []
    sources = []
    for item in data.get("results", []):
        snippets.append(item.get("content", "") or item.get("snippet", ""))
        sources.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
            }
        )
    return {"snippets": snippets, "sources": sources, "provider": "tavily"}


def _normalize_serper(data: dict[str, Any]) -> dict[str, Any]:
    snippets = []
    sources = []
    for item in data.get("organic", []):
        snippets.append(item.get("snippet", ""))
        sources.append({"title": item.get("title", ""), "url": item.get("link", "")})
    return {"snippets": snippets, "sources": sources, "provider": "serper"}


def _search_tavily(query: str, num_results: int) -> dict[str, Any]:
    if not settings.tavily_api_key:
        raise ToolExecutionError("TAVILY_API_KEY not configured")
    response = httpx.post(
        "https://api.tavily.com/search",
        json={
            "api_key": settings.tavily_api_key,
            "query": query,
            "max_results": num_results,
        },
        timeout=settings.request_timeout_sec,
    )
    response.raise_for_status()
    return _normalize_tavily(response.json())


def _search_serper(query: str, num_results: int) -> dict[str, Any]:
    if not settings.serper_api_key:
        raise ToolExecutionError("SERPER_API_KEY not configured")
    response = httpx.post(
        "https://google.serper.dev/search",
        json={"q": query, "num": num_results},
        headers={"X-API-KEY": settings.serper_api_key},
        timeout=settings.request_timeout_sec,
    )
    response.raise_for_status()
    return _normalize_serper(response.json())


def search_web(query: str, num_results: int = 5) -> dict[str, Any]:
    errors: list[str] = []
    try:
        return _search_tavily(query, num_results)
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        errors.append(f"tavily: {exc}")
    try:
        return _search_serper(query, num_results)
    except Exception as exc:
        logger.warning("Serper search failed: %s", exc)
        errors.append(f"serper: {exc}")
    raise ToolExecutionError("; ".join(errors) or "web search unavailable")


class WebSearchTool:
    name = WEB_SEARCH_TOOL

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description="Search the internet for live football news and current events.",
            parameters=[
                ToolParameter(name="query", description="Search query", required=True),
                ToolParameter(
                    name="num_results",
                    type="integer",
                    description="Number of results (3-8)",
                    required=False,
                ),
            ],
            source="builtin",
        )

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            raise ToolExecutionError("query is required")
        num_results = int(arguments.get("num_results", 5))
        num_results = max(3, min(8, num_results))
        return search_web(query, num_results)


def register_web_search() -> None:
    register_tool(WebSearchTool())
