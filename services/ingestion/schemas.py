from pydantic import BaseModel, Field


class CreateJobRequest(BaseModel):
    project_id: str
    file_id: str
    filename: str
    storage_key: str
    content_hash: str = ""


class JobResponse(BaseModel):
    id: str
    project_id: str
    file_id: str
    filename: str
    status: str
    chunks_indexed: int = 0
    error_message: str | None = None
