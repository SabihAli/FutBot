import pytest

from services.tools.builtins.web_search import search_web
from services.tools.registry import WEB_SEARCH_TOOL, execute_tool, reset_registry_for_tests
from services.tools.builtins.web_search import WebSearchTool, register_web_search


def test_web_search_tavily_primary(mocker):
    reset_registry_for_tests()
    register_web_search()
    mocker.patch(
        "services.tools.builtins.web_search._search_tavily",
        return_value={"snippets": ["goal"], "sources": [], "provider": "tavily"},
    )
    result = search_web("Arsenal score")
    assert result["provider"] == "tavily"


def test_web_search_serper_fallback(mocker):
    mocker.patch(
        "services.tools.builtins.web_search._search_tavily",
        side_effect=RuntimeError("tavily down"),
    )
    mocker.patch(
        "services.tools.builtins.web_search._search_serper",
        return_value={"snippets": ["news"], "sources": [], "provider": "serper"},
    )
    result = search_web("Arsenal transfer")
    assert result["provider"] == "serper"


def test_execute_skips_web_search_when_disabled():
    reset_registry_for_tests()
    register_web_search()
    result = execute_tool(WEB_SEARCH_TOOL, {"query": "news"}, web_search_enabled=False)
    assert result.skipped is True
