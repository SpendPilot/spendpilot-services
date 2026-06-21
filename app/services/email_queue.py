from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from enum import StrEnum
from functools import lru_cache
from typing import Any

from azure.servicebus import ServiceBusClient, ServiceBusMessage
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.azure_identity import get_default_credential
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailTemplateType(StrEnum):
    WELCOME_EMAIL = "WELCOME_EMAIL"
    PASSWORD_RESET = "PASSWORD_RESET"
    EXPENSE_SUBMITTED = "EXPENSE_SUBMITTED"
    EXPENSE_APPROVED = "EXPENSE_APPROVED"
    EXPENSE_REJECTED = "EXPENSE_REJECTED"


class EmailRequest(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: EmailTemplateType
    to: EmailStr
    template: str
    data: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(alias="correlationId")
    idempotency_key: str = Field(alias="idempotencyKey")


class EmailQueuePublisher:
    def __init__(
        self,
        settings: Settings | None = None,
        servicebus_client_factory: Callable[[], ServiceBusClient] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._servicebus_client_factory = servicebus_client_factory

    @property
    def enabled(self) -> bool:
        return self.settings.email_queue_enabled

    def enqueue(self, request: EmailRequest) -> None:
        self.enqueue_many([request])

    def enqueue_many(self, requests: Sequence[EmailRequest]) -> None:
        if not requests:
            return
        if not self.enabled:
            logger.info("Email queue is disabled; skipping %s email request(s).", len(requests))
            return

        with self._build_service_bus_client() as client:
            sender = client.get_queue_sender(queue_name=self.settings.azure_service_bus_queue_name)
            with sender:
                sender.send_messages([self._to_service_bus_message(request) for request in requests])
        logger.info("Queued %s email request(s) to Service Bus.", len(requests))

    def _build_service_bus_client(self) -> ServiceBusClient:
        if self._servicebus_client_factory is not None:
            return self._servicebus_client_factory()
        if self.settings.azure_service_bus_connection_string:
            return ServiceBusClient.from_connection_string(self.settings.azure_service_bus_connection_string)
        return ServiceBusClient(
            fully_qualified_namespace=self.settings.azure_service_bus_fully_qualified_namespace,
            credential=get_default_credential(),
        )

    @staticmethod
    def _to_service_bus_message(request: EmailRequest) -> ServiceBusMessage:
        return ServiceBusMessage(
            body=request.model_dump_json(by_alias=True),
            content_type="application/json",
            correlation_id=request.correlation_id,
            message_id=request.idempotency_key,
            subject=request.type,
        )


@lru_cache
def get_email_queue_publisher() -> EmailQueuePublisher:
    return EmailQueuePublisher()
