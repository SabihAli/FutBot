from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Protocol

from pydantic import BaseModel, Field, model_validator

from services.chat.config import settings


class CompressorProtocol(Protocol):
    def compress_incremental(
        self,
        existing_snapshot: str,
        new_messages: List[Dict[str, str]],
        run_logger: Any = None,
    ) -> str: ...


class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime


class ConversationContext(BaseModel):
    session_id: str
    messages: List[Message] = Field(default_factory=list)
    snapshot: str = ""
    snapshot_turn_count: int = 0

    @model_validator(mode="before")
    @classmethod
    def migrate_rolling_summary(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "rolling_summary" in data and not data.get("snapshot"):
                data["snapshot"] = data.pop("rolling_summary", "") or ""
            data.pop("rolling_summary", None)
            data.pop("message_count", None)
        return data

    def add_message(self, message: Message) -> None:
        self.messages.append(message)

    def get_hot_messages(self) -> List[Message]:
        return self.messages[-settings.hot_context_window :]

    def get_aged_messages(self) -> List[Message]:
        if len(self.messages) <= settings.hot_context_window:
            return []
        return self.messages[: -settings.hot_context_window]

    def needs_snapshot_update(self) -> bool:
        return len(self.get_aged_messages()) > self.snapshot_turn_count

    def maintain_snapshot(self, compressor: CompressorProtocol, run_logger=None) -> bool:
        aged = self.get_aged_messages()
        if len(aged) == self.snapshot_turn_count:
            return False
        newly_aged = aged[self.snapshot_turn_count :]
        self.snapshot = compressor.compress_incremental(
            existing_snapshot=self.snapshot,
            new_messages=[{"role": m.role, "content": m.content} for m in newly_aged],
            run_logger=run_logger,
        )
        self.snapshot_turn_count = len(aged)
        return True

    def hot_messages_as_dicts(self) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.get_hot_messages()]

    @classmethod
    def from_graph_fields(
        cls,
        session_id: str,
        messages: List[Dict[str, str]],
        snapshot: str,
        snapshot_turn_count: int,
    ) -> ConversationContext:
        return cls.from_stored(session_id, messages, snapshot, snapshot_turn_count)

    def to_graph_fields(self) -> Dict[str, Any]:
        return {
            "all_messages": [
                {"role": m.role, "content": m.content} for m in self.messages
            ],
            "snapshot": self.snapshot,
            "snapshot_turn_count": self.snapshot_turn_count,
            "context_messages": self.hot_messages_as_dicts(),
        }

    @classmethod
    def from_stored(
        cls,
        chat_id: str,
        messages: List[Dict[str, str]],
        snapshot: str,
        snapshot_turn_count: int,
    ) -> ConversationContext:
        msg_objs = [
            Message(
                role=m["role"],
                content=m["content"],
                timestamp=datetime.now(timezone.utc),
            )
            for m in messages
        ]
        return cls(
            session_id=chat_id,
            messages=msg_objs,
            snapshot=snapshot or "",
            snapshot_turn_count=snapshot_turn_count,
        )
