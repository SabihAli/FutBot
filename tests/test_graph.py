import pytest
from typing import TypedDict, List, Dict, Any
from src.graph import (
    GraphState,
    orchestrator_node,
    simple_responder_node,
    rewrite_node,
    retrieve_node,
    draft_node,
    judge_node,
    route_after_orchestrator,
    route_after_judge,
    build_graph,
)

# ---------------------------------------------------------------------------
# Node Tests
# ---------------------------------------------------------------------------

def test_rewrite_node(mocker):
    mocker.patch("src.graph.QueryRewriter.rewrite", return_value="Rewritten Query")
    state: GraphState = {"query": "He did", "context_messages": [{"role": "user", "content": "Did Messi score?"}]}
    
    new_state = rewrite_node(state)
    assert new_state["rewritten_query"] == "Rewritten Query"

def test_orchestrator_node(mocker):
    # Mock the classify method
    mocker.patch("src.graph.Orchestrator.classify", return_value="KNOWLEDGE")
    state: GraphState = {"rewritten_query": "Who won?", "context_messages": []}
    
    new_state = orchestrator_node(state)
    assert new_state["classification"] == "KNOWLEDGE"

def test_simple_responder_node(mocker):
    mocker.patch("src.graph.invoke_llm", return_value="Hello! I am a football bot.")
    mocker.patch("src.graph.get_prompt", return_value="Prompt: {query}")
    state: GraphState = {"rewritten_query": "Hi"}
    
    new_state = simple_responder_node(state)
    assert new_state["final_answer"] == "Hello! I am a football bot."

def test_retrieve_node(mocker):
    mocker.patch("src.graph.reciprocal_rank_fusion", return_value=[{"document": "Messi scored."}])
    state: GraphState = {"rewritten_query": "Did Messi score?"}
    
    new_state = retrieve_node(state)
    assert len(new_state["retrieved_chunks"]) == 1
    assert new_state["retrieved_chunks"][0]["document"] == "Messi scored."

def test_draft_node(mocker):
    mocker.patch("src.graph.DraftGenerator.generate", return_value="Draft answer")
    state: GraphState = {"rewritten_query": "Q", "retrieved_chunks": []}
    
    new_state = draft_node(state)
    assert new_state["draft_answer"] == "Draft answer"

def test_judge_node_initial_try(mocker):
    mocker.patch("src.graph.DecisionJudge.evaluate", return_value={"status": "FAIL", "reasoning": "Missing info"})
    state: GraphState = {"rewritten_query": "Q", "draft_answer": "D", "retrieved_chunks": [], "retry_count": 0}
    
    new_state = judge_node(state)
    assert new_state["judge_status"] == "FAIL"
    assert new_state["judge_reasoning"] == "Missing info"
    assert new_state["retry_count"] == 1


# ---------------------------------------------------------------------------
# Routing Tests
# ---------------------------------------------------------------------------

def test_route_after_orchestrator():
    assert route_after_orchestrator({"classification": "SIMPLE"}) == "simple"
    assert route_after_orchestrator({"classification": "KNOWLEDGE"}) == "knowledge"

def test_route_after_judge_pass():
    state: GraphState = {"judge_status": "PASS", "retry_count": 1}
    assert route_after_judge(state) == "pass"

def test_route_after_judge_fail_can_retry():
    state: GraphState = {"judge_status": "FAIL", "retry_count": 2}
    assert route_after_judge(state) == "retry"

def test_route_after_judge_fail_max_retries():
    state: GraphState = {"judge_status": "FAIL", "retry_count": 3}
    assert route_after_judge(state) == "max_retries"


# ---------------------------------------------------------------------------
# Graph Compilation Test
# ---------------------------------------------------------------------------
def test_build_graph_compiles_without_errors():
    graph = build_graph()
    assert graph is not None
