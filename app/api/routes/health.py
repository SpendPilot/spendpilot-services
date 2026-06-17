from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(service=settings.service_name, checks={"status": "ok"})


@router.get("/ready", response_model=HealthResponse)
def ready(db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()
    checks = {
        "database": "ok",
        "auth_mode": settings.auth_mode,
        "service": settings.service_name,
        "document_intelligence": "configured" if settings.document_intelligence_enabled else "not_configured",
        "ai_foundry": "configured" if settings.foundry_enabled else "not_configured",
        "storage": "configured" if settings.storage_enabled else "local_filesystem",
    }
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        checks["database"] = f"error: {exc}"
    return HealthResponse(service=settings.service_name, checks=checks)
