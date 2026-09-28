"""
Real behavior tests for cross-turn memory (real Groq calls, costs tokens).

Verifies three things concretely:
1. Same thread_id remembers info across separate chat() calls
2. Different thread_ids are properly isolated from each other
3. A brand NEW KokkiAgent instance does NOT resume a previous thread's
   memory - this is a real current limitation worth knowing, not assumed:
   MemorySaver is created fresh inside each KokkiAgent's own create_agent()
   call, so it only lives as long as that one Python object does. Restarting
   the app (a new KokkiAgent()) currently means starting over, even with
   the same thread_id.
"""
from kokki.agent import KokkiAgent


def test_same_thread_remembers_across_calls():
    kokki = KokkiAgent()
    kokki.thread_id = "memory-test-same-thread"

    kokki.chat("My favorite color is teal, remember that.")
    response = kokki.chat("What is my favorite color?")

    assert "teal" in response.lower()


def test_different_threads_are_isolated():
    kokki_a = KokkiAgent()
    kokki_a.thread_id = "memory-test-thread-a"
    kokki_b = KokkiAgent()
    kokki_b.thread_id = "memory-test-thread-b"

    kokki_a.chat("My favorite color is crimson, remember that.")
    response_b = kokki_b.chat("What is my favorite color?")

    assert "crimson" not in response_b.lower()


def test_new_agent_instance_resumes_previous_thread_via_sqlite():
    """
    Since the swap from MemorySaver (RAM) to SqliteSaver (disk), a brand new
    KokkiAgent instance - simulating a server restart - now DOES resume a
    previous thread's memory, because the checkpointer reads the same
    kokki_memory.sqlite file regardless of which Python object created it.
    """
    same_thread_id = "memory-test-resume-attempt"

    kokki_first = KokkiAgent()
    kokki_first.thread_id = same_thread_id
    kokki_first.chat("My favorite color is magenta, remember that.")

    # Brand new KokkiAgent = brand new Python object, SAME sqlite file on disk
    kokki_second = KokkiAgent()
    kokki_second.thread_id = same_thread_id
    response = kokki_second.chat("What is my favorite color?")

    assert "magenta" in response.lower()
