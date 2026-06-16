from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class FindingOut(BaseModel):
    title: str
    description: str
    severity: str


class ExtractedExpenseOut(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    currency: str | None = None
    total_amount: Decimal | None = None
    invoice_date: str | None = None
    category_hint: str | None = None
    summary: str | None = None
    provider_status: str = "fallback"
    raw_response: dict[str, Any] | None = None


class DocumentAnalysisResult(BaseModel):
    summary: str
    risk_level: str
    findings: list[FindingOut] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    provider_status: str = "fallback"
    extracted_expense: ExtractedExpenseOut | None = None
    raw_response: dict[str, Any] | None = None


class DocumentOut(BaseModel):
    id: str
    organization_id: str
    owner_user_id: str
    department_id: str | None
    expense_id: str | None
    filename: str
    content_type: str
    file_size_bytes: int
    storage_kind: str
    storage_url: str | None
    linked_expense_type: str | None
    linked_expense_id: str | None
    status: str
    extracted_text: str | None
    metadata_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentScanOut(BaseModel):
    id: str
    document_id: str
    requested_by_user_id: str
    risk_level: str
    summary: str
    findings: list[FindingOut] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    provider_status: str
    extracted_expense: ExtractedExpenseOut | None = None
    created_at: datetime


class DocumentListItem(BaseModel):
    document: DocumentOut
    latest_scan: DocumentScanOut | None = None


class DocumentUploadResponse(BaseModel):
    document: DocumentOut


class TextAnalyzeRequest(BaseModel):
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
