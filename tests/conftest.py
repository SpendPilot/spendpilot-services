from __future__ import annotations

import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "test-app.db"
if DB_PATH.exists():
    DB_PATH.unlink()

os.environ["APP_ENV"] = "test"
os.environ["AUTH_MODE"] = "dev-local"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["BACKEND_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["DEV_AUTH_SECRET"] = "dev-only-secret-change-me-1234567890"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)


def get_client() -> TestClient:
    return TestClient(app)
