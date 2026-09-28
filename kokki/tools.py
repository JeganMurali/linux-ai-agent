import subprocess
import psutil
import platform
from typing import Dict
from langchain_core.tools import tool
from kokki.observability import get_logger

logger = get_logger()

# Last-resort hard floor for commands where even a confirmed "yes" is too
# risky to trust blindly - unrecoverable, whole-disk/filesystem destruction.
# Reboot/shutdown are NOT here: those are reversible (just a restart) and are
# correctly gated by the CONFIRMATION flow in prompts.py instead, which is
# proven to work now that memory/thread_id lets Kokki see a real "yes."
IRREVERSIBLE_PATTERNS = [
    "rm -rf /", "mkfs", "dd if=",
]

# Caps tool output before it re-enters the LLM's context. A single unbounded
# command (e.g. an unfiltered process list) can otherwise blow past Groq's
# entire per-minute token budget in ONE request - proven by the eval script
# crashing on "monitor the running processes".
MAX_OUTPUT_CHARS = 2000


def _truncate(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(text)} chars total]"


@tool
def system_control(command: str) -> str:
    """
    Runs a shell command on the user's Linux system and returns the output.
    Use this when the user asks to open an app, check system stats, list files, or run any terminal command.
    """
    if any(pattern in command for pattern in IRREVERSIBLE_PATTERNS):
        logger.info(f"tool BLOCKED: system_control(command={command!r})")
        return (
            f"BLOCKED: '{command}' matches a hard safety rule and will not run through this tool, "
            f"no exceptions. If this is genuinely needed, tell the user to run it themselves."
        )

    logger.info(f"tool used: system_control(command={command!r})")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
        )

        if result.returncode == 0:
            return _truncate(result.stdout) or "Done!"
        else:
            return _truncate(f"Error: {result.stderr}")

    except subprocess.TimeoutExpired:
        return "Command timed out (>20 seconds)"
    except Exception as e:
        return f"Error: {str(e)}"
