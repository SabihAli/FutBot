import logging
from typing import Literal

from src.ingestion.errors import FootballRelevanceError
from services.llm_gateway.prompt_loader import get_prompt_parts
from services.llm_gateway.provider import MODEL_ORCHESTRATOR, invoke_llm

logger = logging.getLogger(__name__)


def _parse_verdict(response: str) -> Literal["YES", "NO"]:
    token = response.strip().split()[0].upper().rstrip(".") if response.strip() else ""
    if token == "YES":
        return "YES"
    return "NO"


def enforce_football_relevance(sample: str, filename: str) -> Literal["YES", "NO"]:
    system_prompt, user_template = get_prompt_parts("INGEST_CLASSIFIER")
    user_prompt = user_template.format(content=sample)
    response = invoke_llm(
        prompt=user_prompt,
        model_name=MODEL_ORCHESTRATOR,
        step="classifier",
        system_prompt=system_prompt,
    )
    verdict = _parse_verdict(response)
    if verdict == "NO":
        raise FootballRelevanceError(filename)
    return verdict
