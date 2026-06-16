from fastapi import APIRouter, Depends

from app.core.security import get_current_principal
from app.schemas.ai import AIChatRequest, AIChatResponseOut, AIChatSessionOut
from app.schemas.common import APIEnvelope
from app.schemas.documents import DocumentAnalysisResult, TextAnalyzeRequest
from app.services.ai_chat_service import AIChatService
from app.services.document_service import DocumentService
from app.db.session import get_db
from sqlalchemy.orm import Session

router = APIRouter()
document_service = DocumentService()
ai_chat_service = AIChatService()


@router.post("/analyze", response_model=APIEnvelope[DocumentAnalysisResult])
def analyze_text(
    payload: TextAnalyzeRequest,
    _principal=Depends(get_current_principal),
) -> APIEnvelope[DocumentAnalysisResult]:
    return APIEnvelope(data=document_service.analyze_text(payload.text, payload.metadata))


@router.get("/sessions", response_model=APIEnvelope[list[AIChatSessionOut]])
def sessions(principal=Depends(get_current_principal), db: Session = Depends(get_db)) -> APIEnvelope[list[AIChatSessionOut]]:
    return APIEnvelope(data=[AIChatSessionOut.model_validate(item) for item in ai_chat_service.list_sessions(db, principal)])


@router.post("/chat", response_model=APIEnvelope[AIChatResponseOut])
def chat(
    payload: AIChatRequest,
    principal=Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> APIEnvelope[AIChatResponseOut]:
    session, reply = ai_chat_service.ask(db, principal, payload.message, payload.session_id)
    return APIEnvelope(
        data=AIChatResponseOut(
            session=AIChatSessionOut.model_validate(session),
            reply=reply,
        )
    )
