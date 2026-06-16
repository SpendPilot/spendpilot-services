from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from azure.storage.blob import BlobServiceClient
from fastapi import UploadFile

from app.core.azure_identity import get_default_credential
from app.core.config import get_settings


@dataclass
class StoredFile:
    storage_kind: str
    storage_path: str
    storage_url: str | None
    content: bytes


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._blob_service_client: BlobServiceClient | None = None

    def _get_blob_service_client(self) -> BlobServiceClient:
        if self._blob_service_client is None:
            self._blob_service_client = BlobServiceClient(
                account_url=self.settings.azure_storage_account_url,
                credential=get_default_credential(),
            )
        return self._blob_service_client

    async def save_upload(self, upload: UploadFile, max_upload_bytes: int) -> StoredFile:
        content = await upload.read()
        if len(content) > max_upload_bytes:
            raise ValueError("File is too large")
        safe_name = upload.filename or "document.bin"
        blob_name = f"{uuid.uuid4()}-{safe_name}"

        if self.settings.storage_enabled:
            blob_client = self._get_blob_service_client().get_blob_client(
                container=self.settings.azure_storage_container_name,
                blob=blob_name,
            )
            blob_client.upload_blob(content, overwrite=False)
            return StoredFile(
                storage_kind="blob",
                storage_path=blob_name,
                storage_url=blob_client.url,
                content=content,
            )

        upload_dir = Path(self.settings.local_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / blob_name
        target.write_bytes(content)
        return StoredFile(
            storage_kind="local",
            storage_path=str(target),
            storage_url=None,
            content=content,
        )

    def read_bytes(self, storage_kind: str, storage_path: str) -> bytes:
        if storage_kind == "blob":
            blob_client = self._get_blob_service_client().get_blob_client(
                container=self.settings.azure_storage_container_name,
                blob=storage_path,
            )
            return blob_client.download_blob().readall()
        return Path(storage_path).read_bytes()
