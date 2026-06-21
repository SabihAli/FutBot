import pytest
from datetime import datetime
from src.context import Message, ConversationContext

def test_message_creation():
    msg = Message(role="user", content="Hello", timestamp=datetime(2023, 1, 1))
    assert msg.role == "user"
    assert msg.content == "Hello"

def test_conversation_context_initialization():
    ctx = ConversationContext(session_id="test-session")
    assert ctx.session_id == "test-session"
    assert ctx.messages == []
    assert ctx.rolling_summary == ""
    assert ctx.message_count == 0

def test_add_message_retains_history_but_returns_evicted():
    ctx = ConversationContext(session_id="test-session")
    
    evicted = []
    for i in range(12):
        msg = Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        popped = ctx.add_message(msg)
        if popped:
            evicted.append(popped)
        
    assert ctx.message_count == 12
    # History should be fully retained for UI
    assert len(ctx.messages) == 12
    assert ctx.messages[0].content == "msg 0"
    assert ctx.messages[-1].content == "msg 11"
    
    # 2 messages should have been returned for summarization
    assert len(evicted) == 2
    assert evicted[0].content == "msg 0"
    assert evicted[1].content == "msg 1"

def test_get_context_messages():
    ctx = ConversationContext(session_id="test-session")
    
    for i in range(15):
        msg = Message(role="user", content=f"msg {i}", timestamp=datetime.now())
        ctx.add_message(msg)
        
    # Should only return the last 10 messages for the LLM context
    context_msgs = ctx.get_context_messages()
    assert len(context_msgs) == 10
    assert context_msgs[0].content == "msg 5"
    assert context_msgs[-1].content == "msg 14"
