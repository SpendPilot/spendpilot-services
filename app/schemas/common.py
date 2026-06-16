from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class APIEnvelope(BaseModel, Generic[T]):
    data: T


class HealthResponse(BaseModel):
    service: str
    checks: dict[str, Any]
