from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class AIChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    grounded_context_json: dict | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    grounded_context: dict[str, Any] | None = None
    suggested_followups: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def populate_grounded_fields(cls, value: Any) -> Any:
        grounded = value.get("grounded_context_json") if isinstance(value, dict) else getattr(value, "grounded_context_json", None)
        if not grounded:
            return value
        data = dict(value) if isinstance(value, dict) else {
            "id": value.id,
            "role": value.role,
            "content": value.content,
            "grounded_context_json": grounded,
            "created_at": value.created_at,
        }
        data["sources"] = grounded.get("sources") or []
        data["suggested_followups"] = grounded.get("suggested_followups") or []
        data["grounded_context"] = {
            key: grounded.get(key)
            for key in ("used_tools", "time_range", "confidence", "fallback_used")
            if key in grounded
        } or None
        return data


class AIChatSessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AIChatMessageOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AIChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class AIChatResponseOut(BaseModel):
    session: AIChatSessionOut
    reply: AIChatMessageOut
