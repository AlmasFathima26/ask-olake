from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_ask_empty_question_returns_400():
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 400


def test_ask_missing_question_returns_400():
    r = client.post("/ask", json={})
    assert r.status_code == 422


def test_health_returns_chunks_count():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["chunks"], int)
    assert body["chunks"] > 0


def test_widget_returns_html():
    r = client.get("/widget")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Ask OLake" in r.text


def test_root_endpoint():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["endpoint"] == "POST /ask"
