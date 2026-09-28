"""
Real behavior tests for cross-turn memory (real Groq calls, costs tokens).
KokkiAgent.chat() is async now, so these are async test functions -
pytest-asyncio (asyncio_mode = "auto" in pyproject.toml) runs them.

Verifies three things concretely:
1. Same thread_id remembers info across separate chat() calls
2. Different thread_ids are properly isolated from each other
3. A brand NEW KokkiAgent instance DOES resume a previous thread's memory,
   because the checkpointer (SqliteSaver) persists to disk, not RAM - so it
   survives across separate Python objects (simulating a server restart).
"""
from kokki.agent import KokkiAgent


async def test_same_thread_remembers_across_calls():
    kokki = KokkiAgent()
    kokki.thread_id = "memory-test-same-thread"

    await kokki.chat("My favorite color is teal, remember that.")
    response = await kokki.chat("What is my favorite color?")

    assert "teal" in response.lower()


async def test_different_threads_are_isolated():
    kokki_a = KokkiAgent()
    kokki_a.thread_id = "memory-test-thread-a"
    kokki_b = KokkiAgent()
    kokki_b.thread_id = "memory-test-thread-b"

    await kokki_a.chat("My favorite color is crimson, remember that.")
    response_b = await kokki_b.chat("What is my favorite color?")

    assert "crimson" not in response_b.lower()


async def test_new_agent_instance_resumes_previous_thread_via_sqlite():
    """
    Since the swap from MemorySaver (RAM) to SqliteSaver (disk), a brand new
    KokkiAgent instance - simulating a server restart - now DOES resume a
    previous thread's memory, because the checkpointer reads the same
    kokki_memory.sqlite file regardless of which Python object created it.
    """
    same_thread_id = "memory-test-resume-attempt"

    kokki_first = KokkiAgent()
    kokki_first.thread_id = same_thread_id
    await kokki_first.chat("My favorite color is magenta, remember that.")

    # Brand new KokkiAgent = brand new Python object, SAME sqlite file on disk
    kokki_second = KokkiAgent()
    kokki_second.thread_id = same_thread_id
    response = await kokki_second.chat("What is my favorite color?")

    assert "magenta" in response.lower()
