from tests.conftest import get_client


def _auth_header(client, email: str, role: str, tenant_id: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/dev-login",
        json={"email": email, "display_name": email.split("@")[0].title(), "role": role, "tenant_id": tenant_id},
    )
    return {"Authorization": f"Bearer {response.json()['data']['access_token']}"}


def test_ai_chat_session_is_tenant_and_user_scoped() -> None:
    client = get_client()
    headers = _auth_header(client, "owner-ai@example.com", "org_owner", "tenant-ai")

    response = client.post(
        "/api/ai/chat",
        headers=headers,
        json={"message": "How is my cash flow this month?"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["reply"]["role"] == "assistant"
    assert payload["session"]["id"]

    sessions = client.get("/api/ai/sessions", headers=headers)
    assert sessions.status_code == 200
    assert len(sessions.json()["data"]) == 1
