import json
import re
from typing import Any

from services.llm_gateway.config import settings
from services.llm_gateway.prompt_loader import get_prompt_parts
from services.llm_gateway.provider import (
    MODEL_DECISION,
    MODEL_GENERATOR,
    MODEL_ORCHESTRATOR,
    invoke_llm,
    parse_snapshot_json,
)


class SnapshotCompressor:
    def compress_incremental(
        self,
        existing_snapshot: str,
        new_messages: list[dict[str, str]],
        run_logger=None,
    ) -> str:
        newly_aged_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in new_messages
        )
        system_prompt, user_template = get_prompt_parts("COMPRESSOR")
        system_prompt = system_prompt.format(max_tokens=settings.snapshot_max_tokens)
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
        return parse_snapshot_json(result, existing_snapshot)


class QueryRewriter:
    def rewrite(
        self,
        query: str,
        context_messages: list[dict[str, str]],
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
    def classify(self, query: str, run_logger=None, iteration: int = 0) -> str:
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
        chunks: list[dict[str, Any]],
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        context_text = "\n\n".join(
            [
                f"Source [{c.get('chunk_id', 'unknown')}]:\n{c.get('document', '')}"
                for c in chunks
            ]
        )
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
        chunks: list[dict[str, Any]],
        run_logger=None,
        iteration: int = 0,
    ) -> dict[str, str]:
        context_text = "\n\n".join([c.get("document", "") for c in chunks])
        system_prompt, user_template = get_prompt_parts("DECISION_JUDGE")
        user_content = user_template.format(
            context_text=context_text, query=query, draft=draft
        )
        result = invoke_llm(
            user_content,
            model_name=MODEL_DECISION,
            step="judge",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )
        try:
            json_match = re.search(r"\{.*?\}", result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError("No JSON found")
        except Exception:
            status = (
                "FAIL"
                if "FAIL" in result.upper() and "PASS" not in result.upper()
                else "PASS"
            )
            return {"status": status, "reasoning": "Fallback parsing applied."}
