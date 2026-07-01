import pytest
from datetime import datetime
from unittest.mock import MagicMock

from src.context import Message, ConversationContext
from src.config import HOT_CONTEXT_WINDOW


def test_message_creation():
    msg = Message(role="user", content="Hello", timestamp=datetime(2023, 1, 1))
    assert msg.role == "user"
    assert msg.content == "Hello"


def test_conversation_context_initialization():
    ctx = ConversationContext(session_id="test-session")
    assert ctx.session_id == "test-session"
    assert ctx.messages == []
    assert ctx.snapshot == ""
    assert ctx.snapshot_turn_count == 0


def test_migrate_rolling_summary_field():
    ctx = ConversationContext.model_validate({
        "session_id": "s1",
        "rolling_summary": "old summary",
    })
    assert ctx.snapshot == "old summary"


def test_add_message_retains_full_history():
    ctx = ConversationContext(session_id="test-session")

    for i in range(12):
        msg = Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        ctx.add_message(msg)

    assert len(ctx.messages) == 12
    assert ctx.messages[0].content == "msg 0"
    assert ctx.messages[-1].content == "msg 11"


def test_get_hot_messages():
    ctx = ConversationContext(session_id="test-session")

    for i in range(15):
        msg = Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        ctx.add_message(msg)

    hot = ctx.get_hot_messages()
    assert len(hot) == HOT_CONTEXT_WINDOW
    assert hot[0].content == f"msg {15 - HOT_CONTEXT_WINDOW}"
    assert hot[-1].content == "msg 14"


def test_get_context_messages_alias():
    ctx = ConversationContext(session_id="test-session")
    ctx.add_message(Message(role="user", content="hi", timestamp=datetime.now()))
    assert ctx.get_context_messages() == ctx.get_hot_messages()


def test_get_aged_messages():
    ctx = ConversationContext(session_id="test-session")
    for i in range(HOT_CONTEXT_WINDOW + 2):
        ctx.add_message(
            Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        )

    aged = ctx.get_aged_messages()
    assert len(aged) == 2
    assert aged[0].content == "msg 0"


def test_needs_snapshot_update():
    ctx = ConversationContext(session_id="test-session")
    assert not ctx.needs_snapshot_update()

    for i in range(HOT_CONTEXT_WINDOW + 1):
        ctx.add_message(
            Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        )

    assert ctx.needs_snapshot_update()


def test_maintain_snapshot_skips_when_current():
    ctx = ConversationContext(session_id="test-session", snapshot_turn_count=1)
    for i in range(HOT_CONTEXT_WINDOW + 1):
        ctx.add_message(
            Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        )

    compressor = MagicMock()
    assert ctx.maintain_snapshot(compressor) is False
    compressor.compress_incremental.assert_not_called()


def test_maintain_snapshot_calls_compressor():
    ctx = ConversationContext(session_id="test-session")
    for i in range(HOT_CONTEXT_WINDOW + 1):
        ctx.add_message(
            Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        )

    compressor = MagicMock()
    compressor.compress_incremental.return_value = '{"schema_version":1}'

    assert ctx.maintain_snapshot(compressor) is True
    compressor.compress_incremental.assert_called_once()
    assert ctx.snapshot_turn_count == 1
    assert ctx.snapshot == '{"schema_version":1}'


def test_from_graph_fields_and_to_graph_fields():
    ctx = ConversationContext.from_graph_fields(
        session_id="s1",
        messages=[{"role": "user", "content": "hello"}],
        snapshot="{}",
        snapshot_turn_count=0,
    )
    fields = ctx.to_graph_fields()
    assert fields["snapshot"] == "{}"
    assert fields["context_messages"] == [{"role": "user", "content": "hello"}]
    assert len(fields["all_messages"]) == 1
