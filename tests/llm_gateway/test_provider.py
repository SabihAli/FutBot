import pytest
import requests
from unittest.mock import MagicMock

from services.llm_gateway.components import (
    DecisionJudge,
    DraftGenerator,
    Orchestrator,
    QueryRewriter,
    SnapshotCompressor,
)
from services.llm_gateway.provider import (
    GROQ_API_URL,
    MODEL_DECISION,
    MODEL_GENERATOR,
    MODEL_ORCHESTRATOR,
    _call_groq,
    _strip_think_tags,
    invoke_llm,
)


def _make_groq_response(content: str, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def test_strip_think_tags_removes_block():
    raw = "<think>This is reasoning.</think>Final answer."
    assert _strip_think_tags(raw) == "Final answer."


def test_call_groq_retries_on_429(mocker):
    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429
    rate_limit_resp.headers = {"retry-after": "0"}
    rate_limit_resp.raise_for_status = MagicMock(side_effect=requests.HTTPError("429"))
    rate_limit_resp.json.return_value = {}
    success_resp = _make_groq_response("Success after retry.")
    mocker.patch(
        "services.llm_gateway.provider.requests.post",
        side_effect=[rate_limit_resp, success_resp],
    )
    mocker.patch("services.llm_gateway.provider._time.sleep")
    import services.llm_gateway.provider as llm_mod

    original_key = llm_mod.settings.groq_api_key
    llm_mod.settings.groq_api_key = "test-key"
    _, clean, _, _ = _call_groq("rewriter", "", "Test prompt.")
    llm_mod.settings.groq_api_key = original_key
    assert clean == "Success after retry."


def test_invoke_llm_groq_provider_routes_correctly(mocker):
    mock_groq = mocker.patch(
        "services.llm_gateway.provider._call_groq",
        return_value=("raw", "Clean Groq response.", 200, 42),
    )
    mock_local = mocker.patch("services.llm_gateway.provider._call_local")
    import services.llm_gateway.provider as llm_mod

    original = llm_mod.settings.llm_provider
    llm_mod.settings.llm_provider = "groq"
    result = invoke_llm("Test prompt.", model_name="ignored", step="rewriter")
    llm_mod.settings.llm_provider = original
    mock_groq.assert_called_once()
    mock_local.assert_not_called()
    assert result == "Clean Groq response."


def test_snapshot_compressor_parses_json(mocker):
    mocker.patch(
        "services.llm_gateway.components.invoke_llm",
        return_value='{"topics":["football"]}',
    )
    mocker.patch(
        "services.llm_gateway.components.get_prompt_parts",
        return_value=("system {max_tokens}", "user {existing_snapshot} {newly_aged_messages}"),
    )
    compressor = SnapshotCompressor()
    result = compressor.compress_incremental("{}", [{"role": "user", "content": "hi"}])
    assert "football" in result


def test_orchestrator_routes_knowledge_query(mocker):
    mocker.patch("services.llm_gateway.components.invoke_llm", return_value="KNOWLEDGE")
    mocker.patch(
        "services.llm_gateway.components.get_prompt_parts",
        return_value=("sys", "user {query}"),
    )
    assert Orchestrator().classify("Who won?") == "KNOWLEDGE"


def test_decision_judge_evaluates_pass(mocker):
    mocker.patch(
        "services.llm_gateway.components.invoke_llm",
        return_value='{"status": "PASS", "reasoning": "ok"}',
    )
    mocker.patch(
        "services.llm_gateway.components.get_prompt_parts",
        return_value=("sys", "{context_text} {query} {draft}"),
    )
    result = DecisionJudge().evaluate("q", "draft", [])
    assert result["status"] == "PASS"
