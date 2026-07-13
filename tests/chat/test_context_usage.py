import pytest

from services.chat.context_usage import ContextInput, compute_context_usage


def test_compute_context_usage_sums_all_prompt_components():
    inp = ContextInput(
        snapshot="summary of old turns",
        hot_messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ],
        current_query="who scored?",
        memory_content="User prefers Liverpool.",
        retrieved_chunks="Chunk A: Salah scored.\nChunk B: 2-1 final.",
    )
    result = compute_context_usage(inp, limit_tokens=8192, compress_threshold_pct=85)

    assert result["used_tokens"] > 0
    assert result["limit_tokens"] == 8192
    assert result["breakdown"]["snapshot"] > 0
    assert result["breakdown"]["hot_messages"] > 0
    assert result["breakdown"]["current_query"] > 0
    assert result["breakdown"]["memory"] > 0
    assert result["breakdown"]["retrieved_chunks"] > 0
    assert (
        result["used_tokens"]
        == result["breakdown"]["snapshot"]
        + result["breakdown"]["hot_messages"]
        + result["breakdown"]["current_query"]
        + result["breakdown"]["memory"]
        + result["breakdown"]["retrieved_chunks"]
    )


def test_compute_context_usage_omits_empty_optional_components():
    inp = ContextInput(
        snapshot="",
        hot_messages=[{"role": "user", "content": "hi"}],
    )
    result = compute_context_usage(inp, limit_tokens=1000)

    assert result["breakdown"]["current_query"] == 0
    assert result["breakdown"]["memory"] == 0
    assert result["breakdown"]["retrieved_chunks"] == 0


def test_should_compress_when_at_or_above_threshold():
    inp = ContextInput(snapshot="x" * 4000, hot_messages=[])
    result = compute_context_usage(inp, limit_tokens=100, compress_threshold_pct=85)
    assert result["should_compress"] is True
    assert result["percent_used"] >= 85


def test_should_not_compress_below_threshold():
    inp = ContextInput(snapshot="hi", hot_messages=[])
    result = compute_context_usage(inp, limit_tokens=8192, compress_threshold_pct=85)
    assert result["should_compress"] is False
