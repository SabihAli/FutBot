from __future__ import annotations

import httpx
from services.chat.schemas import ContextUsage, ContextUsageBreakdown
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from services.chat.config import settings
from services.chat.context_usage import ContextInput, compute_context_usage
from services.chat.conversation import ConversationContext
from services.chat.models import Chat, ChatSnapshot, Message


async def _fetch_memory_content(project_id: str, user_id: str | None) -> str:
    if not project_id or not user_id:
        return ""
    url = f"{settings.project_service_url.rstrip('/')}/projects/{project_id}/memory"
    headers = {"X-User-ID": user_id}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return ""
            items = resp.json().get("data", {}).get("items", [])
            return "\n".join(item.get("content", "") for item in items)
    except httpx.HTTPError:
        return ""


async def load_chat_with_messages(db: AsyncSession, chat_id: str) -> Chat | None:
    result = await db.execute(
        select(Chat)
        .where(Chat.id == chat_id)
        .options(selectinload(Chat.messages), selectinload(Chat.snapshot))
    )
    return result.scalar_one_or_none()


def _messages_to_context(chat: Chat) -> ConversationContext:
    stored = [
        {"role": m.role, "content": m.content}
        for m in sorted(chat.messages, key=lambda m: m.created_at)
    ]
    snap = chat.snapshot.snapshot_text if chat.snapshot else ""
    turn_count = chat.snapshot.snapshot_turn_count if chat.snapshot else 0
    return ConversationContext.from_stored(chat.id, stored, snap, turn_count)


async def build_context_usage(
    chat: Chat,
    *,
    current_query: str = "",
    memory_content: str | None = None,
    retrieved_chunks: str = "",
    user_id: str | None = None,
) -> dict:
    ctx = _messages_to_context(chat)
    if memory_content is None and chat.project_id:
        memory_content = await _fetch_memory_content(chat.project_id, user_id)
    memory_content = memory_content or ""
    raw = compute_context_usage(
        ContextInput(
            snapshot=ctx.snapshot,
            hot_messages=ctx.hot_messages_as_dicts(),
            current_query=current_query,
            memory_content=memory_content,
            retrieved_chunks=retrieved_chunks,
        ),
        limit_tokens=settings.context_budget_tokens,
        compress_threshold_pct=settings.auto_compress_threshold_pct,
    )
    return raw


def to_context_usage_schema(raw: dict) -> ContextUsage:
    b = raw["breakdown"]
    return ContextUsage(
        used_tokens=raw["used_tokens"],
        limit_tokens=raw["limit_tokens"],
        percent_used=raw["percent_used"],
        breakdown=ContextUsageBreakdown(**b),
    )


async def ensure_snapshot(db: AsyncSession, chat_id: str) -> ChatSnapshot:
    result = await db.execute(
        select(ChatSnapshot).where(ChatSnapshot.chat_id == chat_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        return existing
    snap = ChatSnapshot(chat_id=chat_id, snapshot_text="", snapshot_turn_count=0)
    db.add(snap)
    await db.flush()
    return snap


async def run_auto_compress(db: AsyncSession, chat: Chat) -> bool:
    """Call LLM Gateway to compress aged messages into snapshot. Returns True if updated."""
    ctx = _messages_to_context(chat)
    if not ctx.needs_snapshot_update():
        return False

    aged = ctx.get_aged_messages()
    newly_aged = aged[ctx.snapshot_turn_count :]
    url = f"{settings.llm_gateway_url.rstrip('/')}/llm/compress"
    payload = {
        "existing_snapshot": ctx.snapshot or "{}",
        "aged_messages": [
            {"role": m.role, "content": m.content} for m in newly_aged
        ],
        "max_tokens": settings.snapshot_max_tokens,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        snapshot = resp.json()["data"]["snapshot"]

    snap = await ensure_snapshot(db, chat.id)
    snap.snapshot_text = snapshot
    snap.snapshot_turn_count = len(aged)
    if chat.snapshot:
        chat.snapshot.snapshot_text = snapshot
        chat.snapshot.snapshot_turn_count = len(aged)
    else:
        chat.snapshot = snap
    return True
