"""
Measures (not pass/fail) what the event layer costs over the old raw-token
loop, using the scripted fake model so the numbers are pure code overhead:
no network, no LLM latency. Run from the repo root:

    PYTHONPATH=. python evals/bench_stream.py
"""
import asyncio
import json
import statistics
import time

from langchain_core.messages import AIMessageChunk
from langgraph.checkpoint.memory import MemorySaver

from kokki import agent as agent_module
from kokki.agent import KokkiAgent
from tests.fakes import ScriptedChatModel

RUNS = 7


async def build(n_chunks, delay):
    async def fake_checkpointer():
        return MemorySaver()

    pieces = [f"t{i} " for i in range(n_chunks)]
    # One model turn per run; a fresh thread id per run keeps memory from growing.
    model = ScriptedChatModel(script=[pieces] * RUNS * 2, chunk_delay=delay)
    agent_module.get_checkpointer = fake_checkpointer
    agent_module.get_llm = lambda: model
    agent = KokkiAgent()
    await agent._ensure_graph()
    return agent


async def old_raw_loop(agent, thread):
    """The pre-refactor astream_chat body, inlined: yields bare text only."""
    state = {"messages": [], "user_input": "hi"}
    async for chunk, _ in agent.graph.astream(
        state, config={"configurable": {"thread_id": thread}}, stream_mode="messages"
    ):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield chunk.content


async def new_events(agent, thread):
    async for event in agent.astream_chat("hi", thread_id=thread):
        yield json.dumps(event) + "\n"  # include the NDJSON framing the route adds


async def timed(gen):
    start = time.perf_counter()
    first = None
    count = 0
    async for _ in gen:
        count += 1
        if first is None:
            first = time.perf_counter() - start
    return time.perf_counter() - start, first, count


async def scenario(label, n_chunks, delay):
    agent = await build(n_chunks, delay)
    rows = {}
    for name, fn in (("old raw loop", old_raw_loop), ("new astream_chat + NDJSON", new_events)):
        totals, firsts = [], []
        for i in range(RUNS):
            total, first, count = await timed(fn(agent, f"{name}-{i}"))
            totals.append(total)
            firsts.append(first)
        rows[name] = (statistics.median(totals), statistics.median(firsts), count)
    print(f"\n{label}  ({n_chunks} chunks, {delay * 1000:.0f} ms/chunk, median of {RUNS})")
    print(f"  {'variant':28} {'total':>10} {'per chunk':>11} {'first out':>11} {'items':>7}")
    for name, (total, first, count) in rows.items():
        print(f"  {name:28} {total * 1000:8.1f}ms {total / n_chunks * 1e6:9.1f}us {first * 1000:9.2f}ms {count:7d}")
    old = rows["old raw loop"][0]
    new = rows["new astream_chat + NDJSON"][0]
    print(f"  event-layer overhead: {(new - old) * 1000:+.1f} ms total ({(new / old - 1) * 100:+.1f}%)")


async def main():
    await scenario("pure overhead", 2000, 0.0)
    await scenario("paced like a real model", 200, 0.005)


asyncio.run(main())
