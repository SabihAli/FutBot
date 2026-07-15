import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from futbot_common.errors import AuthError
from futbot_common.responses import DataResponse
from services.chat.context_builder import (
    build_context_usage,
    ensure_snapshot,
    load_chat_with_messages,
    run_auto_compress,
    to_context_usage_schema,
    _messages_to_context,
)
from services.chat.db import get_db
from services.chat.deps import assert_chat_access, optional_user_id, require_user_id
from services.chat.models import Chat, Message
from services.chat.orchestrator_client import run_pipeline_sync
from services.chat.schemas import (
    ChatListItem,
    ChatResponse,
    CreateChatRequest,
    CreateMessageRequest,
    MessageListResponse,
    MessageResponse,
    PostMessageResponse,
)

router = APIRouter(prefix="/chats", tags=["chats"])


def _chat_response(chat: Chat, usage_raw: dict) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        user_id=chat.user_id,
        project_id=chat.project_id,
        title=chat.title,
        compression_pending=chat.compression_pending,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        context_usage=to_context_usage_schema(usage_raw),
        should_compress=usage_raw["should_compress"],
    )


@router.get("", response_model=DataResponse[list[ChatListItem]])
async def list_chats(
    user_id: str = Depends(require_user_id),
    db: AsyncSession = Depends(get_db),
    project_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="-updated_at"),
):
    stmt = select(Chat).where(Chat.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(Chat.project_id == project_id)
    if sort == "-updated_at":
        stmt = stmt.order_by(Chat.updated_at.desc())
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    chats = result.scalars().all()
    return DataResponse(
        data=[
            ChatListItem(
                id=c.id,
                project_id=c.project_id,
                title=c.title,
                updated_at=c.updated_at,
            )
            for c in chats
        ]
    )


@router.post("", response_model=DataResponse[ChatResponse], status_code=201)
async def create_chat(
    body: CreateChatRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(optional_user_id),
):
    if body.project_id and not user_id:
        raise AuthError("LOGIN_REQUIRED", "Authentication required.", 403)
    chat = Chat(
        user_id=user_id,
        project_id=body.project_id,
        title=body.title,
    )
    db.add(chat)
    await db.flush()
    await ensure_snapshot(db, chat.id)
    await db.commit()
    chat = await load_chat_with_messages(db, chat.id)
    if not chat:
        raise AuthError("NOT_FOUND", "Chat not found.", 404)
    usage_raw = await build_context_usage(chat, user_id=user_id)
    return DataResponse(data=_chat_response(chat, usage_raw))


@router.get("/{chat_id}", response_model=DataResponse[ChatResponse])
async def get_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(optional_user_id),
):
    chat = await load_chat_with_messages(db, chat_id)
    if not chat:
        raise AuthError("NOT_FOUND", "Chat not found.", 404)
    assert_chat_access(chat.user_id, user_id)
    usage_raw = await build_context_usage(chat, user_id=user_id)
    return DataResponse(data=_chat_response(chat, usage_raw))


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_user_id),
):
    chat = await load_chat_with_messages(db, chat_id)
    if not chat:
        raise AuthError("NOT_FOUND", "Chat not found.", 404)
    if chat.user_id != user_id:
        raise AuthError("FORBIDDEN", "You do not have access to this chat.", 403)
    await db.delete(chat)
    await db.commit()
    return Response(status_code=204)


@router.get("/{chat_id}/messages", response_model=DataResponse[MessageListResponse])
async def list_messages(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(optional_user_id),
):
    chat = await load_chat_with_messages(db, chat_id)
    if not chat:
        raise AuthError("NOT_FOUND", "Chat not found.", 404)
    assert_chat_access(chat.user_id, user_id)
    msgs = sorted(chat.messages, key=lambda m: m.created_at)
    return DataResponse(
        data=MessageListResponse(
            messages=[
                MessageResponse(
                    id=m.id, role=m.role, content=m.content, created_at=m.created_at
                )
                for m in msgs
            ]
        )
    )


