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

    company_budget = client.post(
        "/api/finance/budgets",
        headers=owner_headers,
        json={
            "name": "Company July Budget",
            "scope": "company",
            "currency": "INR",
            "amount": "100000.00",
            "month": 7,
            "year": 2026,
            "alert_threshold_percent": 80,
        },
    )
    assert company_budget.status_code == 200

    budget = client.post(
        "/api/finance/budgets",
        headers=owner_headers,
        json={
            "name": "IT July Budget",
            "scope": "department",
            "department_id": it_department["id"],
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


def test_budget_hierarchy_edit_and_delete() -> None:
    client = get_client()
    tenant_id = "tenant-budget-rules"
    owner_headers = _auth_header(client, "owner-budget@example.com", "org_owner", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers).json()["data"]
    it_department = next(item for item in departments if item["name"] == "IT")
    hr_department = next(item for item in departments if item["name"] == "HR")

    company_budget = client.post(
        "/api/finance/budgets",
        headers=owner_headers,
        json={
            "name": "Company August Budget",
            "scope": "company",
            "currency": "INR",
            "amount": "100000.00",
            "month": 8,
            "year": 2026,
            "alert_threshold_percent": 80,
        },
    )
    assert company_budget.status_code == 200
    company_budget_id = company_budget.json()["data"]["id"]

    first_department_budget = client.post(
        "/api/finance/budgets",
        headers=owner_headers,
        json={
            "name": "IT August Budget",
            "scope": "department",
            "department_id": it_department["id"],
            "currency": "INR",
            "amount": "60000.00",
            "month": 8,
            "year": 2026,
            "alert_threshold_percent": 80,
        },
    )
    assert first_department_budget.status_code == 200
    department_budget_id = first_department_budget.json()["data"]["id"]

    too_much = client.post(
        "/api/finance/budgets",
        headers=owner_headers,
        json={
            "name": "HR August Budget",
            "scope": "department",
            "department_id": hr_department["id"],
            "currency": "INR",
            "amount": "50000.00",
            "month": 8,
            "year": 2026,
            "alert_threshold_percent": 80,
        },
    )
    assert too_much.status_code == 400
    assert "cannot exceed the company budget" in too_much.json()["detail"]

    updated_department_budget = client.patch(
        f"/api/finance/budgets/{department_budget_id}",
        headers=owner_headers,
        json={"amount": "55000.00"},
    )
    assert updated_department_budget.status_code == 200
    assert updated_department_budget.json()["data"]["amount"] == "55000.00"

    lowered_company = client.patch(
        f"/api/finance/budgets/{company_budget_id}",
        headers=owner_headers,
        json={"amount": "50000.00"},
    )
    assert lowered_company.status_code == 400
    assert "cannot be lower than the total department budgets" in lowered_company.json()["detail"]

    deleted = client.delete(f"/api/finance/budgets/{department_budget_id}", headers=owner_headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "deleted"


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


def test_company_threshold_and_department_approval_flow() -> None:
    client = get_client()
    tenant_id = "tenant-threshold"
    owner_headers = _auth_header(client, "owner3@example.com", "org_owner", tenant_id)
    employee_headers = _auth_header(client, "employee3@example.com", "employee", tenant_id)
    dept_headers = _auth_header(client, "head3@example.com", "employee", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers).json()["data"]
    finance_department = next(item for item in departments if item["name"] == "IT")
    members = client.get("/api/admin/members", headers=owner_headers).json()["data"]
    employee_member = next(item for item in members if item["user"]["email"] == "employee3@example.com")
    dept_member = next(item for item in members if item["user"]["email"] == "head3@example.com")
    client.patch(f"/api/admin/members/{employee_member['id']}", headers=owner_headers, json={"department_id": finance_department["id"]})
    client.patch(
        f"/api/admin/members/{dept_member['id']}",
        headers=owner_headers,
        json={"department_id": finance_department["id"], "role": "dept_head"},
    )

    categories = client.get("/api/finance/categories", headers=owner_headers).json()["data"]
    category_id = categories[0]["id"]
    category_name = categories[0]["name"]

    threshold = client.post(
        "/api/finance/spend-limits",
        headers=owner_headers,
        json={
            "requires_approval_above_amount": "2000.00",
            "active": True,
        },
    )
    assert threshold.status_code == 200

    department_rule = client.post(
        "/api/finance/spend-limits",
        headers=owner_headers,
        json={
            "department_id": finance_department["id"],
            "category": category_name,
            "monthly_limit": "25000.00",
            "active": True,
        },
    )
    assert department_rule.status_code == 200

    low_expense = client.post(
        "/api/finance/expenses/variable",
        headers=employee_headers,
        json={
            "title": "Taxi ride",
            "vendor_name": "City Cab",
            "category_id": category_id,
            "currency": "INR",
            "amount": "1200.00",
            "expense_date": "2026-07-10",
            "description": "Client meeting travel",
        },
    )
    assert low_expense.status_code == 200
    assert low_expense.json()["data"]["status"] == "pending_dept_head"
    assert low_expense.json()["data"]["policy_status"] == "needs_dept_head_review"

    low_expense_id = low_expense.json()["data"]["id"]
    low_approved = client.post(
        f"/api/finance/expenses/{low_expense_id}/approve",
        headers=dept_headers,
        json={"comment": "Within department policy"},
    )
    assert low_approved.status_code == 200
    assert low_approved.json()["data"]["status"] == "approved_by_dept_head"

    high_expense = client.post(
        "/api/finance/expenses/variable",
        headers=employee_headers,
        json={
            "title": "Monitor purchase",
            "vendor_name": "Office Hub",
            "category_id": category_id,
            "currency": "INR",
            "amount": "4200.00",
            "expense_date": "2026-07-12",
            "description": "Desk setup",
        },
    )
    assert high_expense.status_code == 200
    assert high_expense.json()["data"]["status"] == "pending_dept_head"
    assert high_expense.json()["data"]["policy_status"] == "needs_org_owner_review"

    high_expense_id = high_expense.json()["data"]["id"]
    forwarded = client.post(
        f"/api/finance/expenses/{high_expense_id}/approve",
        headers=dept_headers,
        json={"comment": "Crosses company threshold"},
    )
    assert forwarded.status_code == 200
    assert forwarded.json()["data"]["status"] == "forwarded_to_org_owner"


def test_owner_can_cancel_recurring_expense() -> None:
    client = get_client()
    tenant_id = "tenant-cancel"
    owner_headers = _auth_header(client, "owner4@example.com", "org_owner", tenant_id)

    created = client.post(
        "/api/finance/recurring-expenses",
        headers=owner_headers,
        json={
            "name": "Payroll processor",
            "vendor_name": "Payroll Cloud",
            "category": "Operations",
            "amount": "9000.00",
            "currency": "INR",
            "billing_cycle": "monthly",
            "priority": "pay_this_week",
        },
    )
    assert created.status_code == 200
    recurring_id = created.json()["data"]["id"]

    cancelled = client.post(
        f"/api/finance/recurring-expenses/{recurring_id}/cancel",
        headers=owner_headers,
        json={"comment": "Service no longer needed"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"


def test_owner_can_delete_spend_limit() -> None:
    client = get_client()
    tenant_id = "tenant-spend-limit-delete"
    owner_headers = _auth_header(client, "owner5@example.com", "org_owner", tenant_id)

    created = client.post(
        "/api/finance/spend-limits",
        headers=owner_headers,
        json={
            "category": "Travel",
            "max_single_expense_amount": "3000.00",
            "monthly_limit": "20000.00",
        },
    )
    assert created.status_code == 200
    spend_limit_id = created.json()["data"]["id"]

    deleted = client.delete(f"/api/finance/spend-limits/{spend_limit_id}", headers=owner_headers)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["status"] == "deleted"
