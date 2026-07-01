import json
import logging
import random
import re
import requests
import os
import time as _time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from src.config import SNAPSHOT_MAX_TOKENS
from src.prompt_loader import get_prompt, get_prompt_parts

# Load environment variables from .env file if it exists
load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider Configuration
# ---------------------------------------------------------------------------

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "local").lower()  # "local" | "groq"
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MAX_RETRIES = int(os.environ.get("GROQ_MAX_RETRIES", "5"))
GROQ_BACKOFF_BASE = float(os.environ.get("GROQ_BACKOFF_BASE", "1.5"))

# ---------------------------------------------------------------------------
# Local Model Configurations (unchanged)
# ---------------------------------------------------------------------------

MODEL_ORCHESTRATOR = os.environ.get("MODEL_ORCHESTRATOR", "Qwen/Qwen3.5-0.8B")
MODEL_GENERATOR = os.environ.get("MODEL_GENERATOR", "Qwen/Qwen3.5-2B")
MODEL_DECISION = os.environ.get("MODEL_DECISION", "Qwen/Qwen3.5-4B")

# Model-specific API endpoints (local/ngrok)
URL_08B = os.environ.get("URL_08B", "https://3ed4-2407-d000-2b-3df3-26d-b720-e3f1-5827.ngrok-free.app/v1/chat/completions")
URL_2B = os.environ.get("URL_2B", "https://6006-154-192-5-123.ngrok-free.app/v1/chat/completions")
URL_4B = os.environ.get("URL_4B", "https://19d9-154-192-5-123.ngrok-free.app/v1/chat/completions")

# ---------------------------------------------------------------------------
# Groq Model Mapping (role → model slug)
# ---------------------------------------------------------------------------

# qwen/qwen3.6-27b: current highest-intelligence model on Groq free tier.
# Supports thinking/non-thinking toggle, multimodal input, 262K context.
_GROQ_MODEL_MAIN = os.environ.get("GROQ_MODEL_MAIN", "qwen/qwen3.6-27b")
_GROQ_MODEL_ORCHESTRATOR = os.environ.get("GROQ_MODEL_ORCHESTRATOR", "openai/gpt-oss-20b")

# Maps the `step` argument from invoke_llm() to the Groq model slug.
GROQ_MODEL_MAP: Dict[str, str] = {
    "orchestrator":     _GROQ_MODEL_ORCHESTRATOR,  # separate budget from main model
    "rewriter":         _GROQ_MODEL_MAIN,
    "compressor":       _GROQ_MODEL_MAIN,
    "drafter":          _GROQ_MODEL_MAIN,
    "simple_responder": _GROQ_MODEL_MAIN,
    "judge":            _GROQ_MODEL_MAIN,
}

# Only the Decision Judge uses thinking mode.
GROQ_THINKING_ROLES = {"judge"}


# ---------------------------------------------------------------------------
# Shared: <think> tag stripping
# ---------------------------------------------------------------------------

