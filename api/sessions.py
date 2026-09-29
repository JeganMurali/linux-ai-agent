from langchain_core.messages import AIMessage, HumanMessage

TITLE_MAX = 60


def _visible(messages):
    """What a person would recognise: what you said and what Kokki said back."""
    for m in messages:
        if isinstance(m, HumanMessage):
            yield "you", str(m.content)
        elif isinstance(m, AIMessage) and m.content:      # skips turns that only asked for a tool
            yield "kokki", str(m.content)


def _title(text):
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= TITLE_MAX else one_line[:TITLE_MAX - 1] + "…"


async def _latest_per_thread(saver):
    latest = {}
    async for snapshot in saver.alist(None):
        thread_id = snapshot.config["configurable"]["thread_id"]
        latest.setdefault(thread_id, snapshot)            # first one seen is that thread's newest
    return latest


async def list_sessions(saver, prefix="", limit=30):
    rows = []
    for thread_id, snapshot in (await _latest_per_thread(saver)).items():
        if prefix and not (thread_id == prefix or thread_id.startswith(prefix + "-")):
            continue
        visible = list(_visible(snapshot.checkpoint["channel_values"].get("messages", [])))
        if not visible:
            continue
        first_you = next((text for role, text in visible if role == "you"), "")
        rows.append({"thread_id": thread_id, "title": _title(first_you) or "(no text)",
                     "updated_at": snapshot.checkpoint["ts"], "message_count": len(visible)})
    rows.sort(key=lambda row: row["updated_at"], reverse=True)
    return rows[:limit]


async def get_messages(saver, thread_id):
    snapshot = await saver.aget_tuple({"configurable": {"thread_id": thread_id}})
    if snapshot is None:
        return None
    return [{"role": role, "text": text}
            for role, text in _visible(snapshot.checkpoint["channel_values"].get("messages", []))]