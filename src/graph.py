import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

from src.llm_components import (
    invoke_llm,
    MODEL_GENERATOR,
    QueryRewriter,
    Orchestrator,
    DraftGenerator,
    DecisionJudge,
    SnapshotCompressor,
)
from src.context import ConversationContext
from src.retriever import reciprocal_rank_fusion
from src.db_logger import PipelineRunLogger, log_pipeline_trace

from src.prompt_loader import get_prompt, get_prompt_parts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    query: str
    session_id: str
    run_logger: Any

    all_messages: List[Dict[str, str]]
    snapshot: str
    snapshot_turn_count: int
    context_messages: List[Dict[str, str]]

    classification: str
    rewritten_query: str
    retrieved_chunks: List[Dict[str, Any]]

    draft_answer: str
    judge_status: str
    judge_reasoning: str
    retry_count: int
    reached_max_retries: bool
    loop_traces: List[Dict[str, Any]]

    # Internal iteration DB ID (for linking retrieval back to the iteration row)
    current_iteration_id: Optional[int]

    final_answer: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def compressor_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")

    ctx = ConversationContext.from_graph_fields(
        session_id=state.get("session_id", ""),
        messages=state.get("all_messages", []),
        snapshot=state.get("snapshot", ""),
        snapshot_turn_count=state.get("snapshot_turn_count", 0),
    )

    ctx.maintain_snapshot(SnapshotCompressor(), run_logger=run_logger)

    return ctx.to_graph_fields()


def rewrite_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    retry_count = state.get("retry_count", 0)
    iteration = retry_count + 1  # 1-indexed

    rewriter = QueryRewriter()
    query = state.get("query", "")
    context = state.get("context_messages", [])
    rewritten = rewriter.rewrite(
        query,
        context,
        snapshot=state.get("snapshot") or "{}",
        run_logger=run_logger,
        iteration=iteration,
    )

    # Log the start of this loop iteration
    iteration_id = None
    if run_logger is not None:
        try:
            iteration_id = run_logger.log_iteration(
                iteration=iteration,
                rewritten_query=rewritten,
            )
        except Exception as e:
            logger.warning(f"Failed to log iteration: {e}")

    traces = state.get("loop_traces", [])
    traces.append({"rewritten_query": rewritten})

    return {
        "rewritten_query": rewritten,
        "loop_traces": traces,
        "current_iteration_id": iteration_id,
    }

def orchestrator_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1

    classifier = Orchestrator()
    classification = classifier.classify(
        state.get("rewritten_query", state.get("query", "")),
        run_logger=run_logger,
        iteration=iteration,
    )
    return {"classification": classification}

def simple_responder_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1

    system_prompt, user_template = get_prompt_parts("SIMPLE_RESPONDER")
    user_content = user_template.format(query=state.get("rewritten_query", state.get("query", "")))
    answer = invoke_llm(
        user_content,
        model_name=MODEL_GENERATOR,
        step="simple_responder",
        run_logger=run_logger,
        iteration=iteration,
        system_prompt=system_prompt,
    )

    return {"final_answer": answer}

def retrieve_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    query = state.get("rewritten_query", "")
    iteration = state.get("retry_count", 0) + 1
    iteration_id = state.get("current_iteration_id")

    dense_results = []
    sparse_results = []
    chunks = []

    try:
        from src.api import global_chroma, global_bm25

        dense_results = global_chroma.query(query, top_k=15)

        try:
            sparse_results = global_bm25.search(query, top_k=15)
        except RuntimeError:
            sparse_results = []

        chunks = reciprocal_rank_fusion(dense_results, sparse_results)
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        chunks = []

    # Log retrieval event
    if run_logger is not None:
        try:
            run_logger.log_retrieval(
                query_used=query,
                fused_chunks=chunks,
                dense_count=len(dense_results),
                sparse_count=len(sparse_results),
                iteration=iteration,
                iteration_id=iteration_id,
            )
        except Exception as e:
            logger.warning(f"Failed to log retrieval: {e}")

    chunk_ids = [c.get("chunk_id", "unknown") for c in chunks]
    traces = state.get("loop_traces", [])
    if traces:
        traces[-1]["retrieved_chunk_ids"] = chunk_ids

    return {"retrieved_chunks": chunks, "loop_traces": traces}

def draft_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1

    generator = DraftGenerator()
    draft = generator.generate(
        state.get("rewritten_query", ""),
        state.get("retrieved_chunks", []),
        run_logger=run_logger,
        iteration=iteration,
    )
    return {"draft_answer": draft}

