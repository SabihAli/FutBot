import pytest
from src.llm_components import (
    QueryRewriter,
    Orchestrator,
    DraftGenerator,
    DecisionJudge,
    HeavyRefiner,
    MODEL_ORCHESTRATOR,
    MODEL_GENERATOR,
    MODEL_DECISION,
)

# ---------------------------------------------------------------------------
# Query Rewriter
# ---------------------------------------------------------------------------
def test_query_rewriter_formats_prompt(mocker):
    """The Rewriter should combine context messages and the current query into a single string."""
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "What is Messi's current team?"

    rewriter = QueryRewriter()
    context = [{"role": "user", "content": "Where does Messi play?"}, {"role": "assistant", "content": "He plays for Inter Miami."}]
    query = "How many goals has he scored there?"

    rewritten = rewriter.rewrite(query=query, context_messages=context)

    assert rewritten == "What is Messi's current team?"
    # Ensure the LLM was called with the right model and a prompt containing the history and query
    call_args, call_kwargs = mock_llm.call_args
    assert "Inter Miami" in call_args[0]
    assert query in call_args[0]
    assert call_kwargs["model_name"] == MODEL_GENERATOR


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def test_orchestrator_routes_simple_greeting(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "SIMPLE"

    orchestrator = Orchestrator()
    route = orchestrator.classify("Hello there!")

    assert route == "SIMPLE"
    assert mock_llm.call_args[1]["model_name"] == MODEL_ORCHESTRATOR


def test_orchestrator_routes_knowledge_query(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "KNOWLEDGE"

    orchestrator = Orchestrator()
    route = orchestrator.classify("Who won the 2022 World Cup?")

    assert route == "KNOWLEDGE"


# ---------------------------------------------------------------------------
# Draft Generator
# ---------------------------------------------------------------------------
def test_draft_generator_uses_chunks(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "Based on the chunks, Argentina won."

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


# ---------------------------------------------------------------------------
# Decision Judge
# ---------------------------------------------------------------------------
def test_decision_judge_evaluates_pass(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    # Return JSON-like string
    mock_llm.return_value = '{"status": "PASS", "reasoning": "The answer directly addresses the query using the chunks."}'

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

    judge = DecisionJudge()
    result = judge.evaluate(query="Who?", draft="I don't know", chunks=[])

    assert result["status"] == "FAIL"


# ---------------------------------------------------------------------------
# Heavy Refiner
# ---------------------------------------------------------------------------
def test_heavy_refiner_polishes_answer(mocker):
    mock_llm = mocker.patch("src.llm_components.invoke_llm")
    mock_llm.return_value = "Here is a polished answer: Argentina won."

    refiner = HeavyRefiner()
    draft = "Argentina won."
    query = "Who won?"

    final = refiner.refine(query=query, draft_answer=draft)

    assert final == "Here is a polished answer: Argentina won."
    call_args, call_kwargs = mock_llm.call_args
    assert draft in call_args[0]
    assert query in call_args[0]
    assert call_kwargs["model_name"] == MODEL_GENERATOR