@router.post("/{chat_id}/messages", response_model=DataResponse[PostMessageResponse])
async def post_message(
    chat_id: str,
    body: CreateMessageRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(optional_user_id),
):
    chat = await load_chat_with_messages(db, chat_id)
    if not chat:
        raise AuthError("NOT_FOUND", "Chat not found.", 404)
    assert_chat_access(chat.user_id, user_id)

    msg = Message(chat_id=chat.id, role=body.role, content=body.content)
    db.add(msg)
    chat.messages.append(msg)
    chat.updated_at = datetime.now(timezone.utc)
    await db.flush()

    usage_raw = await build_context_usage(chat, user_id=user_id)
    if usage_raw["should_compress"]:
        chat.compression_pending = True
        try:
            if await run_auto_compress(db, chat):
                chat.compression_pending = False
                usage_raw = await build_context_usage(chat, user_id=user_id)
        except httpx.HTTPError:
            pass

    await db.commit()
    await db.refresh(msg)

    assistant_msg: Message | None = None
    run_id: int | None = None
    pipeline_result: dict = {}
    if body.role == "user":
        ctx = _messages_to_context(chat)
        snap = chat.snapshot.snapshot_text if chat.snapshot else ""
        turn_count = chat.snapshot.snapshot_turn_count if chat.snapshot else 0
        history = [
            {"role": m.role, "content": m.content}
            for m in sorted(chat.messages, key=lambda m: m.created_at)
        ]
        try:
            pipeline_result = run_pipeline_sync(
                session_id=chat.id,
                query=body.content,
                context_messages=history,
                snapshot=snap,
                snapshot_turn_count=turn_count,
                project_id=chat.project_id,
                web_search_enabled=body.web_search_enabled,
            )
            assistant_msg = Message(
                chat_id=chat.id,
                role="assistant",
                content=pipeline_result["reply"],
                citations_json=json.dumps(pipeline_result.get("citations", [])),
            )
            db.add(assistant_msg)
            chat.messages.append(assistant_msg)
            chat.updated_at = datetime.now(timezone.utc)
            snap_row = await ensure_snapshot(db, chat.id)
            snap_row.snapshot_text = pipeline_result["snapshot"]
            snap_row.snapshot_turn_count = pipeline_result["snapshot_turn_count"]
            run_id = pipeline_result.get("run_id")
            await db.commit()
            await db.refresh(assistant_msg)
            usage_raw = await build_context_usage(chat, user_id=user_id)
        except httpx.HTTPError:
            pass

    return DataResponse(
        data=PostMessageResponse(
            message=MessageResponse(
                id=msg.id, role=msg.role, content=msg.content, created_at=msg.created_at
            ),
            assistant_message=(
                MessageResponse(
                    id=assistant_msg.id,
                    role=assistant_msg.role,
                    content=assistant_msg.content,
                    created_at=assistant_msg.created_at,
                )
                if assistant_msg
                else None
            ),
            context_usage=to_context_usage_schema(usage_raw),
            should_compress=usage_raw["should_compress"],
            compression_pending=chat.compression_pending,
            run_id=run_id,
            tool_notice=pipeline_result.get("tool_notice") if assistant_msg else None,
            tool_notice_code=pipeline_result.get("tool_notice_code") if assistant_msg else None,
            web_search_skipped=bool(pipeline_result.get("web_search_skipped")) if assistant_msg else False,
        )
    )


@router.get("/{chat_id}/export")
async def export_chat(
    chat_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_user_id),
    format: str = Query(default="markdown", pattern="^(markdown|json|pdf)$"),
):
    chat = await load_chat_with_messages(db, chat_id)
    if not chat:
        raise AuthError("NOT_FOUND", "Chat not found.", 404)
    if chat.user_id != user_id:
        raise AuthError("FORBIDDEN", "You do not have access to this chat.", 403)

    msgs = sorted(chat.messages, key=lambda m: m.created_at)
    if format == "json":
        payload = {
            "id": chat.id,
            "title": chat.title,
            "project_id": chat.project_id,
            "messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
                for m in msgs
            ],
        }
        return Response(
            content=json.dumps(payload, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="chat-{chat_id}.json"'},
        )

    lines = [f"# {chat.title}", ""]
    for m in msgs:
        lines.append(f"**{m.role.title()}**: {m.content}")
        lines.append("")
    body = "\n".join(lines)

    if format == "pdf":
        from services.chat.orchestrator_client import export_markdown_to_pdf

        pdf_bytes = export_markdown_to_pdf(body, title=chat.title)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="chat-{chat_id}.pdf"'},
        )

    return Response(
        content=body,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="chat-{chat_id}.md"'},
    )