def judge_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1
    iteration_id = state.get("current_iteration_id")

    judge = DecisionJudge()
    result = judge.evaluate(
        state.get("rewritten_query", ""),
        state.get("draft_answer", ""),
        state.get("retrieved_chunks", []),
        run_logger=run_logger,
        iteration=iteration,
    )

    current_retries = state.get("retry_count", 0)
    traces = state.get("loop_traces", [])

    status = result.get("status", "FAIL")
    reasoning = result.get("reasoning", "")

    if traces:
        traces[-1]["judge_status"] = status
        traces[-1]["judge_reasoning"] = reasoning

    # Update iteration row with judge outcome
    if run_logger is not None and iteration_id is not None:
        try:
            run_logger.update_iteration(
                iteration_id=iteration_id,
                judge_status=status,
                judge_reasoning=reasoning,
            )
        except Exception as e:
            logger.warning(f"Failed to update iteration: {e}")

    reached_max = (status == "FAIL" and current_retries >= 2)

    return {
        "judge_status": status,
        "judge_reasoning": reasoning,
        "retry_count": current_retries + 1,
        "loop_traces": traces,
        "final_answer": state.get("draft_answer", ""),
        "reached_max_retries": reached_max
    }

# ---------------------------------------------------------------------------
# Conditional Edges
# ---------------------------------------------------------------------------
def route_after_orchestrator(state: GraphState) -> str:
    if state.get("classification") == "SIMPLE":
        return "simple"
    return "knowledge"

def route_after_judge(state: GraphState) -> str:
    status = state.get("judge_status", "FAIL")
    retries = state.get("retry_count", 0)

    if status == "PASS":
        return "pass"
    elif retries >= 3:
        return "max_retries"
    else:
        return "retry"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------
def build_graph():
    workflow = StateGraph(GraphState)

    # Add Nodes
    workflow.add_node("compressor", compressor_node)
    workflow.add_node("rewriter", rewrite_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("simple_responder", simple_responder_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("drafter", draft_node)
    workflow.add_node("judge", judge_node)

    # Entry point: eager snapshot maintenance before rewrite
    workflow.set_entry_point("compressor")

    # Edges
    workflow.add_edge("compressor", "rewriter")
    workflow.add_edge("rewriter", "orchestrator")

    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "simple": "simple_responder",
            "knowledge": "retriever"
        }
    )

    workflow.add_edge("simple_responder", END)

    workflow.add_edge("retriever", "drafter")
    workflow.add_edge("drafter", "judge")

    workflow.add_conditional_edges(
        "judge",
        route_after_judge,
        {
            "pass": END,
            "max_retries": END,
            "retry": "rewriter"  # Loop back to rewrite (or retrieve) if failed
        }
    )

    # Compile
    return workflow.compile()


# ---------------------------------------------------------------------------
# Execution Helper
# ---------------------------------------------------------------------------
def run_pipeline(
    query: str,
    context_messages: Optional[List[Dict[str, str]]] = None,
    session_id: str = "",
    snapshot: str = "",
    snapshot_turn_count: int = 0,
) -> tuple[str, str, int]:
    """Run the full RAG pipeline. Returns (answer, snapshot, snapshot_turn_count)."""
    if context_messages is None:
        context_messages = []

    app = build_graph()

    with PipelineRunLogger(original_query=query, session_id=session_id) as run_logger:
        initial_state: GraphState = {
            "query": query,
            "all_messages": context_messages,
            "snapshot": snapshot,
            "snapshot_turn_count": snapshot_turn_count,
            "context_messages": [],
            "session_id": session_id,
            "run_logger": run_logger,
            "retry_count": 0,
            "loop_traces": [],
            "current_iteration_id": None,
        }

        # Run the graph
        result = app.invoke(initial_state)

        answer = result.get("final_answer", "Error: No answer generated.")
        result_snapshot = result.get("snapshot", snapshot)
        result_turn_count = result.get("snapshot_turn_count", snapshot_turn_count)

        # If we hit max retries without a PASS, append a user-visible warning
        if result.get("reached_max_retries"):
            answer += "\n\nWARNING: No decisive answer was found in the available sources. This result should be independently verified."

        snapshot_token_count = len(result_snapshot.split()) if result_snapshot else 0

        # Finalize the run record
        try:
            run_logger.finish(
                classification=result.get("classification", "UNKNOWN"),
                total_iterations=result.get("retry_count", 0),
                final_answer=answer,
                reached_max_retries=bool(result.get("reached_max_retries")),
                snapshot_text=result_snapshot,
                snapshot_token_count=snapshot_token_count,
            )
        except Exception as e:
            logger.error(f"Failed to finalize run log: {e}")

    return answer, result_snapshot, result_turn_count
