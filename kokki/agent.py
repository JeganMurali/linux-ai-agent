import time
from groq import APIError
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from typing import TypedDict, Annotated
from kokki.tools import system_control
from kokki.config import GROQ_API_KEY, GROQ_MODEL
from kokki.prompts import KOKKI_SYSTEM_PROMPT
from kokki.memory import get_checkpointer
from kokki.observability import get_logger

TOOLS = [system_control]
logger = get_logger()


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_input: str


def input_node(state):
    logger.info(f"user: {state['user_input']!r}")
    return {"messages": [HumanMessage(content=state["user_input"])]}


async def llm_node(state):
    llm = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL)
    llm_with_tools = llm.bind_tools(TOOLS)

    messages = [SystemMessage(content=KOKKI_SYSTEM_PROMPT)] + state["messages"]

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

        logger.info(f"memory saved: thread_id={thread_id!r}")
        return result["messages"][-1].content
