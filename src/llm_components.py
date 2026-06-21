import json
import logging
import re
import requests
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

OLLAMA_API_URL = "https://e7a8-154-192-139-73.ngrok-free.app/api/generate"

# Model configurations as specified by the user
MODEL_ORCHESTRATOR = "qwen3.5:0.8b"
MODEL_GENERATOR = "qwen3.5:2b"
MODEL_DECISION = "qwen3.5:4b"

# Qwen3 models output <think>...</think> blocks before their actual response.
# We must strip these to get the real answer.
def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by Qwen3 models."""
    stripped = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)
    return stripped.strip()

def invoke_llm(prompt: str, model_name: str) -> str:
    """Invokes the external Ollama API over ngrok."""
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        # Disable thinking mode for Qwen3 models to save time and tokens
        "options": {"think": False}
    }
    try:
        resp = requests.post(
            OLLAMA_API_URL,
            json=payload,
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=120  # Raised from 30s — Qwen3 2b/4b need longer to generate
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
        # Strip any remaining <think> blocks just in case
        clean = _strip_think_tags(raw)
        if not clean:
            logger.warning(f"LLM ({model_name}) returned an empty response after stripping think tags. Raw: {raw[:200]!r}")
        return clean
    except requests.RequestException as e:
        logger.error(f"Error calling LLM API ({model_name}): {e}")
        return ""




class QueryRewriter:
    def rewrite(self, query: str, context_messages: List[Dict[str, str]]) -> str:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in context_messages])
        prompt = f"""Given the following conversation history and a new user query, rewrite the query to be fully self-contained. 
If the user's query is already standalone, return it exactly as is. Do not answer the query.

Conversation History:
{history_text}

User Query: {query}

Rewritten Query:"""
        return invoke_llm(prompt, model_name=MODEL_GENERATOR)

class Orchestrator:
    def classify(self, query: str) -> str:
        prompt = f"""Classify the following user query into one of two categories:
SIMPLE: Greetings, pleasantries, or generic statements that do not require football knowledge.
KNOWLEDGE: Questions or statements requiring football facts, news, or history.

Reply ONLY with the exact word SIMPLE or KNOWLEDGE.

Query: {query}

Classification:"""
        classification = invoke_llm(prompt, model_name=MODEL_ORCHESTRATOR).upper()
        if "KNOWLEDGE" in classification:
            return "KNOWLEDGE"
        return "SIMPLE"

class DraftGenerator:
    def generate(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        context_text = "\n\n".join([f"Source [{c.get('chunk_id', 'unknown')}]:\n{c.get('document', '')}" for c in chunks])
        prompt = f"""You are a football knowledge assistant. Using ONLY the context chunks below, write a clear and complete answer to the query.
Do not invent facts. Do not use outside knowledge. Stick strictly to what is in the sources.
If the context does not contain enough information, say: "The available sources do not contain enough information to answer this question."

Context Chunks:
{context_text}

Query: {query}

Answer (no preamble, answer directly):"""
        return invoke_llm(prompt, model_name=MODEL_GENERATOR)

class DecisionJudge:
    def evaluate(self, query: str, draft: str, chunks: List[Dict[str, Any]]) -> Dict[str, str]:
        context_text = "\n\n".join([c.get("document", "") for c in chunks])
        prompt = f"""You are a fact-checking evaluator. Your job is to verify whether a draft answer is supported by the provided context.

Rules:
- PASS if the draft answer is mostly supported by the context, even if not word-for-word.
- FAIL if the draft answer says the information is not available or cannot be found — this means retrieval failed and should be retried.
- FAIL if the draft answer makes specific factual claims that directly contradict or are completely absent from the context.
- Be LENIENT for partial answers. Prefer PASS over FAIL when there is genuine supporting evidence in the context.

Respond with ONLY a JSON object. Example: {{"status": "PASS", "reasoning": "The answer is supported by the context."}}

Context:
{context_text}

Query: {query}

Draft Answer: {draft}

JSON:"""
        result = invoke_llm(prompt, model_name=MODEL_DECISION)
        try:
            # Try to extract JSON from anywhere in the response
            import re
            json_match = re.search(r'\{.*?\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("No JSON found")
        except Exception:
            # Default to PASS so we don't loop endlessly on small model JSON failures
            status = "FAIL" if "FAIL" in result.upper() and "PASS" not in result.upper() else "PASS"
            return {"status": status, "reasoning": "Fallback parsing applied."}

class HeavyRefiner:
    def refine(self, query: str, draft_answer: str) -> str:
        prompt = f"""Polish the following draft answer. Fix grammar, improve clarity, and use Markdown formatting (bold key names, use bullet lists where appropriate).
Do NOT add any new facts. Do NOT use phrases like "Refined Answer:", "Draft:", or "Journalist's response:". Start your response directly.

Query: {query}

Draft: {draft_answer}

Polished response:"""
        return invoke_llm(prompt, model_name=MODEL_GENERATOR)
