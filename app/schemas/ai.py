from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    grounded_context_json: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


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
