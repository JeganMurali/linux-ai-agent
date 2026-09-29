"""
Unit tests for api/sessions.py: turning the saved conversation snapshots into
"a list of sessions" and "the messages of one session". Runs on an in-memory
saver with a scripted fake model, so it is free and offline.
"""
import importlib
from datetime import datetime

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from kokki import agent as agent_module
from kokki.agent import KokkiAgent
from tests.fakes import ScriptedChatModel, ToolTurn


def S():
    """api.sessions, imported when a test runs so each test fails on its own."""
    return importlib.import_module("api.sessions")


@pytest.fixture
def build(monkeypatch):
    """build(script) -> (agent, saver, talk); talk(message, thread) runs one turn."""
    def make(script):
        saver = MemorySaver()

        async def checkpointer():
            return saver

        monkeypatch.setattr(agent_module, "get_checkpointer", checkpointer)
        monkeypatch.setattr(agent_module, "get_llm", lambda model=ScriptedChatModel(script=script): model)
        agent = KokkiAgent()

        async def talk(message, thread):
            return [event async for event in agent.astream_chat(message, thread_id=thread)]

        return agent, saver, talk
    return make


REPLIES = [["reply"]] * 12


# ------------------------------------------------------------ what is visible

def test_visible_keeps_what_you_said_and_what_kokki_said_and_hides_tool_traffic():
    messages = [
        HumanMessage(content="open files"),
        AIMessage(content="", tool_calls=[{"name": "system_control", "args": {"command": "xdg-open ."}, "id": "1"}]),
        ToolMessage(content="Done!", tool_call_id="1"),
        AIMessage(content="Opened."),
    ]
    assert list(S()._visible(messages)) == [("you", "open files"), ("kokki", "Opened.")]


def test_visible_of_an_empty_conversation_is_empty():
    assert list(S()._visible([])) == []


# ---------------------------------------------------------------- the titles

def test_title_collapses_newlines_and_runs_of_spaces():
    assert S()._title("open   the\n\nfiles \t app") == "open the files app"


def test_title_at_exactly_the_limit_is_left_alone():
    text = "x" * S().TITLE_MAX
    assert S()._title(text) == text


def test_title_over_the_limit_is_cut_and_ends_with_an_ellipsis_at_the_limit_length():
    title = S()._title("y" * (S().TITLE_MAX + 25))
    assert len(title) == S().TITLE_MAX
    assert title.endswith("…")


def test_title_of_only_whitespace_is_empty():
    assert S()._title(" \n\t ") == ""


# -------------------------------------------------------------- list_sessions

async def test_no_conversations_gives_an_empty_list(build):
    _, saver, _ = build(REPLIES)
    assert await S().list_sessions(saver) == []


async def test_a_session_has_id_title_count_and_a_parseable_utc_timestamp(build):
    _, saver, talk = build(REPLIES)
    await talk("open the files app", "bar-1")
    [row] = await S().list_sessions(saver)
    assert row["thread_id"] == "bar-1"
    assert row["title"] == "open the files app"
    assert row["message_count"] == 2
    assert datetime.fromisoformat(row["updated_at"]).utcoffset().total_seconds() == 0


async def test_sessions_come_newest_first_by_last_activity_not_by_creation(build):
    _, saver, talk = build(REPLIES)
    await talk("first", "bar-a")
    await talk("second", "bar-b")
    await talk("first again", "bar-a")          # bar-a is now the most recently active
    assert [r["thread_id"] for r in await S().list_sessions(saver)] == ["bar-a", "bar-b"]


async def test_only_the_newest_snapshot_counts_so_the_count_grows_with_the_chat(build):
    _, saver, talk = build(REPLIES)
    await talk("one", "bar-1")
    first = (await S().list_sessions(saver))[0]
    await talk("two", "bar-1")
    second = (await S().list_sessions(saver))[0]
    assert (first["message_count"], second["message_count"]) == (2, 4)
    assert second["updated_at"] > first["updated_at"]
    assert second["title"] == "one", "the title stays the FIRST thing said"


async def test_tool_traffic_is_not_counted(build):
    _, saver, talk = build([ToolTurn("system_control", {"command": "echo hi"}), ["Done, roasted."]])
    await talk("run echo", "bar-1")
    [row] = await S().list_sessions(saver)
    assert row["message_count"] == 2, "Human + final AI only; the tool call and result are hidden"


async def test_prefix_matches_the_base_and_its_dash_children_only(build):
    _, saver, talk = build(REPLIES)
    for thread in ("bar", "bar-123", "barbecue", "evtest", "memory-test-x"):
        await talk("hi", thread)
    ids = {r["thread_id"] for r in await S().list_sessions(saver, prefix="bar")}
    assert ids == {"bar", "bar-123"}


async def test_no_prefix_returns_every_thread(build):
    _, saver, talk = build(REPLIES)
    for thread in ("bar-1", "evtest"):
        await talk("hi", thread)
    assert len(await S().list_sessions(saver)) == 2


async def test_limit_keeps_the_newest_ones(build):
    _, saver, talk = build(REPLIES)
    for thread in ("bar-1", "bar-2", "bar-3"):
        await talk("hi", thread)
    assert [r["thread_id"] for r in await S().list_sessions(saver, limit=2)] == ["bar-3", "bar-2"]


async def test_a_message_of_only_spaces_gets_a_placeholder_title(build):
    _, saver, talk = build(REPLIES)
    await talk("     ", "bar-1")
    assert (await S().list_sessions(saver))[0]["title"] == "(no text)"


async def test_a_long_first_message_is_shortened_in_the_title(build):
    _, saver, talk = build(REPLIES)
    await talk("please " * 40, "bar-1")
    assert len((await S().list_sessions(saver))[0]["title"]) == S().TITLE_MAX


# --------------------------------------------------------------- get_messages

async def test_messages_come_back_in_order_as_you_and_kokki(build):
    _, saver, talk = build([["Hello there"], ["Second reply"]])
    await talk("hi", "bar-1")
    await talk("and again", "bar-1")
    assert await S().get_messages(saver, "bar-1") == [
        {"role": "you", "text": "hi"}, {"role": "kokki", "text": "Hello there"},
        {"role": "you", "text": "and again"}, {"role": "kokki", "text": "Second reply"},
    ]


async def test_messages_hide_tool_calls_and_tool_results(build):
    _, saver, talk = build([ToolTurn("system_control", {"command": "echo hi"}), ["All done."]])
    await talk("do it", "bar-1")
    roles = [m["role"] for m in await S().get_messages(saver, "bar-1")]
    assert roles == ["you", "kokki"]


async def test_an_unknown_thread_is_none_not_an_empty_list(build):
    _, saver, _ = build(REPLIES)
    assert await S().get_messages(saver, "no-such-thread") is None


async def test_threads_do_not_leak_into_each_other(build):
    _, saver, talk = build([["a reply"], ["b reply"]])
    await talk("secret in A", "bar-a")
    await talk("hello from B", "bar-b")
    texts = " ".join(m["text"] for m in await S().get_messages(saver, "bar-b"))
    assert "secret in A" not in texts
