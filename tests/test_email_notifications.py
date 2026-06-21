from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.api.routes import finance as finance_routes
from app.db.session import SessionLocal
from app.services.email_queue import EmailTemplateType
from app.services.finance_service import FinanceService
from app.services.user_service import sync_user_context_from_claims
from functions.email_sender.function_app import process_email_request
from tests.conftest import get_client


class StubEmailQueue:
    def __init__(self) -> None:
        self.requests = []

    def enqueue(self, request) -> None:
        self.requests.append(request)

    def enqueue_many(self, requests) -> None:
        self.requests.extend(list(requests))


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
    token = response.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_new_membership_enqueues_welcome_email() -> None:
    queue = StubEmailQueue()
    now = datetime.now(UTC)

    with SessionLocal() as db:
        sync_user_context_from_claims(
            db,
            {
                "tid": "tenant-email-welcome",
                "oid": "oid-welcome",
                "sub": "sub-welcome",
                "email": "new.user@example.com",
                "preferred_username": "new.user@example.com",
                "name": "New User",
                "iss": "https://login.microsoftonline.com/tenant-email-welcome/v2.0",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "sid": "sid-welcome",
            },
            session_fingerprint="fp-welcome",
            session_identifier="sid-welcome",
            auth_provider="entra",
            user_agent="pytest",
            email_queue=queue,
        )

    assert len(queue.requests) == 1
    assert queue.requests[0].type == EmailTemplateType.WELCOME_EMAIL
    assert str(queue.requests[0].to) == "new.user@example.com"


def test_finance_flow_enqueues_submission_and_approval_emails(monkeypatch) -> None:
    queue = StubEmailQueue()
    monkeypatch.setattr(finance_routes, "finance_service", FinanceService(email_queue=queue))

    client = get_client()
    tenant_id = "tenant-email-finance"
    owner_headers = _auth_header(client, "owner-email@financepilot.com", "org_owner", tenant_id)
    employee_headers = _auth_header(client, "employee-email@financepilot.com", "employee", tenant_id)
    dept_headers = _auth_header(client, "head-email@financepilot.com", "employee", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers).json()["data"]
    it_department = next(item for item in departments if item["name"] == "IT")

    members = client.get("/api/admin/members", headers=owner_headers).json()["data"]
    employee_member = next(item for item in members if item["user"]["email"] == "employee-email@financepilot.com")
    dept_member = next(item for item in members if item["user"]["email"] == "head-email@financepilot.com")
    client.patch(f"/api/admin/members/{employee_member['id']}", headers=owner_headers, json={"department_id": it_department["id"]})
    client.patch(
        f"/api/admin/members/{dept_member['id']}",
        headers=owner_headers,
        json={"department_id": it_department["id"], "role": "dept_head"},
    )

    category_id = client.get("/api/finance/categories", headers=owner_headers).json()["data"][0]["id"]
    expense = client.post(
        "/api/finance/expenses/variable",
        headers=employee_headers,
        json={
            "title": "Mouse",
            "vendor_name": "Office Hub",
            "category_id": category_id,
            "currency": "INR",
            "amount": "900.00",
            "expense_date": "2026-07-10",
            "description": "Developer hardware",
        },
    )
    assert expense.status_code == 200
    expense_id = expense.json()["data"]["id"]

    submission_email = next(request for request in queue.requests if request.type == EmailTemplateType.EXPENSE_SUBMITTED)
    assert str(submission_email.to) == "head-email@financepilot.com"

    approved = client.post(
        f"/api/finance/expenses/{expense_id}/approve",
        headers=dept_headers,
        json={"comment": "Approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved_by_dept_head"

    approval_email = next(request for request in queue.requests if request.type == EmailTemplateType.EXPENSE_APPROVED)
    assert str(approval_email.to) == "employee-email@financepilot.com"


class FakePoller:
    def result(self):
        return type("SendResult", (), {"status": "Succeeded"})()


class FakeEmailClient:
    def __init__(self) -> None:
        self.messages = []

    def begin_send(self, message):
        self.messages.append(message)
        return FakePoller()


def test_function_processes_email_request(monkeypatch) -> None:
    fake_client = FakeEmailClient()
    monkeypatch.setenv("ACS_EMAIL_SENDER_ADDRESS", "DoNotReply@example.azurecomm.net")
    monkeypatch.setattr("functions.email_sender.function_app._get_email_client", lambda: fake_client)

    process_email_request(
        
            '{"type":"EXPENSE_APPROVED","to":"user@example.com","template":"expense-approved",'
            '"data":{"title":"Mouse","amount":"900.00","currency":"INR","status":"approved_by_dept_head"},'
            '"correlationId":"expense-123","idempotencyKey":"expense-approved:expense-123"}'
        
    )

    assert len(fake_client.messages) == 1
    assert fake_client.messages[0]["senderAddress"] == "DoNotReply@example.azurecomm.net"
    assert fake_client.messages[0]["recipients"]["to"][0]["address"] == "user@example.com"