def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by Qwen3 models."""
    stripped = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)
    return stripped.strip()


# ---------------------------------------------------------------------------
# Groq Backend
# ---------------------------------------------------------------------------

def _call_groq(
    role: str,
    system_prompt: str,
    user_content: str,
    image: Optional[bytes] = None,
) -> tuple[str, str, int | None, int]:
    """
    Call the Groq API for the given role.

    Returns (raw_response, clean_response, status_code, latency_ms).

    Implements exponential backoff with jitter on HTTP 429.

    Thinking mode is disabled for non-judge roles by adding `reasoning_effort="none"`
    (or `"low"` for GPT models) to the payload. For the judge role, this parameter
    is omitted so the model defaults to thinking mode.
    """
    if not GROQ_API_KEY:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment when using LLM_PROVIDER=groq."
        )

    model = GROQ_MODEL_MAP.get(role, _GROQ_MODEL_MAIN)
    thinking = role in GROQ_THINKING_ROLES

    # Build user message content (supports optional image attachment)
    if image is not None:
        import base64
        img_b64 = base64.b64encode(image).decode("utf-8")
        user_msg_content = [
            {"type": "text", "text": user_content},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]
    else:
        user_msg_content = user_content

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg_content},
    ]

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    if not thinking:
        if "gpt" in model.lower():
            payload["reasoning_effort"] = "low"
        else:
            payload["reasoning_effort"] = "none"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    raw = ""
    clean = ""
    status_code: int | None = None
    t0 = _time.monotonic()

    for attempt in range(GROQ_MAX_RETRIES):
        try:
            resp = requests.post(
                GROQ_API_URL,
                json=payload,
                headers=headers,
                timeout=120,
            )
            status_code = resp.status_code

            if resp.status_code == 429:
                retry_after = float(
                    resp.headers.get("retry-after", GROQ_BACKOFF_BASE ** attempt)
                )
                wait = retry_after + random.uniform(0, 0.5)
                logger.warning(
                    f"Groq 429 on attempt {attempt + 1}/{GROQ_MAX_RETRIES}. "
                    f"Waiting {wait:.2f}s (retry-after={retry_after})."
                )
                _time.sleep(wait)
                continue

            resp.raise_for_status()

            choices = resp.json().get("choices", [{}])
            raw = choices[0].get("message", {}).get("content", "").strip()
            clean = _strip_think_tags(raw)

            if not clean:
                logger.warning(
                    f"Groq ({model}, role={role}) returned empty response after "
                    f"stripping think tags. Raw: {raw[:200]!r}"
                )

            latency_ms = int((_time.monotonic() - t0) * 1000)
            return raw, clean, status_code, latency_ms

        except requests.RequestException as e:
            latency_ms = int((_time.monotonic() - t0) * 1000)
            logger.error(f"Groq API request error (attempt {attempt + 1}): {e}")
            if attempt == GROQ_MAX_RETRIES - 1:
                return raw, clean, status_code, latency_ms
            _time.sleep(GROQ_BACKOFF_BASE ** attempt + random.uniform(0, 0.5))

    latency_ms = int((_time.monotonic() - t0) * 1000)
    return raw, clean, status_code, latency_ms


# ---------------------------------------------------------------------------
# Local Backend
# ---------------------------------------------------------------------------

def _call_local(
    model_name: str,
    prompt: str,
) -> tuple[str, str, str, int | None, int]:
    """
    Call the local Ollama/ngrok endpoint.

    Returns (api_url, raw_response, clean_response, status_code, latency_ms).
    """
    model_name_lower = model_name.lower()
    if "0.8b" in model_name_lower:
        api_url = URL_08B
    elif "2b" in model_name_lower:
        api_url = URL_2B
    elif "4b" in model_name_lower:
        api_url = URL_4B
    else:
        api_url = URL_2B

    if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
    else:
        # Legacy Ollama API format
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"think": False},
        }

    raw = ""
    clean = ""
    status_code: int | None = None
    t0 = _time.monotonic()

    try:
        resp = requests.post(api_url, json=payload, timeout=120)
        status_code = resp.status_code
        resp.raise_for_status()

        if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
            raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            raw = resp.json().get("response", "").strip()

        clean = _strip_think_tags(raw)
        if not clean:
            logger.warning(
                f"LLM ({model_name}) returned an empty response after stripping think tags. "
                f"Raw: {raw[:200]!r}"
            )

        latency_ms = int((_time.monotonic() - t0) * 1000)
        return api_url, raw, clean, status_code, latency_ms

    except requests.RequestException as e:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        logger.error(f"Error calling local LLM API ({model_name}) at {api_url}: {e}")
        return api_url, raw, clean, status_code, latency_ms


# ---------------------------------------------------------------------------
# Provider-Aware Dispatcher — public interface (signature unchanged)
# ---------------------------------------------------------------------------

def invoke_llm(
    prompt: str,
    model_name: str,
    step: str = "unknown",
    run_logger=None,
    iteration: int = 0,
    image: Optional[bytes] = None,
    system_prompt: Optional[str] = None,
) -> str:
    """
    Provider-aware LLM dispatcher.

    When LLM_PROVIDER=local  → calls the local Ollama/ngrok endpoint using `model_name`.
                               `system_prompt` is prepended to `prompt` separated by two
                               newlines so local models still receive all instructions.
    When LLM_PROVIDER=groq   → calls the Groq API, selecting the model from GROQ_MODEL_MAP
                               by `step` (role). `system_prompt` goes in role:system;
                               `prompt` goes in role:user.

    All existing call sites remain identical — `system_prompt` defaults to None and the
    combined `prompt` string is used as a fallback for both providers.
    """
    raw = ""
    clean = ""
    api_url = ""
    status_code: int | None = None
    latency_ms = 0

    if LLM_PROVIDER == "groq":
        api_url = GROQ_API_URL
        groq_model = GROQ_MODEL_MAP.get(step, _GROQ_MODEL_MAIN)
        # If a dedicated system_prompt was supplied use it; otherwise treat the
        # whole prompt as user content with a minimal system message.
        sys_msg = system_prompt if system_prompt is not None else ""
        raw, clean, status_code, latency_ms = _call_groq(
            step, sys_msg, prompt, image=image
        )
        log_model_name = groq_model
    else:
        # Local path: merge system_prompt into the prompt string if provided
        local_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        api_url, raw, clean, status_code, latency_ms = _call_local(model_name, local_prompt)
        log_model_name = model_name

    if run_logger is not None:
        try:
            run_logger.log_llm_call(
                step=step,
                model_name=log_model_name,
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

    return clean


# ---------------------------------------------------------------------------
# Pipeline Components
# ---------------------------------------------------------------------------

class SnapshotCompressor:
    """Stateless LLM adapter for incremental JSON snapshot compression."""

    def compress_incremental(
        self,
        existing_snapshot: str,
        new_messages: List[Dict[str, str]],
        run_logger=None,
    ) -> str:
        newly_aged_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in new_messages
        )
        system_prompt, user_template = get_prompt_parts("COMPRESSOR")
        system_prompt = system_prompt.format(max_tokens=SNAPSHOT_MAX_TOKENS)
        user_content = user_template.format(
            existing_snapshot=existing_snapshot.strip() or "{}",
            newly_aged_messages=newly_aged_text,
        )
        result = invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="compressor",
            run_logger=run_logger,
            iteration=0,
            system_prompt=system_prompt,
        )
        return self._parse_or_fallback(result, existing_snapshot)

    def _parse_or_fallback(self, raw: str, existing_snapshot: str) -> str:
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, separators=(",", ":"))
        except json.JSONDecodeError:
            logger.warning(
                "Snapshot compressor returned invalid JSON; keeping existing snapshot."
            )
            return existing_snapshot or "{}"


class QueryRewriter:
    def rewrite(
        self,
        query: str,
        context_messages: List[Dict[str, str]],
        snapshot: str = "",
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in context_messages])
        system_prompt, user_template = get_prompt_parts("REWRITER")
        user_content = user_template.format(
            snapshot=snapshot or "{}",
            history_text=history_text,
            query=query,
        )
        return invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="rewriter",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )


class Orchestrator:
    def classify(
        self,
        query: str,
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        system_prompt, user_template = get_prompt_parts("ORCHESTRATOR")
        user_content = user_template.format(query=query)
        classification = invoke_llm(
            user_content,
            model_name=MODEL_ORCHESTRATOR,
            step="orchestrator",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
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
        system_prompt, user_template = get_prompt_parts("DRAFT_GENERATOR")
        user_content = user_template.format(context_text=context_text, query=query)
        return invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="drafter",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
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
        system_prompt, user_template = get_prompt_parts("DECISION_JUDGE")
        user_content = user_template.format(context_text=context_text, query=query, draft=draft)

        result = invoke_llm(
            user_content,
            model_name=MODEL_DECISION,
            step="judge",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )
        try:
            json_match = re.search(r'\{.*?\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("No JSON found")
        except Exception:
            # Default to PASS so we don't loop endlessly on small model JSON failures
            status = "FAIL" if "FAIL" in result.upper() and "PASS" not in result.upper() else "PASS"
            return {"status": status, "reasoning": "Fallback parsing applied."}