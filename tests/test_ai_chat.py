from app.api.routes.ai import ai_chat_service
from app.services.ai_agent_service import AgentAnswer
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


def test_ai_chat_falls_back_when_agent_fails(monkeypatch) -> None:
    client = get_client()
    headers = _auth_header(client, "fallback-ai@example.com", "org_owner", "tenant-fallback-ai")

    def _fail(*args, **kwargs):
        raise RuntimeError("foundry unavailable")

    monkeypatch.setattr(ai_chat_service.agent_service, "answer", _fail)

    response = client.post(
        "/api/ai/chat",
        headers=headers,
        json={"message": "How is my cash flow this month?"},
    )
    assert response.status_code == 200
    reply = response.json()["data"]["reply"]
    assert reply["grounded_context"]["fallback_used"] is True
    assert reply["sources"][0]["tool_name"] == "get_finance_dashboard_summary"


def test_ai_chat_returns_grounded_sources_and_followups(monkeypatch) -> None:
    client = get_client()
    headers = _auth_header(client, "agent-ai@example.com", "org_owner", "tenant-agent-ai")

    def _answer(*args, **kwargs):
        return AgentAnswer(
            answer="You have 2 pending approvals and one urgent payment.",
            sources=[
                {"label": "Pending approvals", "type": "tool", "tool_name": "get_pending_approvals_summary"},
                {"label": "Urgent payments", "type": "tool", "tool_name": "get_urgent_payments"},
            ],
            grounded_context={
                "used_tools": ["get_pending_approvals_summary", "get_urgent_payments"],
                "confidence": "high",
                "time_range": {"label": "current_month"},
            },
            suggested_followups=["Show me the urgent payment", "What caused the approval backlog?"],
        )

    monkeypatch.setattr(ai_chat_service.agent_service, "answer", _answer)

    response = client.post(
        "/api/ai/chat",
        headers=headers,
        json={"message": "What needs my attention today?"},
    )
    assert response.status_code == 200
    reply = response.json()["data"]["reply"]
    assert reply["sources"][0]["label"] == "Pending approvals"
    assert reply["grounded_context"]["confidence"] == "high"
    assert reply["suggested_followups"] == ["Show me the urgent payment", "What caused the approval backlog?"]

    sessions = client.get("/api/ai/sessions", headers=headers)
    assert sessions.status_code == 200
    stored_reply = sessions.json()["data"][0]["messages"][-1]
    assert stored_reply["sources"][1]["tool_name"] == "get_urgent_payments"
