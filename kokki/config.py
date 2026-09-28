import os
from dotenv import load_dotenv

load_dotenv()

# Which backend to use: "groq" (cloud, fast, needs an API key) or
# "ollama" (fully local, private, no key needed, slower on weak hardware)
LLM_BACKEND = os.getenv("KOKKI_LLM_BACKEND", "groq")

# Groq connection config
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("KOKKI_GROQ_MODEL", "openai/gpt-oss-120b")

# Ollama connection config
OLLAMA_BASE_URL = os.getenv("KOKKI_OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("KOKKI_OLLAMA_MODEL", "qwen3:1.7b")

# Personality config - safety/behavior rules are NEVER configurable
# (see kokki/prompts.py), only tone and profanity are user-adjustable.
KOKKI_PERSONALITY = os.getenv("KOKKI_PERSONALITY")  # None = use the default
KOKKI_PROFANITY = os.getenv("KOKKI_PROFANITY", "true").lower() == "true"

# Which tools are enabled - set by kokki_setup.py, comma-separated tool names
ENABLED_TOOLS = os.getenv("KOKKI_ENABLED_TOOLS", "system_control,get_system_info").split(",")
