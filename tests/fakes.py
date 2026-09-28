"""
Scripted stand-in for the real chat model, so streaming behavior can be tested
deterministically with no network, API key, or token cost.

Each call the graph makes to the model consumes one "turn" from the script:
  - a list of str            -> stream those chunks as the reply text
  - ToolTurn(name, args)     -> the model asks to run a tool
  - a list ending in an Exception instance -> stream the strings, then raise it
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field


@dataclass
class ToolTurn:
    name: str
    args: dict


class ScriptedChatModel(BaseChatModel):
    script: list = Field(default_factory=list)
    chunk_delay: float = 0.0
    calls: list = Field(default_factory=list)  # messages seen on each model call
    turn: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _next_turn(self, messages):
        self.calls.append(list(messages))
        if self.turn >= len(self.script):
            raise AssertionError("model was called more times than the script has turns")
        turn = self.script[self.turn]
        self.turn += 1
        return turn

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs: Any):
        turn = self._next_turn(messages)
        if isinstance(turn, ToolTurn):
            yield ChatGenerationChunk(message=AIMessageChunk(
                content="",
                tool_call_chunks=[{
                    "name": turn.name, "args": json.dumps(turn.args),
                    "id": f"call_{self.turn}", "index": 0,
                }],
            ))
            return
        for piece in turn:
            if isinstance(piece, Exception):
                raise piece
            if self.chunk_delay:
                await asyncio.sleep(self.chunk_delay)
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any):
        turn = self._next_turn(messages)
        if isinstance(turn, ToolTurn):
            message = AIMessage(content="", tool_calls=[
                {"name": turn.name, "args": turn.args, "id": f"call_{self.turn}"}
            ])
        else:
            message = AIMessage(content="".join(p for p in turn if isinstance(p, str)))
        return ChatResult(generations=[ChatGeneration(message=message)])
