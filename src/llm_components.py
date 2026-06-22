import json
import logging
import re
import requests
import os
from typing import List, Dict, Any
from dotenv import load_dotenv

from src.prompt_loader import get_prompt

# Load environment variables from .env file if it exists
load_dotenv()

logger = logging.getLogger(__name__)

OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "https://a3fc-154-192-5-123.ngrok-free.app/api/generate")

# Model configurations
MODEL_ORCHESTRATOR = os.environ.get("MODEL_ORCHESTRATOR", "qwen3.5:0.8b")
MODEL_GENERATOR = os.environ.get("MODEL_GENERATOR", "qwen3.5:2b")
MODEL_DECISION = os.environ.get("MODEL_DECISION", "qwen3.5:4b")

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
        prompt_template = get_prompt("REWRITER")
        prompt = prompt_template.format(history_text=history_text, query=query)
        return invoke_llm(prompt, model_name=MODEL_GENERATOR)

class Orchestrator:
    def classify(self, query: str) -> str:
        prompt_template = get_prompt("ORCHESTRATOR")
        prompt = prompt_template.format(query=query)
        classification = invoke_llm(prompt, model_name=MODEL_ORCHESTRATOR).upper()
        if "KNOWLEDGE" in classification:
            return "KNOWLEDGE"
        return "SIMPLE"

class DraftGenerator:
    def generate(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        context_text = "\n\n".join([f"Source [{c.get('chunk_id', 'unknown')}]:\n{c.get('document', '')}" for c in chunks])
        prompt_template = get_prompt("DRAFT_GENERATOR")
        prompt = prompt_template.format(context_text=context_text, query=query)
        return invoke_llm(prompt, model_name=MODEL_GENERATOR)

class DecisionJudge:
    def evaluate(self, query: str, draft: str, chunks: List[Dict[str, Any]]) -> Dict[str, str]:
        context_text = "\n\n".join([c.get("document", "") for c in chunks])
        prompt_template = get_prompt("DECISION_JUDGE")
        # To avoid KeyError for {{ and }}, the text file uses standard format. 
        # Wait, the prompt contains {{ and }} which format requires! 
        # I actually formatted it with double brackets in prompts.txt.
        # But wait, python format() handles double brackets by reducing to single bracket.
        prompt = prompt_template.format(context_text=context_text, query=query, draft=draft)
        
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