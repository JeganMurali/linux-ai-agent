from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # omit to use the default shared conversation


class ChatResponse(BaseModel):
    reply: str
    thread_id: str  # which conversation this reply belongs to


class ThreadResponse(BaseModel):
    thread_id: str
