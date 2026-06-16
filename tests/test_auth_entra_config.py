from app.core.config import Settings


def test_accepted_backend_audiences_include_uri_and_client_id() -> None:
    settings = Settings(
        ENTRA_BACKEND_CLIENT_ID="02a2ab18-2971-48dd-b806-4dd041fd512e",
        ENTRA_BACKEND_AUDIENCE="api://spendpilot-prod-api",
    )

    assert settings.accepted_backend_audiences == [
        "02a2ab18-2971-48dd-b806-4dd041fd512e",
        "api://02a2ab18-2971-48dd-b806-4dd041fd512e",
        "api://spendpilot-prod-api",
    ]
