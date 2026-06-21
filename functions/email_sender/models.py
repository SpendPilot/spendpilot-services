from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class EmailTemplateType(StrEnum):
    WELCOME_EMAIL = "WELCOME_EMAIL"
    PASSWORD_RESET = "PASSWORD_RESET"
    EXPENSE_SUBMITTED = "EXPENSE_SUBMITTED"
    EXPENSE_APPROVED = "EXPENSE_APPROVED"
    EXPENSE_REJECTED = "EXPENSE_REJECTED"


class EmailRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: EmailTemplateType
    to: EmailStr
    template: str
    data: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(alias="correlationId")
    idempotency_key: str = Field(alias="idempotencyKey")

