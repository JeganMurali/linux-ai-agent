import json
import uuid
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from kokki.agent import KokkiAgent
from api import sessions
from api.schemas import ChatRequest, ChatResponse, SessionMessage, SessionSummary, ThreadResponse

app = FastAPI()

# Created ONCE, at server startup - reused across every request.
# A fresh KokkiAgent() per-request would silently reset memory every message
# (proven by tests/test_memory.py::test_new_agent_instance_does_not_resume_previous_thread).
# thread_id is now passed per-call (see kokki.agent.KokkiAgent.chat), so this
# ONE instance safely serves many separate, isolated conversations at once.
kokki = KokkiAgent()

DEFAULT_THREAD_ID = "main"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/threads", response_model=ThreadResponse)
def create_thread():
    """Start a brand new, isolated conversation. Use the returned thread_id
    on every /chat call you want part of that same conversation."""
    return ThreadResponse(thread_id=str(uuid.uuid4()))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    thread_id = request.thread_id or DEFAULT_THREAD_ID
    reply = await kokki.chat(request.message, thread_id=thread_id)
    return ChatResponse(reply=reply, thread_id=thread_id)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Same as /chat, but streams as Kokki generates: one JSON event per line
    (NDJSON) - tool / token / done / error, shapes in api.schemas.ChatEvent.
    json.dumps never emits a raw newline, so "one event per line" always
    holds, even for replies containing newlines.
    """
    thread_id = request.thread_id or DEFAULT_THREAD_ID

    async def generate():
        async for event in kokki.astream_chat(request.message, thread_id=thread_id):
            yield json.dumps(event) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@app.get("/threads", response_model=list[SessionSummary])
async def list_threads(prefix: str = "", limit: int = Query(30, ge=1, le=100)):
    await kokki._ensure_graph()
    return await sessions.list_sessions(kokki.graph.checkpointer, prefix, limit)


@app.get("/threads/{thread_id}/messages", response_model=list[SessionMessage])
async def thread_messages(thread_id: str):
    await kokki._ensure_graph()
    messages = await sessions.get_messages(kokki.graph.checkpointer, thread_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="no such thread")
    return messages