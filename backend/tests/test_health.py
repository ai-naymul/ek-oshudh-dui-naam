from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_live_not_cached():
    a = client.get("/health").json()
    b = client.get("/health").json()
    assert a["status"] == "ok"
    assert a["request_id"] != b["request_id"]
