import uuid
from fastapi import FastAPI
from kokki.agent import KokkiAgent
from api.schemas import ChatRequest, ChatResponse, ThreadResponse

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
def chat(request: ChatRequest):
    thread_id = request.thread_id or DEFAULT_THREAD_ID
    reply = kokki.chat(request.message, thread_id=thread_id)
    return ChatResponse(reply=reply, thread_id=thread_id)
