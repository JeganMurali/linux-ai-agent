# Kokki Kumar — Project Handoff

Read this first in any new session before touching the code. It captures
what's built, why key decisions were made, and exactly where the QML work
was paused — not just what to do next, but what's already been ruled out
and why, so a fresh session doesn't re-litigate settled decisions.

## What This Project Is

A personal AI agent for Omarchy Linux, being built to eventually distribute
to the wider Omarchy community — not just for solo use anymore (see
"Community pivot" below). LangGraph + Groq (or local Ollama), real
LLM-driven tool calling, sarcastic/configurable personality, runs as a
FastAPI server. Character: sharp-tongued, roasts you, always gets the job
done.

## Critical Collaboration Rule (read this before writing any code)

**Jegan corrected this explicitly and it matters: discuss and get his
actual go-ahead before implementing anything beyond what he directly asked
for — even a "quick addition" or "good idea while I'm at it."** Give your
opinion, make a recommendation, then STOP and wait. Don't treat "here's my
recommendation" as permission to build it. This applies to new tools, new
features, architecture changes — not to fixing an actual bug he reported,
or straightforward tooling/setup friction (pip installs, venv issues,
syntax fixes in files he's actively learning from).

See `~/Work/CLAUDE.md` for the full teaching/collaboration approach
(concept before code, let him write learning-relevant code himself,
review like a PR not a grader).

## Current State — What Actually Works

- **`kokki/agent.py`** — LangGraph agent, fully async (`chat()` and
  `astream_chat()` both `async def`), real tool calling via `@tool` +
  `bind_tools()` + `ToolNode`/`tools_condition` (no keyword matching)
- **Backend-configurable**: `LLM_BACKEND` env var picks Groq (`ChatGroq`)
  or Ollama (`ChatOllama`) — see `kokki/config.py`, `get_llm()` in
  `kokki/agent.py`
- **Personality-configurable**: `kokki/prompts.py` splits
  `KOKKI_SAFETY_PROMPT` (fixed, never configurable — the confirmation
  flow and sudo gate) from `build_system_prompt(personality, profanity)`
  (user-adjustable tone)
- **`kokki_setup.py`** — interactive onboarding wizard, writes `.env`.
  Named `kokki_setup.py` NOT `setup.py` deliberately — that filename
  collides with legacy setuptools and broke `pip install -e .`
- **Memory**: `AsyncSqliteSaver` (disk-backed, survives restarts) via
  `kokki/memory.py`. `KokkiAgent.__init__` can't be async (Python
  limitation), so the graph builds lazily on first real `chat()` call
  (`_ensure_graph()`) — this exact pattern matters if you ever refactor
  `KokkiAgent`, don't "simplify" it back into `__init__`
- **Streaming**: `KokkiAgent.astream_chat()` yields real token-by-token
  chunks via `graph.astream(..., stream_mode="messages")`, filtered to
  `AIMessageChunk` only (a real bug: the `HumanMessage` itself leaked
  through as a fake chunk before this filter existed)
- **`api/server.py`** — FastAPI: `GET /health`, `POST /threads` (creates
  isolated conversation IDs), `POST /chat`, `POST /chat/stream`
  (`StreamingResponse`). One shared `KokkiAgent` instance at module level,
  `thread_id` passed per-call — NOT a fresh agent per request (would
  silently reset memory every message)
- **Only one tool**: `system_control(command: str)` — runs arbitrary shell
  commands. A second tool (`get_system_info`) was built and then removed
  per Jegan's explicit feedback (built without discussing first). If a
  second tool comes up again: discuss what it should actually be first,
  don't default back to that one.
- **Safety, found via live incidents, not designed upfront**:
  - Hardcoded blocklist (`rm -rf /`, `mkfs`, `dd if=`) — last-resort floor
    for stuff too risky to trust even a confirmed "yes"
  - `stdin=subprocess.DEVNULL` — prevents hangs on commands needing
    interactive input (sudo password prompts)
  - Confirmation flow in the prompt — genuinely disruptive actions
    (reboot, killing the WM, sudo/root anything) must ask first, proven
    working via real tests, not just designed
  - Output truncation (`MAX_OUTPUT_CHARS`) — a single unbounded command
    result can blow Groq's entire per-minute token budget in one request
    (this actually happened, crashed the eval script, before the fix)
- **Tests**: `tests/test_smoke.py`, `test_tools.py`, `test_memory.py`,
  `test_agent_integration.py`, `test_api.py` — 21+ passing. CI on GitHub
  Actions runs the free/deterministic ones on every push (`test_tools.py`,
  `test_smoke.py`) — NOT the integration/API ones (real Groq calls, needs
  a secret, costs tokens)
- **`evals/run_command_choice_eval.py`** — measures (not pass/fail) how
  often Kokki picks safe one-shot commands over interactive ones
- Repo: `github.com/JeganMurali/linux-ai-agent`, CI green as of last push

## Community Pivot (mid-session decision, confirmed with Jegan)

