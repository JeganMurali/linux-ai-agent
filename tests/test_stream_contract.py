"""
The streaming contract: KokkiAgent.astream_chat yields event dicts and GET
/chat/stream sends them as NDJSON. All of this runs against a scripted fake
model + in-memory checkpointer, so it is free, offline, and deterministic.
"""
import groq
import httpx
import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import MemorySaver
from pydantic import TypeAdapter

from api import server
from api.schemas import ChatEvent
from kokki import agent as agent_module
from kokki.agent import KokkiAgent
from tests.fakes import ScriptedChatModel, ToolTurn

event_adapter = TypeAdapter(ChatEvent)
TERMINAL = ("done", "error")


@pytest.fixture
def make_agent(monkeypatch):
    """Returns build(script) -> (agent, fake_model), fully offline."""
    async def fake_checkpointer():
        return MemorySaver()

    monkeypatch.setattr(agent_module, "get_checkpointer", fake_checkpointer)

    def build(script, **model_kwargs):
        model = ScriptedChatModel(script=script, **model_kwargs)
        monkeypatch.setattr(agent_module, "get_llm", lambda: model)
        return KokkiAgent(), model

    return build


async def events_of(agent, message="hi", thread_id="t"):
    return [e async for e in agent.astream_chat(message, thread_id=thread_id)]


def types(events):
    return [e["type"] for e in events]


# ---------------------------------------------------------------- unit level

async def test_plain_reply_is_tokens_then_done_with_spaces_kept(make_agent):
    agent, _ = make_agent([["Hello", " brave", " world"]])
    assert await events_of(agent) == [
        {"type": "token", "text": "Hello"},
        {"type": "token", "text": " brave"},
        {"type": "token", "text": " world"},
        {"type": "done"},
    ]


async def test_tool_call_emits_one_tool_event_before_any_token(make_agent):
    agent, _ = make_agent([ToolTurn("system_control", {"command": "echo hi"}), ["done", " it"]])
    events = await events_of(agent)
    assert events[0] == {"type": "tool", "name": "system_control"}
    assert types(events).count("tool") == 1
    assert types(events).index("tool") < types(events).index("token")
    assert events[-1] == {"type": "done"}


async def test_two_tool_calls_in_one_turn_sequence_emit_two_tool_events(make_agent):
    agent, _ = make_agent([
        ToolTurn("system_control", {"command": "echo a"}),
        ToolTurn("system_control", {"command": "echo b"}),
        ["ok"],
    ])
    assert types(await events_of(agent)) == ["tool", "tool", "token", "done"]


async def test_failure_after_first_token_ends_with_error_and_no_done(make_agent):
    agent, _ = make_agent([["Half a", RuntimeError("connection reset")]])
    events = await events_of(agent)
    assert types(events) == ["token", "error"]
    assert "backend" in events[-1]["message"]


async def test_groq_api_error_gets_the_groq_message(make_agent):
    boom = groq.APIError("rate limited", request=httpx.Request("POST", "http://x"), body=None)
    agent, _ = make_agent([[boom]])
    events = await events_of(agent)
    assert types(events) == ["error"]
    assert "Groq" in events[0]["message"]


async def test_failure_before_any_token_is_a_lone_error_event(make_agent):
    agent, _ = make_agent([[RuntimeError("down")]])
    assert types(await events_of(agent)) == ["error"]


@pytest.mark.parametrize("script", [
    [["a", "b"]],
    [ToolTurn("system_control", {"command": "echo x"}), ["r"]],
    [["a", RuntimeError("x")]],
    [[""]],
])
async def test_exactly_one_terminal_event_and_it_is_last(make_agent, script):
    agent, _ = make_agent(script)
    events = await events_of(agent)
    assert types(events).count("done") + types(events).count("error") == 1
    assert events[-1]["type"] in TERMINAL


async def test_empty_reply_is_just_done(make_agent):
    agent, _ = make_agent([[""]])
    assert await events_of(agent) == [{"type": "done"}]


