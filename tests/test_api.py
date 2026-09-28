"""
Real API-level tests using FastAPI's TestClient - hits the actual routes,
real Groq calls under the hood, but no need for uvicorn running separately.

Each test gets a fresh event loop (pytest-asyncio default). The real
uvicorn server only ever has ONE event loop for its whole life, so this
isn't an issue there - but our shared module-level `kokki` object caches
its graph (and the aiosqlite connection inside it) bound to whichever
loop built it. Reset it before each test so it rebuilds fresh in THAT
test's current loop, instead of reusing a stale one from a prior test.
"""
import pytest
from fastapi.testclient import TestClient
from api.server import app
from api import server

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_kokki_graph():
    server.kokki.graph = None


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


def test_chat_stream_endpoint_returns_real_content():
    """
    Confirms the streaming endpoint is wired correctly end-to-end.
    NOTE: doesn't assert on chunk COUNT - FastAPI's TestClient drains the
    whole ASGI response synchronously through its portal, collapsing
    multi-chunk generators into a single read regardless of how many
    pieces were actually yielded. True chunk-by-chunk delivery is already
    proven directly against KokkiAgent.astream_chat() in test_memory.py,
    and against a real running uvicorn server via curl -N.
    """
    with client.stream(
        "POST", "/chat/stream", json={"message": "tell me a short joke"}
    ) as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert text.strip() != ""
