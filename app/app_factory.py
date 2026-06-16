from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.ai import router as ai_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.finance import router as finance_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.session import engine

configure_logging()

ROUTER_REGISTRY = {
    "health": (health_router, "", ["health"]),
    "auth": (auth_router, "/api/auth", ["auth"]),
    "admin": (admin_router, "/api/admin", ["admin"]),
    "finance": (finance_router, "/api/finance", ["finance"]),
    "documents": (documents_router, "/api/documents", ["documents"]),
    "ai": (ai_router, "/api/ai", ["ai"]),
}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.app_env in {"development", "test"}:
        Base.metadata.create_all(bind=engine)
    yield


def create_app(*, router_names: list[str]) -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Spend Control Platform",
        version="2.0.0",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router_name in router_names:
        router, prefix, tags = ROUTER_REGISTRY[router_name]
        app.include_router(router, prefix=prefix, tags=tags)
    return app