This stopped being solo-use-only. Two explicit decisions made together:
1. Support **both** Groq and Ollama, user picks (not Groq-only)
2. Personality/profanity **configurable**, not hardcoded to one character
   — but safety rules (confirmation flow, sudo gate) stay fixed regardless

## Where QML Work Was Paused — Read Carefully Before Continuing

**Decision made**: Option A — build using Omarchy's real internal
component library (`qs.Commons`/`qs.Ui`) for proper native theme
integration, NOT a bare standalone Quickshell `PanelWindow` (that was
Option B, explicitly not chosen).

**What's verified so far** (real files read, not guessed):
- Plugin structure: `~/.config/omarchy/plugins/<id>/` +
  `manifest.json` (`"kinds": ["bar-widget"]`, `entryPoints.barWidget`)
  — confirmed via `/usr/share/omarchy/shell/plugins/agents/manifest.json`
- IPC/communication pattern: **QML never makes HTTP calls directly.**
  Every plugin shells out via `Process` + a stdout reader. Two readers,
  two different jobs:
  - `StdioCollector` + `waitForEnd: true` + `onStreamFinished` — waits
    for the whole process, gives you complete output once (for our
    plain `/chat`, via `curl`)
  - `SplitParser` + `onRead: function(line) {...}` — fires
    **incrementally** as lines arrive (for `/chat/stream`, via
    `curl -N`) — confirmed real usage in
    `/usr/share/omarchy/shell/plugins/panels/disk-speedtest/Panel.qml`
    (151 lines, shortest real example, read in full)
- Core component library located at `/usr/share/omarchy/shell/Commons/`
  and `/usr/share/omarchy/shell/Ui/` (this is what `import qs.Commons`
  and `import qs.Ui` actually resolve to)
- Read and understood so far: `Ui/Panel.qml` (base type — `moduleName`,
  `ipcTarget`, `open()`/`close()`/`toggle()`, wraps `PanelController`),
  `Ui/PanelController.qml` (trivial — just an `open: bool` + show/hide/
  toggle), `Ui/TextField.qml` (themed `QtQuick.Controls.TextField`
  subclass, standard `text`/`placeholderText`/`accepted` API still
  works), `Ui/BarIconButton.qml` (extends `WidgetButton`, needs `text`
  as glyph or `iconComponent`)

**NOT yet read — needed before writing a real `Panel.qml`**:
- `Ui/WidgetButton.qml` — what `BarIconButton` actually extends
- `Ui/PopupCard.qml` — likely the actual popup-window-rendering piece
  (disk-speedtest delegates its visual popup to `SpeedTestOverlay`,
  a similar-shaped component we haven't read — `PopupCard` is probably
  the more generic version of that same idea)
- `Ui/BarWidget.qml` — how a plugin's bar icon actually gets registered
  into the bar itself (as opposed to the popup content)
- Worth finding a real plugin that has genuine **text input + scrollback
  display** (closer to a chat shape) rather than a gauge/dial display like
  disk-speedtest — `wifiqr/Panel.qml` (369 lines) or `power/Panel.qml`
  (536 lines) are reasonable next candidates to check, untested guesses,
  verify before trusting

**The actual build plan once research is done**:
1. `manifest.json` for `kokki` — bar-widget, `entryPoints.barWidget: Panel.qml`
2. `Panel.qml` extending base `Panel` — bar icon (`BarIconButton`) +
   popup content (probably built on `PopupCard`, once verified) with a
   `TextField` for input and a scrollback display area
3. Wire `/chat` first via `Process` + `StdioCollector` + `curl` — prove
   the whole loop once, non-streaming
4. Then swap to `/chat/stream` via `Process` + `SplitParser` +
   `curl -N` — visible token-by-token text, same mechanism
   `disk-speedtest` already proved works for its own streaming numbers

## Key File Locations Reference

```
~/Work/kokki-kumar/          - this project
~/Work/CLAUDE.md              - durable teaching/collaboration guidance
/usr/share/omarchy/shell/plugins/  - read-only, reference/example plugins
/usr/share/omarchy/shell/Commons/  - qs.Commons source (Color, Style, Border, Util)
/usr/share/omarchy/shell/Ui/       - qs.Ui source (Panel, TextField, buttons, etc.)
~/.config/omarchy/plugins/    - where Kokki's own plugin will actually live
```

## Running Things

```bash
cd ~/Work/kokki-kumar
source venv/bin/activate

# CLI chat
python main.py

# FastAPI server
uvicorn api.server:app --port 8000

# Tests (free ones)
pytest tests/test_smoke.py tests/test_tools.py -v

# Tests (real Groq calls, costs tokens)
pytest tests/test_memory.py tests/test_agent_integration.py tests/test_api.py -v

# Eval (measures, not pass/fail, real Groq calls)
python evals/run_command_choice_eval.py
```

Known gotcha: `rm -f kokki_memory.sqlite*` before test runs if you see
`sqlite3.OperationalError: disk I/O error` — usually means a leftover
`uvicorn` process is still holding the same file open.
