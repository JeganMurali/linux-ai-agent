"""
Integration tests: the real FastAPI app, real routes, real saver logic - only
the model is scripted and the store is in memory. Covers the wiring the unit
tests cannot: routing, validation, response shapes, status codes, and that a
conversation held through /chat/stream shows up in the history routes.
"""
import importlib
import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from pydantic import TypeAdapter

from kokki import agent as agent_module
from tests.fakes import ScriptedChatModel, ToolTurn


@pytest.fixture
def api(monkeypatch):
    """api(script) -> TestClient wired to a fresh in-memory agent."""
    server = importlib.import_module("api.server")
    schemas = importlib.import_module("api.schemas")

    def make(script):
        saver = MemorySaver()

        async def checkpointer():
            return saver

        monkeypatch.setattr(agent_module, "get_checkpointer", checkpointer)
        monkeypatch.setattr(agent_module, "get_llm", lambda model=ScriptedChatModel(script=script): model)
        server.kokki.graph = None
        client = TestClient(server.app)
        client.schemas = schemas
        return client

    yield make
    server.kokki.graph = None


def chat(client, message, thread):
    with client.stream("POST", "/chat/stream", json={"message": message, "thread_id": thread}) as response:
        assert response.status_code == 200
        return [json.loads(line) for line in response.iter_lines() if line]


REPLIES = [["reply"]] * 12


def test_the_server_still_starts_and_the_old_routes_still_work(api):
    client = api(REPLIES)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.post("/threads").status_code == 200, "POST /threads must coexist with GET /threads"


def test_an_empty_store_lists_no_sessions(api):
    response = api(REPLIES).get("/threads")
    assert response.status_code == 200
    assert response.json() == []


def test_a_conversation_held_through_the_stream_route_appears_in_the_list(api):
    client = api([["Hi, roast served."]])
    events = chat(client, "open files please", "bar-42")
    assert events[-1] == {"type": "done"}
    [row] = client.get("/threads").json()
    assert (row["thread_id"], row["title"], row["message_count"]) == ("bar-42", "open files please", 2)


def test_list_response_matches_the_declared_shape(api):
    client = api(REPLIES)
    chat(client, "hello", "bar-1")
    parsed = TypeAdapter(list[client.schemas.SessionSummary]).validate_python(client.get("/threads").json())
    assert parsed[0].thread_id == "bar-1"


def test_list_is_newest_first_and_prefix_filters_the_test_junk(api):
    client = api(REPLIES)
    for thread in ("bar-1", "evtest", "bar-2"):
        chat(client, "hi", thread)
    assert [r["thread_id"] for r in client.get("/threads").json()] == ["bar-2", "evtest", "bar-1"]
    assert [r["thread_id"] for r in client.get("/threads?prefix=bar").json()] == ["bar-2", "bar-1"]


def test_limit_is_applied(api):
    client = api(REPLIES)
    for thread in ("bar-1", "bar-2", "bar-3"):
        chat(client, "hi", thread)
    assert [r["thread_id"] for r in client.get("/threads?limit=2").json()] == ["bar-3", "bar-2"]


@pytest.mark.parametrize("bad", ["0", "-1", "101", "many"])
def test_a_bad_limit_is_rejected_with_422(api, bad):
    assert api(REPLIES).get(f"/threads?limit={bad}").status_code == 422


def test_messages_route_returns_the_conversation_in_order(api):
    client = api([["First reply"], ["Second reply"]])
    chat(client, "one", "bar-1")
    chat(client, "two", "bar-1")
    response = client.get("/threads/bar-1/messages")
    assert response.status_code == 200
    assert response.json() == [
        {"role": "you", "text": "one"}, {"role": "kokki", "text": "First reply"},
        {"role": "you", "text": "two"}, {"role": "kokki", "text": "Second reply"},
    ]


def test_messages_response_matches_the_declared_shape(api):
    client = api(REPLIES)
    chat(client, "hello", "bar-1")
    parsed = TypeAdapter(list[client.schemas.SessionMessage]).validate_python(client.get("/threads/bar-1/messages").json())
    assert [m.role for m in parsed] == ["you", "kokki"]


def test_tool_calls_stay_out_of_the_history(api):
    client = api([ToolTurn("system_control", {"command": "echo hi"}), ["Ran it."]])
    events = chat(client, "run echo", "bar-1")
    assert events[0] == {"type": "tool", "name": "system_control"}
    messages = client.get("/threads/bar-1/messages").json()
    assert [m["role"] for m in messages] == ["you", "kokki"]


def test_an_unknown_thread_is_a_404_with_a_reason(api):
    response = api(REPLIES).get("/threads/does-not-exist/messages")
    assert response.status_code == 404
    assert response.json() == {"detail": "no such thread"}


def test_a_path_with_extra_slashes_never_reaches_the_handler(api):
    assert api(REPLIES).get("/threads/a/b/messages").status_code == 404


def test_history_survives_a_new_server_object_because_it_lives_in_the_store(api):
    client = api([["Remembered."]])
    chat(client, "keep this", "bar-9")
    server = importlib.import_module("api.server")
    saver = server.kokki.graph.checkpointer
    server.kokki.graph = None                      # simulate the graph being rebuilt (as after a restart)

    async def same_saver():
        return saver
    agent_module.get_checkpointer = same_saver
    assert client.get("/threads/bar-9/messages").json()[0] == {"role": "you", "text": "keep this"}
