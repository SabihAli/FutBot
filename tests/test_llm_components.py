import pytest
import requests
from unittest.mock import MagicMock, patch

from src.llm_components import (
    QueryRewriter,
    Orchestrator,
    DraftGenerator,
    DecisionJudge,
    MODEL_ORCHESTRATOR,
    MODEL_GENERATOR,
    MODEL_DECISION,
    GROQ_API_URL,
    _strip_think_tags,
    _call_groq,
    _call_local,
    invoke_llm,
)


# ===========================================================================
# Shared helpers
# ===========================================================================

def _make_groq_response(content: str, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response that looks like a Groq API response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _make_local_response(content: str) -> MagicMock:
    """Build a mock requests.Response that looks like a local /v1/chat/completions response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ===========================================================================
# _strip_think_tags
# ===========================================================================

def test_strip_think_tags_removes_block():
    raw = "<think>This is reasoning.</think>Final answer."
    assert _strip_think_tags(raw) == "Final answer."


def test_strip_think_tags_multiline():
    raw = "<think>\nLine 1\nLine 2\n</think>Clean output."
    assert _strip_think_tags(raw) == "Clean output."


def test_strip_think_tags_no_block():
    raw = "No think tags here."
    assert _strip_think_tags(raw) == "No think tags here."


def test_strip_think_tags_case_insensitive():
    raw = "<THINK>Caps block</THINK>Answer."
    assert _strip_think_tags(raw) == "Answer."


# ===========================================================================
# _call_groq — happy path
# ===========================================================================

def test_call_groq_non_thinking_role(mocker):
    """Non-judge roles should inject a /no_think system message to suppress think tags."""
    mock_post = mocker.patch("src.llm_components.requests.post",
                             return_value=_make_groq_response("Rewritten query."))
    mocker.patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})

    # Re-import to pick up patched env (or pass directly)
    import src.llm_components as llm_mod
    original_key = llm_mod.GROQ_API_KEY
    llm_mod.GROQ_API_KEY = "test-key"

    raw, clean, status_code, latency_ms = _call_groq("rewriter", "", "Rewrite this.")

    llm_mod.GROQ_API_KEY = original_key  # restore

    assert clean == "Rewritten query."
    assert status_code == 200
    assert latency_ms >= 0

    # Payload must include reasoning_effort="none" for non-judge roles
    payload = mock_post.call_args[1]["json"]
    assert payload.get("reasoning_effort") == "none"
    assert payload["model"] == "qwen/qwen3.6-27b"


def test_call_groq_thinking_enabled_for_judge(mocker):
    """The judge role must inject a /think system message to enable reasoning."""
    mock_post = mocker.patch("src.llm_components.requests.post",
                             return_value=_make_groq_response('{"status": "PASS"}'))

    import src.llm_components as llm_mod
    original_key = llm_mod.GROQ_API_KEY
    llm_mod.GROQ_API_KEY = "test-key"

    _call_groq("judge", "", "Evaluate this draft.")

    llm_mod.GROQ_API_KEY = original_key

    payload = mock_post.call_args[1]["json"]
    assert "reasoning_effort" not in payload


def test_call_groq_orchestrator_uses_gpt_model(mocker):
    """Orchestrator role should use the separate gpt-oss-20b model."""
    mock_post = mocker.patch("src.llm_components.requests.post",
                             return_value=_make_groq_response("SIMPLE"))

    import src.llm_components as llm_mod
    original_key = llm_mod.GROQ_API_KEY
    llm_mod.GROQ_API_KEY = "test-key"

    _call_groq("orchestrator", "", "Classify this query.")

    llm_mod.GROQ_API_KEY = original_key

    payload = mock_post.call_args[1]["json"]
    assert payload["model"] == "openai/gpt-oss-20b"


def test_call_groq_strips_think_tags(mocker):
    """Raw think blocks are stripped from the clean response."""
    mocker.patch("src.llm_components.requests.post",
                 return_value=_make_groq_response("<think>Reasoning...</think>Clean answer."))

    import src.llm_components as llm_mod
    original_key = llm_mod.GROQ_API_KEY
    llm_mod.GROQ_API_KEY = "test-key"

    raw, clean, _, _ = _call_groq("rewriter", "", "Some prompt.")

    llm_mod.GROQ_API_KEY = original_key

    assert "<think>" in raw
    assert "<think>" not in clean
    assert clean == "Clean answer."


# ===========================================================================
# _call_groq — 429 retry / backoff
# ===========================================================================

def test_call_groq_retries_on_429(mocker):
    """A 429 response should trigger a retry, and the second attempt succeeds."""
    rate_limit_resp = MagicMock()
    rate_limit_resp.status_code = 429
    rate_limit_resp.headers = {"retry-after": "0"}
    rate_limit_resp.raise_for_status = MagicMock(side_effect=requests.HTTPError("429"))
    rate_limit_resp.json.return_value = {}

    success_resp = _make_groq_response("Success after retry.")

    mock_post = mocker.patch(
        "src.llm_components.requests.post",
        side_effect=[rate_limit_resp, success_resp]
    )
    mocker.patch("src.llm_components._time.sleep")  # don't actually sleep

    import src.llm_components as llm_mod
    original_key = llm_mod.GROQ_API_KEY
    llm_mod.GROQ_API_KEY = "test-key"

    raw, clean, status_code, _ = _call_groq("rewriter", "", "Test prompt.")

    llm_mod.GROQ_API_KEY = original_key

    assert mock_post.call_count == 2
    assert clean == "Success after retry."


def test_call_groq_raises_if_no_api_key(mocker):
    """Should raise ValueError immediately when GROQ_API_KEY is not set."""
    import src.llm_components as llm_mod
    original_key = llm_mod.GROQ_API_KEY
    llm_mod.GROQ_API_KEY = ""

    with pytest.raises(ValueError, match="GROQ_API_KEY is not set"):
        _call_groq("rewriter", "", "Some prompt.")

    llm_mod.GROQ_API_KEY = original_key


# ===========================================================================
# invoke_llm — Groq provider mode
# ===========================================================================

def test_invoke_llm_groq_provider_routes_correctly(mocker):
    """When LLM_PROVIDER=groq, invoke_llm should call _call_groq, not _call_local."""
    mock_groq = mocker.patch(
        "src.llm_components._call_groq",
        return_value=("raw", "Clean Groq response.", 200, 42)
    )
    mock_local = mocker.patch("src.llm_components._call_local")

    import src.llm_components as llm_mod
    original_provider = llm_mod.LLM_PROVIDER
    llm_mod.LLM_PROVIDER = "groq"

    result = invoke_llm("Test prompt.", model_name="ignored", step="rewriter")

    llm_mod.LLM_PROVIDER = original_provider

    mock_groq.assert_called_once_with("rewriter", "", "Test prompt.", image=None)
    mock_local.assert_not_called()
    assert result == "Clean Groq response."


def test_invoke_llm_local_provider_routes_correctly(mocker):
    """When LLM_PROVIDER=local, invoke_llm should call _call_local, not _call_groq."""
    mock_local = mocker.patch(
        "src.llm_components._call_local",
        return_value=("http://local/v1", "raw", "Local response.", 200, 55)
    )
    mock_groq = mocker.patch("src.llm_components._call_groq")

    import src.llm_components as llm_mod
    original_provider = llm_mod.LLM_PROVIDER
    llm_mod.LLM_PROVIDER = "local"

    result = invoke_llm("Test prompt.", model_name=MODEL_GENERATOR, step="drafter")

    llm_mod.LLM_PROVIDER = original_provider

    mock_local.assert_called_once_with(MODEL_GENERATOR, "Test prompt.")
    mock_groq.assert_not_called()
    assert result == "Local response."


def test_invoke_llm_groq_logs_groq_model_name(mocker):
    """DB logger should record the Groq model slug, not the local model_name."""
    mocker.patch(
        "src.llm_components._call_groq",
        return_value=("raw", "Answer.", 200, 10)
    )

    import src.llm_components as llm_mod
    original_provider = llm_mod.LLM_PROVIDER
    llm_mod.LLM_PROVIDER = "groq"

    mock_logger = MagicMock()
    invoke_llm("Prompt.", model_name="Qwen/Qwen3.5-2B", step="drafter", run_logger=mock_logger)

    llm_mod.LLM_PROVIDER = original_provider

    log_call_kwargs = mock_logger.log_llm_call.call_args[1]
    assert log_call_kwargs["model_name"] == "qwen/qwen3.6-27b"
    assert log_call_kwargs["api_url"] == GROQ_API_URL


def test_invoke_llm_groq_logs_orchestrator_model_name(mocker):
    """Orchestrator should log openai/gpt-oss-20b as the model when using Groq."""
    mocker.patch(
        "src.llm_components._call_groq",
        return_value=("raw", "SIMPLE", 200, 10)
    )

    import src.llm_components as llm_mod
    original_provider = llm_mod.LLM_PROVIDER
    llm_mod.LLM_PROVIDER = "groq"

    mock_logger = MagicMock()
    invoke_llm("Classify.", model_name=MODEL_ORCHESTRATOR, step="orchestrator", run_logger=mock_logger)

    llm_mod.LLM_PROVIDER = original_provider

    log_call_kwargs = mock_logger.log_llm_call.call_args[1]
    assert log_call_kwargs["model_name"] == "openai/gpt-oss-20b"


# ===========================================================================
# Existing component tests (local provider — unchanged behaviour)
# ===========================================================================

def test_query_rewriter_formats_prompt(mocker):
    """The Rewriter should combine context messages and the current query into a single string."""
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "What is Messi's current team?"

    mocker.patch("src.llm_components.get_prompt", return_value="Prompt: {history_text} | {query}")

    rewriter = QueryRewriter()
    context = [{"role": "user", "content": "Where does Messi play?"}, {"role": "assistant", "content": "He plays for Inter Miami."}]
    query = "How many goals has he scored there?"

    rewritten = rewriter.rewrite(query=query, context_messages=context)

    assert rewritten == "What is Messi's current team?"
    call_args, call_kwargs = mock_llm.call_args
    assert "Inter Miami" in call_args[0]
    assert query in call_args[0]
    assert call_kwargs["model_name"] == MODEL_GENERATOR


def test_orchestrator_routes_simple_greeting(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "SIMPLE"

    mocker.patch("src.llm_components.get_prompt", return_value="Prompt: {query}")

    orchestrator = Orchestrator()
    route = orchestrator.classify("Hello there!")

    assert route == "SIMPLE"
    assert mock_llm.call_args[1]["model_name"] == MODEL_ORCHESTRATOR


def test_orchestrator_routes_knowledge_query(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "KNOWLEDGE"

    mocker.patch("src.llm_components.get_prompt", return_value="Prompt: {query}")

    orchestrator = Orchestrator()
    route = orchestrator.classify("Who won the 2022 World Cup?")

    assert route == "KNOWLEDGE"


def test_draft_generator_uses_chunks(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "Based on the chunks, Argentina won."

    mocker.patch("src.llm_components.get_prompt", return_value="Prompt: {context_text} | {query}")

    generator = DraftGenerator()
    chunks = [
        {"chunk_id": "1", "document": "Argentina won the 2022 World Cup.", "rrf_score": 0.5}
    ]
    query = "Who won in 2022?"

    draft = generator.generate(query=query, chunks=chunks)

    assert draft == "Based on the chunks, Argentina won."
    call_args, call_kwargs = mock_llm.call_args
    assert "Argentina won the 2022 World Cup" in call_args[0]
    assert query in call_args[0]
    assert call_kwargs["model_name"] == MODEL_GENERATOR


def test_decision_judge_evaluates_pass(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = '{"status": "PASS", "reasoning": "The answer directly addresses the query using the chunks."}'

    mocker.patch("src.llm_components.get_prompt", return_value="Prompt: {context_text} | {query} | {draft}")

    judge = DecisionJudge()
    query = "Who won in 2022?"
    draft = "Argentina won."
    chunks = [{"document": "Argentina won the 2022 World Cup."}]

    result = judge.evaluate(query=query, draft=draft, chunks=chunks)

    assert result["status"] == "PASS"
    assert "reasoning" in result
    assert mock_llm.call_args[1]["model_name"] == MODEL_DECISION


def test_decision_judge_evaluates_fail(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = '{"status": "FAIL", "reasoning": "The answer hallucinates."}'

    mocker.patch("src.llm_components.get_prompt", return_value="Prompt: {context_text} | {query} | {draft}")

    judge = DecisionJudge()
    result = judge.evaluate(query="Who?", draft="I don't know", chunks=[])

    assert result["status"] == "FAIL"
