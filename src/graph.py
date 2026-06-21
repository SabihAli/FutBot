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
    HeavyRefiner,
)
from src.retriever import reciprocal_rank_fusion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    query: str
    context_messages: List[Dict[str, str]]
    
    classification: str
    rewritten_query: str
    retrieved_chunks: List[Dict[str, Any]]
    
    draft_answer: str
    judge_status: str
    judge_reasoning: str
    retry_count: int
    reached_max_retries: bool
    
    final_answer: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def orchestrator_node(state: GraphState) -> GraphState:
    classifier = Orchestrator()
    classification = classifier.classify(state.get("query", ""))
    return {"classification": classification}

def simple_responder_node(state: GraphState) -> GraphState:
    prompt = f"Respond naturally to this user greeting or simple statement:\n{state.get('query', '')}"
    answer = invoke_llm(prompt, model_name=MODEL_GENERATOR)
    return {"final_answer": answer}

def rewrite_node(state: GraphState) -> GraphState:
    rewriter = QueryRewriter()
    # On retries, we might want to modify the rewrite, but for now we keep it standard.
    # Alternatively, the retry could just fetch different documents.
    query = state.get("query", "")
    context = state.get("context_messages", [])
    rewritten = rewriter.rewrite(query, context)
    return {"rewritten_query": rewritten}

def retrieve_node(state: GraphState) -> GraphState:
    query = state.get("rewritten_query", "")
    
    try:
        # Import dynamically to avoid circular imports during testing
        from src.api import global_chroma, global_bm25
        
        # Query both retrievers
        dense_results = global_chroma.query(query, top_k=5)
        
        # BM25 might raise an error if index isn't built yet
        try:
            sparse_results = global_bm25.search(query, top_k=5)
        except RuntimeError:
            sparse_results = []
            
        chunks = reciprocal_rank_fusion(dense_results, sparse_results)
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        chunks = []
        
    return {"retrieved_chunks": chunks}

def draft_node(state: GraphState) -> GraphState:
    generator = DraftGenerator()
    draft = generator.generate(state.get("rewritten_query", ""), state.get("retrieved_chunks", []))
    return {"draft_answer": draft}

def judge_node(state: GraphState) -> GraphState:
    judge = DecisionJudge()
    result = judge.evaluate(
        state.get("rewritten_query", ""), 
        state.get("draft_answer", ""), 
        state.get("retrieved_chunks", [])
    )
    
    current_retries = state.get("retry_count", 0)
    return {
        "judge_status": result.get("status", "FAIL"),
        "judge_reasoning": result.get("reasoning", ""),
        "retry_count": current_retries + 1
    }

def refine_node(state: GraphState) -> GraphState:
    refiner = HeavyRefiner()
    reached_max = state.get("judge_status") == "FAIL"
    
    if reached_max:
        draft = state.get("draft_answer", "I'm sorry, I couldn't find a confident answer in the retrieved documents.")
    else:
        draft = state.get("draft_answer", "")
        
    final = refiner.refine(state.get("query", ""), draft)
    return {"final_answer": final, "reached_max_retries": reached_max}


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
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("simple_responder", simple_responder_node)
    workflow.add_node("rewriter", rewrite_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("drafter", draft_node)
    workflow.add_node("judge", judge_node)
    workflow.add_node("refiner", refine_node)
    
    # Entry Point
    workflow.set_entry_point("orchestrator")
    
    # Edges
    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "simple": "simple_responder",
            "knowledge": "rewriter"
        }
    )
    
    workflow.add_edge("simple_responder", END)
    
    workflow.add_edge("rewriter", "retriever")
    workflow.add_edge("retriever", "drafter")
    workflow.add_edge("drafter", "judge")
    
    workflow.add_conditional_edges(
        "judge",
        route_after_judge,
        {
            "pass": "refiner",
            "max_retries": "refiner",
            "retry": "rewriter"  # Loop back to rewrite (or retrieve) if failed
        }
    )
    
    workflow.add_edge("refiner", END)
    
    # Compile
    return workflow.compile()


# ---------------------------------------------------------------------------
# Execution Helper
# ---------------------------------------------------------------------------
def run_pipeline(query: str, context_messages: Optional[List[Dict[str, str]]] = None) -> str:
    """Convenience function to run the full RAG pipeline for a given query."""
    if context_messages is None:
        context_messages = []
        
    app = build_graph()
    initial_state: GraphState = {
        "query": query,
        "context_messages": context_messages,
        "retry_count": 0
    }
    
    # Run the graph
    result = app.invoke(initial_state)
    
    answer = result.get("final_answer", "Error: No answer generated.")
    
    # If we hit max retries without a PASS, append a user-visible warning
    if result.get("reached_max_retries"):
        answer += "\n\n⚠️ WARNING: No decisive answer was found in the available sources. This result should be independently verified."
    
    return answer
