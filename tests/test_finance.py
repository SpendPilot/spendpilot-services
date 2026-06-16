from tests.conftest import get_client


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


def test_budget_variable_expense_and_approval_flow() -> None:
    client = get_client()
    tenant_id = "tenant-flow"
    owner_headers = _auth_header(client, "owner@example.com", "org_owner", tenant_id)
    employee_headers = _auth_header(client, "employee@example.com", "employee", tenant_id)
    dept_headers = _auth_header(client, "head@example.com", "employee", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers)
    it_department = next(item for item in departments.json()["data"] if item["name"] == "IT")

    members = client.get("/api/admin/members", headers=owner_headers).json()["data"]
    employee_member = next(item for item in members if item["user"]["email"] == "employee@example.com")
    dept_member = next(item for item in members if item["user"]["email"] == "head@example.com")
    client.patch(f"/api/admin/members/{employee_member['id']}", headers=owner_headers, json={"department_id": it_department["id"]})
    client.patch(
        f"/api/admin/members/{dept_member['id']}",
        headers=owner_headers,
        json={"department_id": it_department["id"], "role": "dept_head"},
    )

    categories = client.get("/api/finance/categories", headers=owner_headers)
    category_id = categories.json()["data"][0]["id"]

    budget = client.post(
        "/api/finance/budgets",
        headers=owner_headers,
        json={
            "name": "IT July Budget",
            "scope": "department",
            "department_id": it_department["id"],
            "category_id": category_id,
            "currency": "INR",
            "amount": "50000.00",
            "month": 7,
            "year": 2026,
            "alert_threshold_percent": 80,
        },
    )
    assert budget.status_code == 200

    expense = client.post(
        "/api/finance/expenses/variable",
        headers=employee_headers,
        json={
            "title": "Laptop bag",
            "vendor_name": "Office Hub",
            "category_id": category_id,
            "currency": "INR",
            "amount": "2500.00",
            "expense_date": "2026-07-10",
            "description": "Team equipment",
        },
    )
    assert expense.status_code == 200
    expense_id = expense.json()["data"]["id"]
    assert expense.json()["data"]["status"] == "pending_dept_head"

    forwarded = client.post(
        f"/api/finance/expenses/{expense_id}/forward",
        headers=dept_headers,
        json={"comment": "Looks valid"},
    )
    assert forwarded.status_code == 200
    assert forwarded.json()["data"]["status"] == "forwarded_to_org_owner"

    approved = client.post(
        f"/api/finance/expenses/{expense_id}/approve",
        headers=owner_headers,
        json={"comment": "Approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["data"]["status"] == "approved_by_org_owner"


def test_recurring_request_and_payment_priorities() -> None:
    client = get_client()
    tenant_id = "tenant-recurring"
    owner_headers = _auth_header(client, "owner2@example.com", "org_owner", tenant_id)
    dept_headers = _auth_header(client, "dept@example.com", "employee", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers)
    marketing = next(item for item in departments.json()["data"] if item["name"] == "Marketing")
    members = client.get("/api/admin/members", headers=owner_headers).json()["data"]
    dept_member = next(item for item in members if item["user"]["email"] == "dept@example.com")
    client.patch(
        f"/api/admin/members/{dept_member['id']}",
        headers=owner_headers,
        json={"department_id": marketing["id"], "role": "dept_head"},
    )

    request = client.post(
        "/api/finance/recurring-expense-requests",
        headers=dept_headers,
        json={
            "name": "Campaign tool",
            "vendor_name": "Ads Cloud",
            "category": "Marketing",
            "estimated_amount": "12000.00",
            "currency": "INR",
            "billing_cycle": "monthly",
            "reason": "Campaign operations",
        },
    )
    assert request.status_code == 200

    request_id = request.json()["data"]["id"]
    decided = client.post(
        f"/api/finance/recurring-expense-requests/{request_id}/decision",
        headers=owner_headers,
        json={"approved": True},
    )
    assert decided.status_code == 200
    assert decided.json()["data"]["status"] == "approved"

    recurring = client.get("/api/finance/recurring-expenses", headers=owner_headers)
    assert recurring.status_code == 200
    assert any(item["name"] == "Campaign tool" for item in recurring.json()["data"])

    priorities = client.get("/api/finance/payment-priorities", headers=owner_headers)
    assert priorities.status_code == 200
    assert len(priorities.json()["data"]) >= 1
