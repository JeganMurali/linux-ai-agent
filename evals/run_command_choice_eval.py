"""
Eval, not a test: measures how OFTEN Kokki picks a safe, non-interactive
command over an interactive one that would hang (top vs top -bn1, etc).
LLM judgment is probabilistic, so this reports a success rate over N tries
per prompt, not a pass/fail. Costs real Groq tokens - run manually, not in CI.
"""
import time
import uuid
from kokki.agent import KokkiAgent

# Programs that hang/misbehave if run non-interactively without the right flags
INTERACTIVE_PROGRAMS = ["top", "htop", "vim", "nano", "less", "man"]

PROMPTS = [
    "check my cpu usage",
    "show me what's using the most memory",
    "monitor the running processes",
]

RUNS_PER_PROMPT = 5


def get_last_tool_command(kokki):
    """Pull the actual command Kokki called, straight from graph state."""
    state = kokki.graph.get_state({"configurable": {"thread_id": kokki.thread_id}})
    for msg in state.values["messages"]:
        if getattr(msg, "tool_calls", None):
            return msg.tool_calls[0]["args"].get("command", "")
    return None


def is_safe_command(command):
    if command is None:
        return False
    # Flag as unsafe only if an interactive program appears WITHOUT
    # a batch/non-interactive flag right after it (a rough but useful check)
    for prog in INTERACTIVE_PROGRAMS:
        if prog in command and f"{prog} -bn1" not in command and f"cat " not in command:
            return False
    return True


def run_eval():
    print("🧪 Command Choice Eval\n" + "=" * 50)
    overall_safe = 0
    overall_total = 0

    for prompt in PROMPTS:
        safe_count = 0
        commands_seen = []

        for _ in range(RUNS_PER_PROMPT):
            kokki = KokkiAgent()
            kokki.thread_id = f"eval-{uuid.uuid4()}"
            kokki.chat(prompt)
            command = get_last_tool_command(kokki)
            commands_seen.append(command)
            if is_safe_command(command):
                safe_count += 1
            time.sleep(4)  # pace calls to stay under Groq's free-tier TPM budget

        overall_safe += safe_count
        overall_total += RUNS_PER_PROMPT

        print(f"\nPrompt: {prompt!r}")
        print(f"  Safe: {safe_count}/{RUNS_PER_PROMPT} ({safe_count / RUNS_PER_PROMPT * 100:.0f}%)")
        for c in commands_seen:
            print(f"    - {c!r}")

    print("\n" + "=" * 50)
    print(f"OVERALL: {overall_safe}/{overall_total} ({overall_safe / overall_total * 100:.0f}%) safe command choices")


if __name__ == "__main__":
    run_eval()
