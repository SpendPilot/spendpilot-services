from tests.conftest import get_client


def _auth_header(client, email: str, role: str = "employee", tenant_id: str = "local-dev-tenant") -> dict[str, str]:
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


def test_default_departments_and_employee_onboarding_flow() -> None:
    client = get_client()
    tenant_id = "tenant-onboarding"

    owner_headers = _auth_header(client, "owner@example.com", "org_owner", tenant_id)
    departments = client.get("/api/auth/departments", headers=owner_headers)
    assert departments.status_code == 200
    department_names = [item["name"] for item in departments.json()["data"]]
    assert department_names == ["HR", "IT", "Marketing"]

    employee_headers = _auth_header(client, "employee@example.com", "employee", tenant_id)
    profile = client.get("/api/auth/me", headers=employee_headers)
    assert profile.status_code == 200
    assert profile.json()["data"]["effective_role"] == "employee"
    assert profile.json()["data"]["membership"]["onboarding_completed"] is False

    it_department = next(item for item in departments.json()["data"] if item["name"] == "IT")
    onboard = client.post(
        "/api/auth/onboarding/department",
        headers=employee_headers,
        json={"department_id": it_department["id"]},
    )
    assert onboard.status_code == 200
    assert onboard.json()["data"]["department"]["name"] == "IT"
    assert onboard.json()["data"]["onboarding_completed"] is True


def test_org_owner_can_promote_single_department_head_per_department() -> None:
    client = get_client()
    tenant_id = "tenant-dept-heads"

    owner_headers = _auth_header(client, "owner2@example.com", "org_owner", tenant_id)
    employee_one_headers = _auth_header(client, "it1@example.com", "employee", tenant_id)
    employee_two_headers = _auth_header(client, "it2@example.com", "employee", tenant_id)

    departments = client.get("/api/admin/departments", headers=owner_headers)
    assert departments.status_code == 200
    it_department = next(item for item in departments.json()["data"] if item["name"] == "IT")

    client.post(
        "/api/auth/onboarding/department",
        headers=employee_one_headers,
        json={"department_id": it_department["id"]},
    )
    client.post(
        "/api/auth/onboarding/department",
        headers=employee_two_headers,
        json={"department_id": it_department["id"]},
    )

    members = client.get("/api/admin/members", headers=owner_headers)
    assert members.status_code == 200
    memberships = members.json()["data"]
    first_member = next(item for item in memberships if item["user"]["email"] == "it1@example.com")
    second_member = next(item for item in memberships if item["user"]["email"] == "it2@example.com")

    promote_first = client.patch(
        f"/api/admin/members/{first_member['id']}",
        headers=owner_headers,
        json={"role": "dept_head"},
    )
    assert promote_first.status_code == 200
    assert promote_first.json()["data"]["role"] == "dept_head"

    promote_second = client.patch(
        f"/api/admin/members/{second_member['id']}",
        headers=owner_headers,
        json={"role": "dept_head"},
    )
    assert promote_second.status_code == 409
