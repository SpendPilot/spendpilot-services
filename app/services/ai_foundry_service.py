from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.identity import get_bearer_token_provider
from fastapi.encoders import jsonable_encoder
from openai import AzureOpenAI

from app.core.azure_identity import get_default_credential
from app.core.config import get_settings
from app.schemas.documents import DocumentAnalysisResult, ExtractedExpenseOut
from app.services.policy_service import build_fallback_analysis, normalize_analysis_result

logger = logging.getLogger(__name__)


@dataclass
class DocumentExtraction:
    text: str
    extractor: str
    invoice_fields: ExtractedExpenseOut | None = None


class AIFoundryService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._document_client: DocumentIntelligenceClient | None = None
        self._openai_client: AzureOpenAI | None = None

    def _get_document_client(self) -> DocumentIntelligenceClient:
        if self._document_client is None:
            self._document_client = DocumentIntelligenceClient(
                endpoint=self.settings.azure_document_intelligence_endpoint,
                credential=get_default_credential(),
            )
        return self._document_client

    def _get_openai_client(self) -> AzureOpenAI:
        if self._openai_client is None:
            token_provider = get_bearer_token_provider(
                get_default_credential(),
                "https://cognitiveservices.azure.com/.default",
            )
            self._openai_client = AzureOpenAI(
                base_url=self.settings.foundry_openai_base_url,
                api_key=token_provider,
            )
        return self._openai_client

    def extract_text_from_document(self, *, filename: str, content_type: str, content: bytes) -> DocumentExtraction:
        suffix = Path(filename).suffix.lower()
        if content_type.startswith("text/") or suffix in {".txt", ".md", ".json", ".csv"}:
            text = content.decode("utf-8", errors="ignore")
            return DocumentExtraction(
                text=text,
                extractor="local-text",
                invoice_fields=self._fallback_expense_details(text),
            )

        if self.settings.document_intelligence_enabled:
            try:
                invoice_fields = self.extract_expense_fields(
                    filename=filename,
                    content_type=content_type,
                    content=content,
                    extracted_text=None,
                )
                poller = self._get_document_client().begin_analyze_document("prebuilt-read", body=content)
                result = poller.result()
                return DocumentExtraction(
                    text=(result.content or "").strip(),
                    extractor="azure-document-intelligence",
                    invoice_fields=invoice_fields,
                )
            except Exception as exc:  # pragma: no cover - network failure path
                logger.warning("Document Intelligence extraction failed: %s", exc)

        return DocumentExtraction(
            text="",
            extractor="fallback",
            invoice_fields=None,
        )

    def extract_expense_fields(
        self,
        *,
        filename: str,
        content_type: str,
        content: bytes,
        extracted_text: str | None,
    ) -> ExtractedExpenseOut:
        suffix = Path(filename).suffix.lower()
        if self.settings.document_intelligence_enabled and (
            content_type.startswith("image/") or suffix in {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
        ):
            try:
                poller = self._get_document_client().begin_analyze_document("prebuilt-invoice", body=content)
                result = poller.result()
                payload = self._invoice_result_to_payload(result)
                if payload.total_amount or payload.vendor_name or payload.invoice_number:
                    return payload
            except Exception as exc:  # pragma: no cover - network failure path
                logger.warning("Invoice extraction failed: %s", exc)

        text = extracted_text or ""
        if text and self.settings.foundry_enabled:
            try:
                completion = self._get_openai_client().chat.completions.create(
                    model=self.settings.azure_ai_model_deployment,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Extract structured expense fields from invoice or receipt text. "
                                "Return compact JSON with vendor_name, invoice_number, invoice_date, "
                                "currency, total_amount, category_hint, and summary."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "filename": filename,
                                    "document_text": text[:12000],
                                }
                            ),
                        },
                    ],
                )
                payload = json.loads(completion.choices[0].message.content or "{}")
                payload["provider_status"] = "azure-ai-foundry"
                payload["raw_response"] = payload
                return ExtractedExpenseOut.model_validate(payload)
            except Exception as exc:  # pragma: no cover - network failure path
                logger.warning("Foundry expense extraction failed: %s", exc)

        return self._fallback_expense_details(text)

    def analyze_document(
        self,
        text: str,
        metadata: dict,
        *,
        extracted_expense: ExtractedExpenseOut | None = None,
    ) -> DocumentAnalysisResult:
        if not text.strip():
            return build_fallback_analysis(
                "No extractable text was available. Configure Azure Document Intelligence for PDFs and images.",
                metadata,
            )

        if self.settings.foundry_enabled:
            try:
                completion = self._get_openai_client().chat.completions.create(
                    model=self.settings.azure_ai_model_deployment,
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You review business finance documents and return compact JSON with "
                                "summary, risk_level, findings, recommendations, and optional extracted_expense."
                            ),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                {
                                    "instructions": (
                                        "Analyze this business document for finance operations. "
                                        "Check for policy concerns, approval risks, missing invoice signals, "
                                        "and spend anomalies. Return JSON shaped as "
                                        "{summary, risk_level, findings, recommendations, extracted_expense}."
                                    ),
                                    "metadata": metadata,
                                    "document_text": text[:16000],
                                    "extracted_expense": self._json_value(extracted_expense) if extracted_expense else None,
                                }
                            ),
                        },
                    ],
                )
                payload = json.loads(completion.choices[0].message.content or "{}")
                payload["provider_status"] = "azure-ai-foundry"
                payload["raw_response"] = payload
                if extracted_expense and not payload.get("extracted_expense"):
                    payload["extracted_expense"] = self._json_value(extracted_expense)
                return normalize_analysis_result(payload)
            except Exception as exc:  # pragma: no cover - network failure path
                logger.warning("Azure AI Foundry analysis failed: %s", exc)

        fallback = build_fallback_analysis(text, metadata)
        if extracted_expense:
            fallback.extracted_expense = extracted_expense
        return fallback

    def _invoice_result_to_payload(self, result) -> ExtractedExpenseOut:
        document = result.documents[0] if getattr(result, "documents", None) else None
        if document is None:
            return ExtractedExpenseOut(provider_status="fallback")
        fields = getattr(document, "fields", {}) or {}
        payload = {
            "vendor_name": self._field_value(fields.get("VendorName")),
            "invoice_number": self._field_value(fields.get("InvoiceId")),
            "invoice_date": self._field_value(fields.get("InvoiceDate")),
            "currency": self._field_value(fields.get("CurrencyCode")) or "INR",
            "total_amount": self._decimal_value(fields.get("InvoiceTotal")),
            "category_hint": "travel" if "travel" in (result.content or "").lower() else "professional-services",
            "summary": "Extracted with Azure Document Intelligence invoice model.",
            "provider_status": "azure-document-intelligence",
            "raw_response": {
                "model_id": getattr(result, "model_id", None),
                "document_type": getattr(document, "doc_type", None),
            },
        }
        return ExtractedExpenseOut.model_validate(payload)

    def _fallback_expense_details(self, text: str) -> ExtractedExpenseOut:
        amount_match = re.search(r"(?i)(?:total|amount due|invoice total)[^0-9]{0,10}([0-9][0-9,]*\.?[0-9]{0,2})", text)
        invoice_match = re.search(r"(?i)(?:invoice|receipt)\s*(?:#|no\.?|number)?\s*[:\-]?\s*([A-Z0-9\-\/]+)", text)
        date_match = re.search(r"(?i)(\d{4}-\d{2}-\d{2}|\d{2}[\/\-]\d{2}[\/\-]\d{4})", text)

        total_amount = None
        if amount_match:
            try:
                total_amount = Decimal(amount_match.group(1).replace(",", ""))
            except InvalidOperation:
                total_amount = None

        return ExtractedExpenseOut(
            invoice_number=invoice_match.group(1) if invoice_match else None,
            invoice_date=date_match.group(1) if date_match else None,
            total_amount=total_amount,
            currency="INR" if "inr" in text.lower() or "rs" in text.lower() else None,
            summary="Fallback extraction based on OCR text patterns.",
            provider_status="fallback",
        )

    @staticmethod
    def _json_value(value):
        return jsonable_encoder(value)

    @staticmethod
    def _field_value(field) -> str | None:
        if field is None:
            return None
        for attr in ("value_string", "value_date", "value_currency", "content"):
            value = getattr(field, attr, None)
            if value is None:
                continue
            if attr == "value_currency" and getattr(value, "amount", None) is not None:
                return getattr(value, "currency_symbol", None) or getattr(value, "code", None)
            return str(value)
        return None

    @staticmethod
    def _decimal_value(field) -> Decimal | None:
        if field is None:
            return None
        value = getattr(field, "value_currency", None)
        if value is not None and getattr(value, "amount", None) is not None:
            try:
                return Decimal(str(value.amount))
            except InvalidOperation:
                return None
        raw = getattr(field, "content", None)
        if raw is None:
            return None
        try:
            return Decimal(str(raw).replace(",", ""))
        except InvalidOperation:
            return None
