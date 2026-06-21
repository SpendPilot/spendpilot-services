from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

import azure.functions as func

logger = logging.getLogger(__name__)


@lru_cache
def _get_email_client():
    from azure.communication.email import EmailClient
    from azure.identity import DefaultAzureCredential

    connection_string = os.getenv("ACS_EMAIL_CONNECTION_STRING", "").strip()
    if connection_string:
        return EmailClient.from_connection_string(connection_string)

    endpoint = os.getenv("ACS_EMAIL_ENDPOINT", "").strip()
    if not endpoint:
        raise RuntimeError("ACS_EMAIL_ENDPOINT or ACS_EMAIL_CONNECTION_STRING must be configured.")

    return EmailClient(
        endpoint=endpoint,
        credential=DefaultAzureCredential(exclude_interactive_browser_credential=True),
    )


def process_email_request(payload: str) -> None:
    from email_templates import render_email
    from models import EmailRequest

    request = EmailRequest.model_validate_json(payload)
    sender_address = os.getenv("ACS_EMAIL_SENDER_ADDRESS", "").strip()
    if not sender_address:
        raise RuntimeError("ACS_EMAIL_SENDER_ADDRESS must be configured.")

    rendered = render_email(request)
    message = {
        "content": {
            "subject": rendered.subject,
            "plainText": rendered.plain_text,
            "html": rendered.html,
        },
        "recipients": {
            "to": [
                {
                    "address": request.to,
                }
            ]
        },
        "senderAddress": sender_address,
    }
    poller = _get_email_client().begin_send(message)
    result = poller.result()
    logger.info(
        "Email send completed for correlation_id=%s template=%s status=%s",
        request.correlation_id,
        request.type,
        getattr(result, "status", "unknown"),
    )


def main(message: func.ServiceBusMessage) -> None:
    correlation_id = message.correlation_id or message.message_id or "unknown"
    try:
        process_email_request(message.get_body().decode("utf-8"))
    except json.JSONDecodeError:
        logger.exception("Invalid JSON payload received for correlation_id=%s", correlation_id)
        raise
    except Exception:
        logger.exception("Email send failed for correlation_id=%s", correlation_id)
        raise
