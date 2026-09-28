from langgraph.checkpoint.memory import MemorySaver

def get_checkpointer():
    return MemorySaver()
