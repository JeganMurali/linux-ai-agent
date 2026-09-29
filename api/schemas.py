from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field

class SessionSummary(BaseModel):
    thread_id: str
    title: str           # the first thing you said, shortened
    updated_at: str      # UTC timestamp of the last saved step
    message_count: int   # what you said + what Kokki said back


class SessionMessage(BaseModel):
    role: Literal["you", "kokki"]
    text: str


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # omit to use the default shared conversation


class ChatResponse(BaseModel):
    reply: str
    thread_id: str  # which conversation this reply belongs to


class ThreadResponse(BaseModel):
    thread_id: str


# One line of the /chat/events stream. A stream is any number of tool/token
# events followed by exactly one terminal event: done or error.
class ToolEvent(BaseModel):
    type: Literal["tool"]
    name: str


class TokenEvent(BaseModel):
    type: Literal["token"]
    text: str


class DoneEvent(BaseModel):
    type: Literal["done"]


class ErrorEvent(BaseModel):
    type: Literal["error"]
    message: str


ChatEvent = Annotated[
    Union[ToolEvent, TokenEvent, DoneEvent, ErrorEvent],
    Field(discriminator="type"),
]
