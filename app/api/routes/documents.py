from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_current_principal
from app.db.session import get_db
from app.schemas.common import APIEnvelope
from app.schemas.documents import (
    DocumentListItem,
    DocumentOut,
    DocumentScanOut,
    DocumentUploadResponse,
    ExtractedExpenseOut,
)
from app.services.document_service import DocumentService

router = APIRouter()
document_service = DocumentService()


@router.get("", response_model=APIEnvelope[list[DocumentListItem]])
def list_documents(
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[list[DocumentListItem]]:
    return APIEnvelope(data=document_service.list_documents(db, principal))


@router.post("/upload", response_model=APIEnvelope[DocumentUploadResponse])
async def upload_document(
    file: UploadFile = File(...),
    expense_id: str | None = Form(default=None),
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[DocumentUploadResponse]:
    settings = get_settings()
    document = await document_service.upload_document(
        db,
        principal,
        file,
        settings.max_upload_bytes,
        expense_id=expense_id,
    )
    return APIEnvelope(data=DocumentUploadResponse(document=document))


@router.get("/{document_id}", response_model=APIEnvelope[DocumentOut])
def get_document(
    document_id: str,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[DocumentOut]:
    return APIEnvelope(data=DocumentOut.model_validate(document_service.get_document(db, principal, document_id)))


@router.post("/{document_id}/scan", response_model=APIEnvelope[DocumentScanOut])
def scan_document(
    document_id: str,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[DocumentScanOut]:
    return APIEnvelope(data=document_service.scan_document(db, principal, document_id))


@router.get("/{document_id}/scan-result", response_model=APIEnvelope[DocumentScanOut])
def get_scan_result(
    document_id: str,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[DocumentScanOut]:
    return APIEnvelope(data=document_service.get_latest_scan(db, principal, document_id))


@router.post("/{document_id}/extract-expense", response_model=APIEnvelope[ExtractedExpenseOut])
def extract_expense_data(
    document_id: str,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[ExtractedExpenseOut]:
    return APIEnvelope(data=document_service.extract_expense_data(db, principal, document_id))
