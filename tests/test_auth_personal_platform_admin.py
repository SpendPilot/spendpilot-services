from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.user_service import (
    MICROSOFT_CONSUMER_TENANT_ID,
    PERSONAL_ACCOUNT_TENANT_PREFIX,
    sync_user_context_from_claims,
)


def _consumer_payload(email: str) -> dict:
    now = datetime.now(UTC)
    return {
        "tid": MICROSOFT_CONSUMER_TENANT_ID,
        "sub": f"sub-{email}",
        "email": email,
        "preferred_username": email,
        "name": "Platform Owner",
        "iss": f"https://login.microsoftonline.com/{MICROSOFT_CONSUMER_TENANT_ID}/v2.0",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "sid": f"sid-{email}",
    }


def _guest_personal_payload(
    email: str,
    oid: str,
    *,
    tenant_id: str = "11111111-2222-3333-4444-555555555555",
) -> dict:
    now = datetime.now(UTC)
    return {
        "tid": tenant_id,
        "oid": oid,
        "sub": f"sub-{oid}",
        "email": email,
        "preferred_username": email,
        "name": "Guest User",
        "idp": "live.com",
        "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "sid": f"sid-{oid}",
    }


def test_personal_account_bootstraps_isolated_workspace(monkeypatch) -> None:
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "owner@outlook.com")
    get_settings.cache_clear()

    with SessionLocal() as db:
        context = sync_user_context_from_claims(
            db,
            _consumer_payload("owner@outlook.com"),
            session_fingerprint="fingerprint-owner",
            session_identifier="session-owner",
            auth_provider="entra",
            user_agent="pytest",
        )

    assert context.user.platform_role == "platform_admin"
    assert context.organization.tenant_id.startswith(f"{PERSONAL_ACCOUNT_TENANT_PREFIX}:")
    assert context.organization.name == "Platform Owner Workspace"
    assert context.membership.role == "org_owner"


def test_personal_accounts_do_not_share_the_consumer_tenant_workspace(monkeypatch) -> None:
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    get_settings.cache_clear()

    with SessionLocal() as db:
        first = sync_user_context_from_claims(
            db,
            _consumer_payload("someone@outlook.com"),
            session_fingerprint="fingerprint-user-1",
            session_identifier="session-user-1",
            auth_provider="entra",
            user_agent="pytest",
        )
        first_org_id = first.organization.id
        first_tenant_id = first.organization.tenant_id
        first_role = first.membership.role
        second = sync_user_context_from_claims(
            db,
            _consumer_payload("another@outlook.com"),
            session_fingerprint="fingerprint-user-2",
            session_identifier="session-user-2",
            auth_provider="entra",
            user_agent="pytest",
        )
        second_org_id = second.organization.id
        second_tenant_id = second.organization.tenant_id
        second_role = second.membership.role

    assert first_org_id != second_org_id
    assert first_tenant_id != second_tenant_id
    assert first_role == "org_owner"
    assert second_role == "org_owner"

    os.environ.pop("PLATFORM_ADMIN_EMAILS", None)
    get_settings.cache_clear()


def test_guest_personal_account_in_org_tenant_joins_tenant_workspace(monkeypatch) -> None:
    monkeypatch.delenv("PLATFORM_ADMIN_EMAILS", raising=False)
    get_settings.cache_clear()
    tenant_id = "99999999-8888-7777-6666-555555555555"

    with SessionLocal() as db:
        native = sync_user_context_from_claims(
            db,
            {
                "tid": tenant_id,
                "oid": "oid-native",
                "sub": "sub-native",
                "email": "admin@abccompany.com",
                "preferred_username": "admin@abccompany.com",
                "name": "Admin",
                "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
                "sid": "sid-native",
            },
            session_fingerprint="fingerprint-native",
            session_identifier="session-native",
            auth_provider="entra",
            user_agent="pytest",
        )
        guest = sync_user_context_from_claims(
            db,
            _guest_personal_payload(
                "lijazsalim_gmail.com#EXT#@lijazsalimgmail.onmicrosoft.com",
                "oid-guest",
                tenant_id=tenant_id,
            ),
            session_fingerprint="fingerprint-guest",
            session_identifier="session-guest",
            auth_provider="entra",
            user_agent="pytest",
        )

    assert native.organization.id == guest.organization.id
    assert native.organization.tenant_id == tenant_id
    assert guest.organization.tenant_id == tenant_id
    assert guest.membership.role == "employee"
