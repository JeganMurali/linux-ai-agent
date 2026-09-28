import time
from groq import APIError
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk
from typing import TypedDict, Annotated
from kokki.tools import system_control
from kokki.config import (
    LLM_BACKEND,
    GROQ_API_KEY,
    GROQ_MODEL,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    KOKKI_PERSONALITY,
    KOKKI_PROFANITY,
    ENABLED_TOOLS,
)
from kokki.prompts import build_system_prompt
from kokki.memory import get_checkpointer
from kokki.observability import get_logger

# All tools Kokki knows about, keyed by name - setup.py's ENABLED_TOOLS
# picks a subset of this to actually bind to the LLM.
ALL_TOOLS = {"system_control": system_control}
TOOLS = [ALL_TOOLS[name] for name in ENABLED_TOOLS if name in ALL_TOOLS]

logger = get_logger()


def get_llm():
    if LLM_BACKEND == "ollama":
        return ChatOllama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)
    return ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_input: str


def input_node(state):
    logger.info(f"user: {state['user_input']!r}")
    return {"messages": [HumanMessage(content=state["user_input"])]}


async def llm_node(state):
    llm = get_llm()
    llm_with_tools = llm.bind_tools(TOOLS)

    system_prompt = build_system_prompt(KOKKI_PERSONALITY, KOKKI_PROFANITY)
    messages = [SystemMessage(content=system_prompt)] + state["messages"]

    start = time.time()
    response = await llm_with_tools.ainvoke(messages)
    duration_ms = (time.time() - start) * 1000

    thinking = response.additional_kwargs.get("reasoning_content")
    logger.info(
        f"llm fetch took {duration_ms:.0f}ms | "
        f"ai: {response.content!r} | "
        f"tool_calls: {response.tool_calls} | "
        f"thinking: {thinking!r}"
    )

    return {"messages": [response]}


async def create_agent():
    graph = StateGraph(AgentState)
    graph.add_node("input", input_node)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "input")
    graph.add_edge("input", "llm")
    graph.add_conditional_edges("llm", tools_condition)
    graph.add_edge("tools", "llm")

    checkpointer = await get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


class KokkiAgent:
    def __init__(self):
        self.graph = None  # built lazily - see _ensure_graph
        self.thread_id = "main"

    async def _ensure_graph(self):
        # aiosqlite.connect() (inside get_checkpointer) is itself async,
        # and __init__ can never be async - so the graph gets built on the
        # first real chat() call instead of at construction time.
        if self.graph is None:
            self.graph = await create_agent()

    async def chat(self, user_input: str, thread_id: str = None):
        await self._ensure_graph()
        thread_id = thread_id or self.thread_id
        state = {"messages": [], "user_input": user_input}
        try:
            result = await self.graph.ainvoke(
                state,
                config={"configurable": {"thread_id": thread_id}}
            )
        except APIError as e:
            logger.info(f"groq api error: {e!r}")
            return "Fuck, Groq choked on that one - try rephrasing it."
        except Exception as e:
            # Catches Ollama-side failures too (e.g. connection refused if
            # `ollama serve` isn't running) - any backend, same boundary.
            logger.info(f"llm backend error: {e!r}")
            return f"Fuck, couldn't reach the {LLM_BACKEND} backend - is it actually running?"

        logger.info(f"memory saved: thread_id={thread_id!r}")
        return result["messages"][-1].content

    async def astream_chat(self, user_input: str, thread_id: str = None):
        """
        Yields Kokki's reply piece by piece, as Groq/Ollama generates it -
        instead of chat()'s wait-for-the-whole-thing-then-return.

        stream_mode="messages" gives a (chunk, metadata) pair for every
        token from EVERY LLM call inside the graph - including the internal
        "should I call a tool?" reasoning call, which usually has empty or
        irrelevant content. We only yield real, non-empty text chunks, so
        the caller only ever sees the actual conversational reply.
        """
        await self._ensure_graph()
        thread_id = thread_id or self.thread_id
        state = {"messages": [], "user_input": user_input}

        async for chunk, metadata in self.graph.astream(
            state,
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="messages",
        ):
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                yield chunk.content

        logger.info(f"memory saved: thread_id={thread_id!r}")
