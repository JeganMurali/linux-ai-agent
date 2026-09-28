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


def llm_node(state):
    llm = ChatGroq(api_key=GROQ_API_KEY, model=GROQ_MODEL)
    llm_with_tools = llm.bind_tools(TOOLS)

    messages = [SystemMessage(content=KOKKI_SYSTEM_PROMPT)] + state["messages"]

    start = time.time()
    response = llm_with_tools.invoke(messages)
    duration_ms = (time.time() - start) * 1000

    thinking = response.additional_kwargs.get("reasoning_content")
    logger.info(
        f"llm fetch took {duration_ms:.0f}ms | "
        f"ai: {response.content!r} | "
        f"tool_calls: {response.tool_calls} | "
        f"thinking: {thinking!r}"
    )

    return {"messages": [response]}


def create_agent():
    graph = StateGraph(AgentState)
    graph.add_node("input", input_node)
    graph.add_node("llm", llm_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "input")
    graph.add_edge("input", "llm")
    graph.add_conditional_edges("llm", tools_condition)
    graph.add_edge("tools", "llm")

    return graph.compile(checkpointer=get_checkpointer())


class KokkiAgent:
    def __init__(self):
        self.graph = create_agent()
        self.thread_id = "main"

    def chat(self, user_input: str, thread_id: str = None):
        thread_id = thread_id or self.thread_id
        state = {"messages": [], "user_input": user_input}
        try:
            result = self.graph.invoke(
                state,
                config={"configurable": {"thread_id": thread_id}}
            )
        except APIError as e:
            logger.info(f"groq api error: {e!r}")
            return "Fuck, Groq choked on that one - try rephrasing it."

        logger.info(f"memory saved: thread_id={thread_id!r}")
        return result["messages"][-1].content
