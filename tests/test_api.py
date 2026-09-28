"""
Real API-level tests using FastAPI's TestClient - hits the actual routes,
real Groq calls under the hood, but no need for uvicorn running separately.
"""
from fastapi.testclient import TestClient
from api.server import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_thread_returns_unique_ids():
    thread_a = client.post("/threads").json()["thread_id"]
    thread_b = client.post("/threads").json()["thread_id"]
    assert thread_a != thread_b


def test_chat_uses_default_thread_when_none_given():
    response = client.post("/chat", json={"message": "hi"})
    assert response.status_code == 200
    body = response.json()
    assert "reply" in body
    assert body["thread_id"] == "main"


def test_chat_respects_explicit_thread_id():
    thread_id = client.post("/threads").json()["thread_id"]
    response = client.post("/chat", json={"message": "hi", "thread_id": thread_id})
    assert response.json()["thread_id"] == thread_id
