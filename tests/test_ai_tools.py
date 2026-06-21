from __future__ import annotations

from app.core.security import AuthenticatedPrincipal
from app.db.session import SessionLocal
from app.services.ai_tools import AIToolbox
from tests.conftest import get_client


def _auth_payload(client, email: str, role: str, tenant_id: str) -> dict:
    response = client.post(
        "/api/auth/dev-login",
        json={
            "email": email,
            "display_name": email.split("@")[0].title(),
            "role": role,
            "tenant_id": tenant_id,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]["profile"]


def _auth_header(client, email: str, role: str, tenant_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/dev-login",
        json={
            "email": email,
            "display_name": email.split("@")[0].title(),
            "role": role,
            "tenant_id": tenant_id,
        },
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def _principal_from_profile(profile: dict) -> AuthenticatedPrincipal:
    membership = profile["membership"]
    organization = profile["organization"]
    user = profile["user"]
    session = profile["session"]
    department = membership.get("department") or {}
    return AuthenticatedPrincipal(
        user_id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        role=profile["effective_role"],
        platform_role=user["platform_role"],
        membership_id=membership["id"],
        organization_id=organization["id"],
        organization_name=organization["name"],
        organization_slug=organization["slug"],
        default_currency=organization["default_currency"],
        membership_status=membership["status"],
        department_id=membership["department_id"],
        department_name=department.get("name"),
        onboarding_completed=membership["onboarding_completed"],
        tenant_id=organization["tenant_id"],
        entra_oid=user.get("entra_oid"),
        session_id=session["id"],
    )


def _seed_finance_visibility_workspace(client, tenant_id: str) -> dict[str, object]:
    owner_headers = _auth_header(client, "owner-tools@example.com", "org_owner", tenant_id)
    employee_it_headers = _auth_header(client, "employee-it@example.com", "employee", tenant_id)
    employee_marketing_headers = _auth_header(client, "employee-marketing@example.com", "employee", tenant_id)
    _auth_header(client, "dept-head@example.com", "employee", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers).json()["data"]
    it_department = next(item for item in departments if item["name"] == "IT")
    marketing_department = next(item for item in departments if item["name"] == "Marketing")

    members = client.get("/api/admin/members", headers=owner_headers).json()["data"]
    employee_it_member = next(item for item in members if item["user"]["email"] == "employee-it@example.com")
    employee_marketing_member = next(item for item in members if item["user"]["email"] == "employee-marketing@example.com")
    dept_head_member = next(item for item in members if item["user"]["email"] == "dept-head@example.com")

    client.patch(
        f"/api/admin/members/{employee_it_member['id']}",
        headers=owner_headers,
        json={"department_id": it_department["id"]},
    )
    client.patch(
        f"/api/admin/members/{employee_marketing_member['id']}",
        headers=owner_headers,
        json={"department_id": marketing_department["id"]},
    )
    client.patch(
        f"/api/admin/members/{dept_head_member['id']}",
        headers=owner_headers,
        json={"department_id": it_department["id"], "role": "dept_head"},
    )

    category_id = client.get("/api/finance/categories", headers=owner_headers).json()["data"][0]["id"]
    it_expense = client.post(
        "/api/finance/expenses/variable",
        headers=employee_it_headers,
        json={
            "title": "IT Laptop Bag",
            "vendor_name": "Office Hub",
            "category_id": category_id,
            "currency": "INR",
            "amount": "1500.00",
            "expense_date": "2026-06-10",
            "description": "IT team gear",
        },
    ).json()["data"]
    marketing_expense = client.post(
        "/api/finance/expenses/variable",
        headers=employee_marketing_headers,
        json={
            "title": "Marketing Banner",
            "vendor_name": "Brand House",
            "category_id": category_id,
            "currency": "INR",
            "amount": "2200.00",
            "expense_date": "2026-06-11",
            "description": "Campaign materials",
        },
    ).json()["data"]

    it_document = client.post(
        "/api/documents/upload",
        headers=employee_it_headers,
        files={"file": ("it-note.txt", b"IT laptop bag receipt for 1500 INR", "text/plain")},
    ).json()["data"]["document"]
    marketing_document = client.post(
        "/api/documents/upload",
        headers=employee_marketing_headers,
        files={"file": ("marketing-note.txt", b"Marketing banner invoice for 2200 INR", "text/plain")},
    ).json()["data"]["document"]

    owner_profile = _auth_payload(client, "owner-tools@example.com", "org_owner", tenant_id)
    dept_head_profile = _auth_payload(client, "dept-head@example.com", "employee", tenant_id)
    employee_it_profile = _auth_payload(client, "employee-it@example.com", "employee", tenant_id)
    employee_marketing_profile = _auth_payload(client, "employee-marketing@example.com", "employee", tenant_id)

    return {
        "owner": _principal_from_profile(owner_profile),
        "dept_head": _principal_from_profile(dept_head_profile),
        "employee_it": _principal_from_profile(employee_it_profile),
        "employee_marketing": _principal_from_profile(employee_marketing_profile),
        "it_expense": it_expense,
        "marketing_expense": marketing_expense,
        "it_document": it_document,
        "marketing_document": marketing_document,
    }


def test_search_expenses_summary_respects_role_visibility() -> None:
    client = get_client()
    tenant_id = "tenant-ai-tools-expenses"
    seeded = _seed_finance_visibility_workspace(client, tenant_id)
    toolbox = AIToolbox()

    with SessionLocal() as db:
        owner_result = toolbox.search_expenses_summary(db, seeded["owner"], limit=5)
        dept_result = toolbox.search_expenses_summary(db, seeded["dept_head"], limit=5)
        employee_result = toolbox.search_expenses_summary(db, seeded["employee_it"], limit=5)

    assert {item["title"] for item in owner_result.payload["items"]} == {"IT Laptop Bag", "Marketing Banner"}
    assert [item["title"] for item in dept_result.payload["items"]] == ["IT Laptop Bag"]
    assert [item["title"] for item in employee_result.payload["items"]] == ["IT Laptop Bag"]


def test_get_pending_approvals_summary_respects_role_visibility() -> None:
    client = get_client()
    tenant_id = "tenant-ai-tools-pending"
    seeded = _seed_finance_visibility_workspace(client, tenant_id)
    toolbox = AIToolbox()

    with SessionLocal() as db:
        owner_result = toolbox.get_pending_approvals_summary(db, seeded["owner"], limit=5)
        dept_result = toolbox.get_pending_approvals_summary(db, seeded["dept_head"], limit=5)
        marketing_employee_result = toolbox.get_pending_approvals_summary(db, seeded["employee_marketing"], limit=5)

    assert owner_result.payload["pending_count"] == 2
    assert dept_result.payload["pending_count"] == 1
    assert marketing_employee_result.payload["pending_count"] == 1
    assert dept_result.payload["items"][0]["title"] == "IT Laptop Bag"
    assert marketing_employee_result.payload["items"][0]["title"] == "Marketing Banner"


def test_list_relevant_documents_respects_role_visibility() -> None:
    client = get_client()
    tenant_id = "tenant-ai-tools-docs"
    seeded = _seed_finance_visibility_workspace(client, tenant_id)
    toolbox = AIToolbox()

    with SessionLocal() as db:
        owner_docs = toolbox.list_relevant_documents(db, seeded["owner"], limit=5)
        dept_docs = toolbox.list_relevant_documents(db, seeded["dept_head"], limit=5)
        employee_docs = toolbox.list_relevant_documents(db, seeded["employee_it"], limit=5)

    assert {item["filename"] for item in owner_docs.payload["documents"]} == {"it-note.txt", "marketing-note.txt"}
    assert [item["filename"] for item in dept_docs.payload["documents"]] == ["it-note.txt"]
    assert [item["filename"] for item in employee_docs.payload["documents"]] == ["it-note.txt"]


def test_get_document_text_excerpt_returns_safe_excerpt_for_visible_text_documents() -> None:
    client = get_client()
    tenant_id = "tenant-ai-tools-excerpt"
    seeded = _seed_finance_visibility_workspace(client, tenant_id)
    toolbox = AIToolbox()

    with SessionLocal() as db:
        excerpt = toolbox.get_document_text_excerpt(db, seeded["employee_it"], seeded["it_document"]["id"], max_chars=80)

    assert excerpt.payload["source"] == "blob_excerpt"
    assert "IT laptop bag receipt" in excerpt.payload["excerpt"]