async def test_user_input_never_leaks_out_as_a_token(make_agent):
    agent, _ = make_agent([["fine"]])
    events = await events_of(agent, message="this exact sentence must never stream back")
    joined = "".join(e.get("text", "") for e in events)
    assert "must never stream back" not in joined


async def test_second_call_on_same_thread_sees_earlier_messages(make_agent):
    agent, model = make_agent([["first reply"], ["second reply"]])
    await events_of(agent, message="remember: crimson", thread_id="same")
    await events_of(agent, message="what color?", thread_id="same")
    seen_on_second_call = " ".join(str(m.content) for m in model.calls[1])
    assert "crimson" in seen_on_second_call
    assert "first reply" in seen_on_second_call


async def test_different_threads_do_not_share_messages(make_agent):
    agent, model = make_agent([["one"], ["two"]])
    await events_of(agent, message="secret: crimson", thread_id="A")
    await events_of(agent, message="hello", thread_id="B")
    assert "crimson" not in " ".join(str(m.content) for m in model.calls[1])


async def test_many_tokens_arrive_complete_and_in_order(make_agent):
    pieces = [f"t{i} " for i in range(500)]
    agent, _ = make_agent([pieces])
    events = await events_of(agent)
    assert [e["text"] for e in events if e["type"] == "token"] == pieces


# ------------------------------------------------------------------ API level

@pytest.fixture
def client(make_agent):
    server.kokki.graph = None
    yield TestClient(server.app)
    server.kokki.graph = None


def read_events(client, script_message="hi", thread_id=None):
    body = {"message": script_message}
    if thread_id:
        body["thread_id"] = thread_id
    with client.stream("POST", "/chat/stream", json=body) as response:
        assert response.status_code == 200
        content_type = response.headers["content-type"]
        lines = [line for line in response.iter_lines() if line]
    return content_type, lines


def test_stream_route_is_ndjson_and_every_line_matches_the_schema(client, make_agent):
    make_agent([["Hi", " there"]])
    content_type, lines = read_events(client)
    assert content_type.startswith("application/x-ndjson")
    parsed = [event_adapter.validate_json(line) for line in lines]
    assert parsed[-1].type == "done"
    assert "".join(e.text for e in parsed if e.type == "token") == "Hi there"


def test_reply_containing_newlines_still_travels_as_one_line_per_event(client, make_agent):
    make_agent([["line one\n", "- bullet\n\nline two"]])
    _, lines = read_events(client)
    parsed = [event_adapter.validate_json(line) for line in lines]
    assert [e.type for e in parsed] == ["token", "token", "done"]
    assert "".join(e.text for e in parsed if e.type == "token") == "line one\n- bullet\n\nline two"


def test_emoji_and_non_ascii_survive_the_round_trip(client, make_agent):
    make_agent([["Well \U0001F389 ", "café  ‑ok"]])
    _, lines = read_events(client)
    text = "".join(event_adapter.validate_json(l).text for l in lines if '"token"' in l)
    assert text == "Well \U0001F389 café  ‑ok"


def test_mid_stream_failure_is_http_200_but_ends_with_an_error_event(client, make_agent):
    make_agent([["Half", RuntimeError("boom")]])
    _, lines = read_events(client)
    parsed = [event_adapter.validate_json(line) for line in lines]
    assert [e.type for e in parsed] == ["token", "error"]


def test_tool_event_reaches_the_client_before_the_reply(client, make_agent):
    make_agent([ToolTurn("system_control", {"command": "echo hi"}), ["ok"]])
    _, lines = read_events(client)
    assert [event_adapter.validate_json(l).type for l in lines] == ["tool", "token", "done"]


def test_omitted_thread_id_uses_the_default_thread(client, make_agent):
    _, model = make_agent([["a"], ["b"]])
    read_events(client, script_message="my word is kiwi")
    read_events(client, script_message="what was my word?")
    assert "kiwi" in " ".join(str(m.content) for m in model.calls[1])


def test_blank_message_body_is_rejected_by_validation(client, make_agent):
    make_agent([["never used"]])
    response = client.post("/chat/stream", json={})
    assert response.status_code == 422
