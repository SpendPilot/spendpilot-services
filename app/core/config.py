from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = Field(default="platform-api", alias="SERVICE_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    backend_cors_origins: str = Field(default="http://localhost:3000", alias="BACKEND_CORS_ORIGINS")

    auth_mode: str = Field(default="entra", alias="AUTH_MODE")
    azure_tenant_id: str = Field(default="", alias="AZURE_TENANT_ID")
    azure_client_id: str = Field(default="", alias="AZURE_CLIENT_ID")
    entra_frontend_client_id: str = Field(default="", alias="ENTRA_FRONTEND_CLIENT_ID")
    entra_backend_client_id: str = Field(default="", alias="ENTRA_BACKEND_CLIENT_ID")
    entra_backend_audience: str = Field(default="", alias="ENTRA_BACKEND_AUDIENCE")
    entra_authority: str = Field(default="", alias="ENTRA_AUTHORITY")
    entra_allowed_tenant_ids: str = Field(default="", alias="ENTRA_ALLOWED_TENANT_IDS")
    platform_admin_emails: str = Field(default="", alias="PLATFORM_ADMIN_EMAILS")

    dev_auth_secret: str = Field(
        default="dev-only-secret-change-me-1234567890",
        alias="DEV_AUTH_SECRET",
    )
    dev_auth_default_email: str = Field(default="developer@local.test", alias="DEV_AUTH_DEFAULT_EMAIL")
    dev_auth_default_name: str = Field(default="Local Developer", alias="DEV_AUTH_DEFAULT_NAME")
    dev_auth_default_role: str = Field(default="org_owner", alias="DEV_AUTH_DEFAULT_ROLE")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    azure_ai_foundry_endpoint: str = Field(default="", alias="AZURE_AI_FOUNDRY_ENDPOINT")
    azure_ai_project_endpoint: str = Field(default="", alias="AZURE_AI_PROJECT_ENDPOINT")
    azure_ai_model_deployment: str = Field(default="", alias="AZURE_AI_MODEL_DEPLOYMENT")
    azure_document_intelligence_endpoint: str = Field(default="", alias="AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
    azure_storage_account_url: str = Field(default="", alias="AZURE_STORAGE_ACCOUNT_URL")
    azure_storage_container_name: str = Field(default="", alias="AZURE_STORAGE_CONTAINER_NAME")

    finance_default_currency: str = Field(default="INR", alias="FINANCE_DEFAULT_CURRENCY")
    local_upload_dir: str = Field(default="./data/uploads", alias="LOCAL_UPLOAD_DIR")
    max_upload_bytes: int = Field(default=10_485_760, alias="MAX_UPLOAD_BYTES")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def allowed_tenant_ids_list(self) -> list[str]:
        return [tenant_id.strip() for tenant_id in self.entra_allowed_tenant_ids.split(",") if tenant_id.strip()]

    @property
    def platform_admin_emails_list(self) -> list[str]:
        return [email.strip().lower() for email in self.platform_admin_emails.split(",") if email.strip()]

    @property
    def backend_audience(self) -> str:
        if self.entra_backend_audience:
            return self.entra_backend_audience
        if self.entra_backend_client_id:
            return f"api://{self.entra_backend_client_id}"
        return "api://spend-control-local"

    @property
    def accepted_backend_audiences(self) -> list[str]:
        candidates: list[str] = []
        if self.entra_backend_client_id:
            candidates.append(self.entra_backend_client_id)
            candidates.append(f"api://{self.entra_backend_client_id}")
        candidates.append(self.backend_audience)
        deduped: list[str] = []
        for candidate in candidates:
            if candidate and candidate not in deduped:
                deduped.append(candidate)
        return deduped

    @property
    def authority(self) -> str:
        if self.entra_authority:
            return self.entra_authority.rstrip("/")
        if self.azure_tenant_id:
            return f"https://login.microsoftonline.com/{self.azure_tenant_id}"
        return "https://login.microsoftonline.com/common"

    @property
    def foundry_openai_base_url(self) -> str:
        endpoint = self.azure_ai_project_endpoint or self.azure_ai_foundry_endpoint
        if not endpoint:
            return ""
        endpoint = endpoint.rstrip("/")
        if endpoint.endswith("/openai/v1"):
            return endpoint
        if endpoint.endswith("/openai"):
            return f"{endpoint}/v1"
        return f"{endpoint}/openai/v1"

    @property
    def storage_enabled(self) -> bool:
        return bool(self.azure_storage_account_url and self.azure_storage_container_name)

    @property
    def document_intelligence_enabled(self) -> bool:
        return bool(self.azure_document_intelligence_endpoint)

    @property
    def foundry_enabled(self) -> bool:
        return bool(self.foundry_openai_base_url and self.azure_ai_model_deployment)


@lru_cache
def get_settings() -> Settings:
    return Settings()
