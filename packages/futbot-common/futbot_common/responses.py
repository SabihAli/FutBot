from pydantic import BaseModel
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class DataResponse(BaseModel, Generic[T]):
    data: T
