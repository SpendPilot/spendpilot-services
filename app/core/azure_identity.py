from functools import lru_cache

from azure.identity import DefaultAzureCredential

from app.core.config import get_settings


@lru_cache
def get_default_credential() -> DefaultAzureCredential:
    settings = get_settings()
    return DefaultAzureCredential(
        managed_identity_client_id=settings.azure_client_id or None,
        exclude_interactive_browser_credential=True,
    )
