from pydantic import BaseModel, Field


class MessageDict(BaseModel):
    role: str
    content: str


class CompressRequest(BaseModel):
    existing_snapshot: str = "{}"
    aged_messages: list[MessageDict] = Field(default_factory=list)
    max_tokens: int | None = None


class CompressResponse(BaseModel):
    snapshot: str
    tokens_used: int = 0


class CompleteRequest(BaseModel):
    step: str = "unknown"
    system_prompt: str = ""
    user_content: str
    model: str | None = None
    image_b64: str | None = None


class CompleteResponse(BaseModel):
    content: str
    model: str
    latency_ms: int
    provider: str
