from pydantic import BaseModel, Field


class PipelineRunRequest(BaseModel):
    session_id: str
    query: str
    context_messages: list[dict[str, str]] = Field(default_factory=list)
    snapshot: str = ""
    snapshot_turn_count: int = 0
    project_id: str | None = None


class CitationItem(BaseModel):
    chunk_id: str
    title: str = ""
    snippet: str = ""


class PipelineRunResponse(BaseModel):
    reply: str
    snapshot: str
    snapshot_turn_count: int
    citations: list[CitationItem] = Field(default_factory=list)
    run_id: int | None = None
    classification: str = "UNKNOWN"
    reached_max_retries: bool = False
