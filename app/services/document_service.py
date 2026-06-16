from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, joinedload

from app.core.rbac import ORG_READ_ROLES
from app.core.security import AuthenticatedPrincipal
from app.models import Document, DocumentScan, Expense
from app.schemas.documents import (
    DocumentAnalysisResult,
    DocumentListItem,
    DocumentOut,
    DocumentScanOut,
    ExtractedExpenseOut,
)
from app.services.ai_foundry_service import AIFoundryService
from app.services.audit_service import create_audit_event
from app.services.storage_service import StorageService


class DocumentService:
    def __init__(self) -> None:
        self.storage_service = StorageService()
        self.ai_service = AIFoundryService()

    def list_documents(self, db: Session, principal: AuthenticatedPrincipal) -> list[DocumentListItem]:
        query = (
            db.query(Document)
            .options(joinedload(Document.scans))
            .filter(Document.organization_id == principal.organization_id)
            .order_by(Document.created_at.desc())
        )
        if principal.role in ORG_READ_ROLES:
            pass
        elif principal.role == "dept_head":
            query = query.filter(Document.department_id == principal.department_id)
        else:
            query = query.filter(Document.owner_user_id == principal.user_id)

        results: list[DocumentListItem] = []
        for document in query.all():
            latest_scan = document.scans[0] if document.scans else None
            results.append(
                DocumentListItem(
                    document=DocumentOut.model_validate(document),
                    latest_scan=self._to_scan_out(latest_scan) if latest_scan else None,
                )
            )
        return results

    async def upload_document(
        self,
        db: Session,
        principal: AuthenticatedPrincipal,
        upload: UploadFile,
        max_upload_bytes: int,
        *,
        expense_id: str | None = None,
    ) -> DocumentOut:
        try:
            stored = await self.storage_service.save_upload(upload, max_upload_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large") from exc

        linked_expense_id = None
        if expense_id:
            expense = (
                db.query(Expense)
                .filter(Expense.id == expense_id, Expense.organization_id == principal.organization_id)
                .first()
            )
            if expense is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Expense not found")
            linked_expense_id = expense.id

        document = Document(
            organization_id=principal.organization_id,
            owner_user_id=principal.user_id,
            department_id=principal.department_id,
            expense_id=linked_expense_id,
            filename=upload.filename or "document.bin",
            content_type=upload.content_type or "application/octet-stream",
            file_size_bytes=len(stored.content),
            storage_kind=stored.storage_kind,
            storage_path=stored.storage_path,
            storage_url=stored.storage_url,
            linked_expense_type="variable_expense" if linked_expense_id else None,
            linked_expense_id=linked_expense_id,
            status="uploaded",
            metadata_json={"uploaded_by": principal.email},
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="document",
            resource_id=document.id,
            action="uploaded",
            details={"filename": document.filename},
        )
        return DocumentOut.model_validate(document)

    def get_document(self, db: Session, principal: AuthenticatedPrincipal, document_id: str) -> Document:
        document = (
            db.query(Document)
            .options(joinedload(Document.scans))
            .filter(Document.id == document_id, Document.organization_id == principal.organization_id)
            .first()
        )
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        if principal.role in ORG_READ_ROLES:
            return document
        if principal.role == "dept_head" and document.department_id == principal.department_id:
            return document
        if document.owner_user_id != principal.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        return document

    def scan_document(self, db: Session, principal: AuthenticatedPrincipal, document_id: str) -> DocumentScanOut:
        document = self.get_document(db, principal, document_id)
        content = self.storage_service.read_bytes(document.storage_kind, document.storage_path)
        extraction = self.ai_service.extract_text_from_document(
            filename=document.filename,
            content_type=document.content_type,
            content=content,
        )
        extracted_expense = extraction.invoice_fields or self.ai_service.extract_expense_fields(
            filename=document.filename,
            content_type=document.content_type,
            content=content,
            extracted_text=extraction.text,
        )

        document.extracted_text = extraction.text
        document.metadata_json = {
            **(document.metadata_json or {}),
            "extractor": extraction.extractor,
            "extracted_expense": self._json_value(extracted_expense) if extracted_expense else None,
        }

        analysis = self.ai_service.analyze_document(
            extraction.text,
            {
                "filename": document.filename,
                "content_type": document.content_type,
                "extractor": extraction.extractor,
            },
            extracted_expense=extracted_expense,
        )

        scan = DocumentScan(
            document_id=document.id,
            requested_by_user_id=principal.user_id,
            risk_level=analysis.risk_level,
            summary=analysis.summary,
            findings_json=[self._json_value(finding) for finding in analysis.findings],
            recommendations_json=analysis.recommendations,
            provider_status=analysis.provider_status,
            raw_response_json={
                "analysis": self._json_value(analysis.raw_response),
                "extracted_expense": self._json_value(analysis.extracted_expense) if analysis.extracted_expense else None,
            },
        )
        document.status = "scanned"
        db.add(scan)

        if document.expense_id and analysis.extracted_expense:
            self._apply_extracted_expense(db, document.expense_id, analysis.extracted_expense, analysis)

        db.commit()
        db.refresh(scan)
        create_audit_event(
            db,
            organization_id=principal.organization_id,
            actor_user_id=principal.user_id,
            resource_type="document",
            resource_id=document.id,
            action="scanned",
            details={"risk_level": analysis.risk_level},
        )
        return self._to_scan_out(scan)

    def extract_expense_data(self, db: Session, principal: AuthenticatedPrincipal, document_id: str) -> ExtractedExpenseOut:
        document = self.get_document(db, principal, document_id)
        content = self.storage_service.read_bytes(document.storage_kind, document.storage_path)
        extracted = self.ai_service.extract_expense_fields(
            filename=document.filename,
            content_type=document.content_type,
            content=content,
            extracted_text=document.extracted_text or "",
        )
        document.metadata_json = {
            **(document.metadata_json or {}),
            "extracted_expense": self._json_value(extracted),
        }
        db.commit()
        db.refresh(document)
        return extracted

    def get_latest_scan(self, db: Session, principal: AuthenticatedPrincipal, document_id: str) -> DocumentScanOut:
        document = self.get_document(db, principal, document_id)
        latest_scan = document.scans[0] if document.scans else None
        if latest_scan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No scan result found")
        return self._to_scan_out(latest_scan)

    def analyze_text(self, text: str, metadata: dict) -> DocumentAnalysisResult:
        return self.ai_service.analyze_document(text, metadata)

    @staticmethod
    def _json_value(value):
        return jsonable_encoder(value)

    @staticmethod
    def _to_scan_out(scan: DocumentScan) -> DocumentScanOut:
        extracted_expense = None
        if scan.raw_response_json and scan.raw_response_json.get("extracted_expense"):
            extracted_expense = ExtractedExpenseOut.model_validate(scan.raw_response_json["extracted_expense"])
        return DocumentScanOut(
            id=scan.id,
            document_id=scan.document_id,
            requested_by_user_id=scan.requested_by_user_id,
            risk_level=scan.risk_level,
            summary=scan.summary,
            findings=scan.findings_json or [],
            recommendations=scan.recommendations_json or [],
            provider_status=scan.provider_status,
            extracted_expense=extracted_expense,
            created_at=scan.created_at,
        )

    @staticmethod
    def _apply_extracted_expense(
        db: Session,
        expense_id: str,
        extracted: ExtractedExpenseOut,
        analysis: DocumentAnalysisResult,
    ) -> None:
        expense = db.query(Expense).filter(Expense.id == expense_id).first()
        if expense is None:
            return
        if extracted.vendor_name and not expense.vendor_name:
            expense.vendor_name = extracted.vendor_name
        if extracted.invoice_number and not expense.invoice_number:
            expense.invoice_number = extracted.invoice_number
        if extracted.currency and not expense.currency:
            expense.currency = extracted.currency
        if extracted.total_amount is not None and expense.amount == Decimal("0"):
            expense.amount = extracted.total_amount
        if analysis.summary and not expense.ai_summary:
            expense.ai_summary = analysis.summary
        if analysis.risk_level:
            expense.ai_risk_level = analysis.risk_level
