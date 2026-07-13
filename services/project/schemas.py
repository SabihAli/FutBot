from datetime import datetime

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    created_at: datetime


class ProjectFileResponse(BaseModel):
    id: str
    filename: str
    content_hash: str
    status: str
    created_at: datetime


class CreateMemoryRequest(BaseModel):
    memory_type: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)
    source_chat_id: str | None = None


class MemoryItemResponse(BaseModel):
    id: str
    memory_type: str
    content: str
    source_chat_id: str | None
    created_at: datetime


class MemoryListResponse(BaseModel):
    items: list[MemoryItemResponse]


class ProjectContextResponse(BaseModel):
    project: ProjectResponse
    files: list[ProjectFileResponse]
    memory: list[MemoryItemResponse]
