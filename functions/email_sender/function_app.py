from __future__ import annotations

from . import send_email as send_email_module


def _get_email_client():
    return send_email_module._get_email_client()


def process_email_request(payload: str) -> None:
    original_get_email_client = send_email_module._get_email_client
    send_email_module._get_email_client = _get_email_client
    try:
        send_email_module.process_email_request(payload)
    finally:
        send_email_module._get_email_client = original_get_email_client


def main(message) -> None:
    original_get_email_client = send_email_module._get_email_client
    send_email_module._get_email_client = _get_email_client
    try:
        send_email_module.main(message)
    finally:
        send_email_module._get_email_client = original_get_email_client


__all__ = ["_get_email_client", "main", "process_email_request"]
