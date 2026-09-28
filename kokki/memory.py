import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def get_checkpointer():
    conn = await aiosqlite.connect("kokki_memory.sqlite")
    return AsyncSqliteSaver(conn)
