import json
import logging
import random
import re
import time as _time
from collections.abc import AsyncGenerator
from typing import Any

import requests

from services.llm_gateway.config import settings
from services.llm_gateway.prompt_loader import get_prompt_parts

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

GROQ_MODEL_MAP: dict[str, str] = {
    "orchestrator": settings.groq_model_orchestrator,
    "classifier": settings.groq_model_orchestrator,
    "vision": settings.groq_model_main,
    "rewriter": settings.groq_model_main,
    "compressor": settings.groq_model_main,
    "drafter": settings.groq_model_main,
    "simple_responder": settings.groq_model_main,
    "judge": settings.groq_model_main,
}

GROQ_THINKING_ROLES = {"judge"}

MODEL_ORCHESTRATOR = settings.model_orchestrator
MODEL_GENERATOR = settings.model_generator
MODEL_DECISION = settings.model_decision


def _strip_think_tags(text: str) -> str:
    stripped = re.sub(
        r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE
    )
    return stripped.strip()


def _call_groq(
    role: str,
    system_prompt: str,
    user_content: str,
    image: bytes | None = None,
) -> tuple[str, str, int | None, int]:
    if not settings.groq_api_key:
        raise ValueError(
            "GROQ_API_KEY is not set. "
            "Add it to your .env file or environment when using LLM_PROVIDER=groq."
        )

    model = GROQ_MODEL_MAP.get(role, settings.groq_model_main)
    thinking = role in GROQ_THINKING_ROLES

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

    payload: dict[str, Any] = {
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
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    raw = ""
    clean = ""
    status_code: int | None = None
    t0 = _time.monotonic()

    for attempt in range(settings.groq_max_retries):
        try:
            resp = requests.post(
                GROQ_API_URL, json=payload, headers=headers, timeout=120
            )
            status_code = resp.status_code

            if resp.status_code == 429:
                retry_after = float(
                    resp.headers.get("retry-after", settings.groq_backoff_base**attempt)
                )
                wait = retry_after + random.uniform(0, 0.5)
                logger.warning(
                    "Groq 429 on attempt %s/%s. Waiting %.2fs.",
                    attempt + 1,
                    settings.groq_max_retries,
                    wait,
                )
                _time.sleep(wait)
                continue

            resp.raise_for_status()
            raw = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            clean = _strip_think_tags(raw)
            latency_ms = int((_time.monotonic() - t0) * 1000)
            return raw, clean, status_code, latency_ms

        except requests.RequestException as e:
            logger.error("Groq API request error (attempt %s): %s", attempt + 1, e)
            if attempt == settings.groq_max_retries - 1:
                latency_ms = int((_time.monotonic() - t0) * 1000)
                return raw, clean, status_code, latency_ms
            _time.sleep(settings.groq_backoff_base**attempt + random.uniform(0, 0.5))

    latency_ms = int((_time.monotonic() - t0) * 1000)
    return raw, clean, status_code, latency_ms


def _call_local(model_name: str, prompt: str) -> tuple[str, str, str, int | None, int]:
    model_name_lower = model_name.lower()
    if "0.8b" in model_name_lower:
        api_url = settings.url_08b
    elif "2b" in model_name_lower:
        api_url = settings.url_2b
    elif "4b" in model_name_lower:
        api_url = settings.url_4b
    else:
        api_url = settings.url_2b

    if "/chat/completions" in api_url or "/v1/chat/completions" in api_url:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
    else:
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
        latency_ms = int((_time.monotonic() - t0) * 1000)
        return api_url, raw, clean, status_code, latency_ms
    except requests.RequestException as e:
        latency_ms = int((_time.monotonic() - t0) * 1000)
        logger.error("Error calling local LLM API (%s) at %s: %s", model_name, api_url, e)
        return api_url, raw, clean, status_code, latency_ms


def invoke_llm(
    prompt: str,
    model_name: str,
    step: str = "unknown",
    run_logger=None,
    iteration: int = 0,
    image: bytes | None = None,
    system_prompt: str | None = None,
) -> str:
    raw = ""
    clean = ""
    api_url = ""
    status_code: int | None = None
    latency_ms = 0

    if settings.llm_provider == "groq":
        api_url = GROQ_API_URL
        groq_model = GROQ_MODEL_MAP.get(step, settings.groq_model_main)
        sys_msg = system_prompt if system_prompt is not None else ""
        raw, clean, status_code, latency_ms = _call_groq(step, sys_msg, prompt, image=image)
        log_model_name = groq_model
    else:
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
            logger.warning("Failed to log LLM call: %s", log_err)

    return clean


def invoke_llm_stream(
    prompt: str,
    model_name: str,
    step: str = "drafter",
    system_prompt: str | None = None,
) -> list[str]:
    """Non-streaming fallback tokens for local provider; Groq stream deferred to Phase 6 wiring."""
    text = invoke_llm(
        prompt,
        model_name=model_name,
        step=step,
        system_prompt=system_prompt,
    )
    return [text] if text else []


def parse_snapshot_json(raw: str, existing_snapshot: str) -> str:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    try:
        parsed = json.loads(text)
        return json.dumps(parsed, separators=(",", ":"))
    except json.JSONDecodeError:
        logger.warning("Snapshot compressor returned invalid JSON; keeping existing snapshot.")
        return existing_snapshot or "{}"
