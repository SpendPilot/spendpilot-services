from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.session import SessionLocal
from app.services.user_service import sync_user_context_from_claims


def _workforce_payload(email: str, oid: str, *, tenant_id: str = "11111111-2222-3333-4444-555555555555") -> dict:
    now = datetime.now(UTC)
    return {
        "tid": tenant_id,
        "oid": oid,
        "sub": f"sub-{oid}",
        "email": email,
        "preferred_username": email,
        "name": email.split("@")[0].title(),
        "iss": f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "sid": f"sid-{oid}",
    }


def test_second_user_in_same_tenant_defaults_to_employee() -> None:
    tenant_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    with SessionLocal() as db:
        first = sync_user_context_from_claims(
            db,
            _workforce_payload("admin@abccompany.com", "oid-admin", tenant_id=tenant_id),
            session_fingerprint="fp-admin",
            session_identifier="sid-admin",
            auth_provider="entra",
            user_agent="pytest",
        )
        second = sync_user_context_from_claims(
            db,
            _workforce_payload("employee@abccompany.com", "oid-employee", tenant_id=tenant_id),
            session_fingerprint="fp-employee",
            session_identifier="sid-employee",
            auth_provider="entra",
            user_agent="pytest",
        )
        first_org_id = first.organization.id
        first_role = first.membership.role
        second_org_id = second.organization.id
        second_role = second.membership.role

    assert first_org_id == second_org_id
    assert first_role == "org_owner"
    assert second_role == "employee"
