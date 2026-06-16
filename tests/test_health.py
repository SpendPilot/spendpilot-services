from tests.conftest import get_client


def test_health_and_ready_endpoints() -> None:
    client = get_client()

    health = client.get("/health")
    ready = client.get("/ready")

    assert health.status_code == 200
    assert health.json()["service"] == "platform-api"
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"
