import logging
import time
from typing import Any, Protocol

from services.tools.errors import ToolExecutionError, ToolNotFoundError
from services.tools.schemas import ExecuteToolResponse, ToolDefinition

logger = logging.getLogger(__name__)

WEB_SEARCH_TOOL = "web_search"
MARKDOWN_TO_PDF_TOOL = "markdown_to_pdf"


class ToolHandler(Protocol):
    name: str

    def definition(self) -> ToolDefinition: ...

    def execute(self, arguments: dict[str, Any]) -> dict[str, Any]: ...


_handlers: dict[str, ToolHandler] = {}
_mcp_healthy: bool = True


def register_tool(handler: ToolHandler) -> None:
    _handlers[handler.name] = handler


def set_mcp_healthy(healthy: bool) -> None:
    global _mcp_healthy
    _mcp_healthy = healthy


def mcp_tools_available() -> bool:
    return any(name.startswith("mcp:") for name in _handlers)


def list_tools(*, include_web_search: bool = True) -> list[ToolDefinition]:
    tools: list[ToolDefinition] = []
    for name, handler in sorted(_handlers.items()):
        if name == MARKDOWN_TO_PDF_TOOL:
            continue
        if name == WEB_SEARCH_TOOL and not include_web_search:
            continue
        tools.append(handler.definition())
    return tools


def get_tool(name: str) -> ToolHandler:
    if name not in _handlers:
        raise ToolNotFoundError(name)
    return _handlers[name]


def execute_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    web_search_enabled: bool = False,
) -> ExecuteToolResponse:
    if name == WEB_SEARCH_TOOL and not web_search_enabled:
        return ExecuteToolResponse(
            tool=name,
            success=False,
            skipped=True,
            error_message="web_search disabled",
            duration_ms=0,
        )

    started = time.monotonic()
    try:
        handler = get_tool(name)
        result = handler.execute(arguments)
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExecuteToolResponse(
            tool=name,
            success=True,
            result=result,
            duration_ms=duration_ms,
        )
    except ToolNotFoundError as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExecuteToolResponse(
            tool=name,
            success=False,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        duration_ms = int((time.monotonic() - started) * 1000)
        return ExecuteToolResponse(
            tool=name,
            success=False,
            error_message=str(exc),
            duration_ms=duration_ms,
        )


def reset_registry_for_tests() -> None:
    _handlers.clear()
    set_mcp_healthy(True)
