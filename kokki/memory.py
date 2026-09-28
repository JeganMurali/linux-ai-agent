import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

def get_checkpointer():
    conn = sqlite3.connect("kokki_memory.sqlite", check_same_thread=False)
    return SqliteSaver(conn)
