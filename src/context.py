from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime

class ConversationContext(BaseModel):
    session_id: str
    messages: List[Message] = Field(default_factory=list)
    rolling_summary: str = ""
    message_count: int = 0

    def add_message(self, message: Message) -> Optional[Message]:
        """
        Adds a new message to the context history. 
        Retains all messages for UI history.
        Returns the message that just fell out of the 10-message window (if any),
        so it can be appended to the rolling summary by the caller.
        """
        self.message_count += 1
        self.messages.append(message)
        if len(self.messages) > 10:
            return self.messages[-11]
        return None

    def get_context_messages(self) -> List[Message]:
        """
        Returns the last 10 messages to be used as context for the LLM.
        """
        return self.messages[-10:]
