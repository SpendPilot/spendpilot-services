from tests.conftest import get_client


def test_dev_login_and_me() -> None:
    client = get_client()

    response = client.post(
        "/api/auth/dev-login",
        json={"email": "admin@example.com", "display_name": "Admin User", "role": "org_admin"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["user"]["email"] == "admin@example.com"
    assert me.json()["data"]["effective_role"] == "org_owner"
