from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.ai import router as ai_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.finance import router as finance_router
from app.api.routes.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router, prefix="/api/auth", tags=["auth"])
api_router.include_router(admin_router, prefix="/api/admin", tags=["admin"])
api_router.include_router(finance_router, prefix="/api/finance", tags=["finance"])
api_router.include_router(documents_router, prefix="/api/documents", tags=["documents"])
api_router.include_router(ai_router, prefix="/api/ai", tags=["ai"])
