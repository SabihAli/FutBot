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

# Model configurations
MODEL_ORCHESTRATOR = os.environ.get("MODEL_ORCHESTRATOR", "Qwen/Qwen3.5-0.8B")
MODEL_GENERATOR = os.environ.get("MODEL_GENERATOR", "Qwen/Qwen3.5-2B")
MODEL_DECISION = os.environ.get("MODEL_DECISION", "Qwen/Qwen3.5-4B")

# Model-specific API endpoints
URL_08B = os.environ.get("URL_08B", "https://3ed4-2407-d000-2b-3df3-26d-b720-e3f1-5827.ngrok-free.app/v1/chat/completions")
URL_2B = os.environ.get("URL_2B", "https://6006-154-192-5-123.ngrok-free.app/v1/chat/completions")
URL_4B = os.environ.get("URL_4B", "https://19d9-154-192-5-123.ngrok-free.app/v1/chat/completions")
# URL_4B = os.environ.get("URL_2B", "https://6006-154-192-5-123.ngrok-free.app/v1/chat/completions")

# Qwen3 models output <think>...</think> blocks before their actual response.

# We must strip these to get the real answer.
def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by Qwen3 models."""
    stripped = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)
    return stripped.strip()

def invoke_llm(
    prompt: str,
    model_name: str,
    step: str = "unknown",
    run_logger=None,
    iteration: int = 0,
) -> str:
    """Invokes the external API over ngrok."""
    import time as _time
    model_name_lower = model_name.lower()
    if "0.8b" in model_name_lower:
        api_url = URL_08B
    elif "2b" in model_name_lower:
        api_url = URL_2B
    elif "4b" in model_name_lower:
        api_url = URL_4B
    else:
        api_url = URL_2B

    # Format payload based on endpoint type
    if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "stream": False
        }
    else:
        # Legacy Ollama API format
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"think": False}
        }

    status_code = None
    raw = ""
    clean = ""
    latency_ms = None
    t0 = _time.monotonic()
    try:
        resp = requests.post(
            api_url,
            json=payload,
            timeout=120  # Raised from 30s — Qwen3 2b/4b need longer to generate
        )
        latency_ms = int((_time.monotonic() - t0) * 1000)
        status_code = resp.status_code
        resp.raise_for_status()

        # Parse response based on endpoint type
        if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
            raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            raw = resp.json().get("response", "").strip()

        # Strip any remaining <think> blocks just in case
        clean = _strip_think_tags(raw)
        if not clean:
            logger.warning(f"LLM ({model_name}) returned an empty response after stripping think tags. Raw: {raw[:200]!r}")
        return clean
    except requests.RequestException as e:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        logger.error(f"Error calling LLM API ({model_name}) at {api_url}: {e}")
        return ""
    finally:
        if run_logger is not None:
            try:
                run_logger.log_llm_call(
                    step=step,
                    model_name=model_name,
                    prompt=prompt,
                    raw_response=raw,
                    response=clean,
                    api_url=api_url,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    iteration=iteration,
                )
            except Exception as log_err:
                logger.warning(f"Failed to log LLM call: {log_err}")


class QueryRewriter:
    def rewrite(
        self,
        query: str,
        context_messages: List[Dict[str, str]],
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in context_messages])
        prompt_template = get_prompt("REWRITER")
        prompt = prompt_template.format(history_text=history_text, query=query)
        return invoke_llm(
            prompt,
            model_name=MODEL_GENERATOR,
            step="rewriter",
            run_logger=run_logger,
            iteration=iteration,
        )

class Orchestrator:
    def classify(
        self,
        query: str,
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        prompt_template = get_prompt("ORCHESTRATOR")
        prompt = prompt_template.format(query=query)
        classification = invoke_llm(
            prompt,
            model_name=MODEL_ORCHESTRATOR,
            step="orchestrator",
            run_logger=run_logger,
            iteration=iteration,
        ).upper()
        if "KNOWLEDGE" in classification:
            return "KNOWLEDGE"
        return "SIMPLE"

class DraftGenerator:
    def generate(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        context_text = "\n\n".join([f"Source [{c.get('chunk_id', 'unknown')}]:\n{c.get('document', '')}" for c in chunks])
        prompt_template = get_prompt("DRAFT_GENERATOR")
        prompt = prompt_template.format(context_text=context_text, query=query)
        return invoke_llm(
            prompt,
            model_name=MODEL_GENERATOR,
            step="drafter",
            run_logger=run_logger,
            iteration=iteration,
        )

class DecisionJudge:
    def evaluate(
        self,
        query: str,
        draft: str,
        chunks: List[Dict[str, Any]],
        run_logger=None,
        iteration: int = 0,
    ) -> Dict[str, str]:
        context_text = "\n\n".join([c.get("document", "") for c in chunks])
        prompt_template = get_prompt("DECISION_JUDGE")
        # To avoid KeyError for {{ and }}, the text file uses standard format.
        # Wait, the prompt contains {{ and }} which format requires!
        # I actually formatted it with double brackets in prompts.txt.
        # But wait, python format() handles double brackets by reducing to single bracket.
        prompt = prompt_template.format(context_text=context_text, query=query, draft=draft)

        result = invoke_llm(
            prompt,
            model_name=MODEL_DECISION,
            step="judge",
            run_logger=run_logger,
            iteration=iteration,
        )
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