# Kokki Kumar v0.1 candidate: Production Review A (backend, tests, plugin logic)

Reviewer A. Scope: git-master snapshot (`R/app`) and plugin copy (`R/plugin`). I only read the code and ran it in scratch copies, with a fake model and no real LLM calls. Destructive command strings were checked against the guard with `subprocess.run` stubbed, so none of them ran. `R` = `/tmp/claude-1000/-home-jeganmurali-Work/82a7e7e3-5d05-4e0b-a4ba-ef9741c15496/scratchpad/prod-review`.

## 1. Verdict

**43 / 75 (57 %), grade D.** Letter mapping on the brief's calibration scale: A ≥ 85, B ≥ 75, C ≥ 65, D ≥ 50, F < 50.

**Ship with fixes; do not ship as-is.** The streaming and session layer is solid and well tested. But three things fail in normal use:
- An interrupted tool call leaves the conversation in a broken state.
- Launching an app in the background reports a false timeout.
- Two advertised safety controls (the command blocklist and the Markdown image sanitizer) don't do what their comments say.

All of these are small fixes.

## 2. Scorecard

| Category | Score | Evidence |
|---|---|---|
| Correctness and robustness | **15 / 25** | **Holds:**<br>• Input validation (422s).<br>• Unicode, NUL and surrogate handling.<br>• Exactly one terminal event under failure.<br>• Clean SIGTERM.<br>• History persists across restart.<br>**Breaks:**<br>• F1: dangling tool call after disconnect or crash.<br>• F2: background launch gives a false 20 s timeout.<br>• F8: stdout is dropped when the exit code is non-zero.<br>• F11: same-thread concurrent turns lose data.<br>• F10: every failure is reported as "couldn't reach the backend". |
| Test quality | **9 / 15** (capped at 10: CI runs 5 of 72 offline tests) | 72 offline tests in 7.4 s. Deterministic across 5 random orders. 90 % branch coverage. Assertions are exact. **Mutation kill rate is 17/30 (57 %).** No test covers the safety prompt, the tool guard, the timeout, `/chat`, or config. |
| Security and safety | **6 / 15** | • Blocklist: 25 of 32 destructive probe strings get past it, and 5 of 7 benign commands are wrongly blocked (F3).<br>• The Markdown sanitizer can be bypassed (F4).<br>• No auth, and any Host header is accepted (F5).<br>• The tool's environment includes the API key (F6).<br>• Credit: binds to 127.0.0.1; no CORS; text/plain and no-Content-Type bodies are rejected; the plugin passes curl an argv array, not a shell string; pip-audit is clean. |
| Performance and efficiency | **7 / 10** | • Stream TTFB p50 10.5 ms.<br>• 100 concurrent streams: 100 of 100 finish.<br>• RSS flat at 107.6 MB over 1,000 turns, no fd or thread leak.<br>• But checkpoint storage grows quadratically (148x), and `GET /threads` goes from 256 ms to 1,085 ms as history grows (F9). |
| Architecture and maintainability | **6 / 10** | • Small, clear modules; typed event schema; pure-JS helpers tested headlessly.<br>• But: module-level singletons, config read at import time, the server reaches into private agent internals, paths are relative to the cwd, no lifespan hook, a broken `benchmark.py`, and stale HANDOFF.md claims (F21). |

Overall confidence: **Medium-High.** Everything was measured with a fake model. Real Groq/Ollama behaviour (latency, how it treats malformed history, how it responds to prompt injection) is inferred.

## 3. Findings

Confidence per finding: High unless marked.

| ID | Sev | Cat | Status | Where | What happens | Fix | Effort |
|---|---|---|---|---|---|---|---|
| F1 | High | Correctness | VERIFIED (state) / INFERRED (Groq rejection, Medium) | `kokki/agent.py:134-159`, checkpointing | If the client disconnects (or the server is SIGKILLed) while a tool runs, the command still finishes (marker file written) but the thread keeps `AIMessage(tool_calls)` with no `ToolMessage`; the next turn appends a HumanMessage after it. OpenAI-style APIs normally reject that, so the thread would keep failing. It is triggered by plugin reloads, the curl `--max-time`, or a crash. | Before each turn, insert a synthetic `ToolMessage("interrupted")` for every tool call without an answer (or check `aget_state().next`). | S |
| F2 | High | Correctness | VERIFIED | `kokki/tools.py:47-55` | `cmd &` (the common way to launch an app) keeps the capture pipe open. `sleep 24 & echo launched` returned "Command timed out (>20 seconds)" after 20.02 s, the output was lost, and the child was left orphaned. `sleep 3 &` took 3.01 s. | Send output to temp files instead of pipes, or use `start_new_session=True` with DEVNULL for background jobs. | S |
| F3 | High | Security | VERIFIED | `kokki/tools.py:15-17,38` | The "hard floor" is a plain substring match. My probe set (`scratch/guard/probe_guard.py`, executor stubbed) got 25 of 32 destructive strings past it, including variants that destroy home-directory data without root. 5 of 7 benign commands were blocked (for example `rm -rf /tmp/…`, `man mkfs`). The comment overstates the protection. | Make this a real check: parse the command (shlex/bashlex) and enforce policy for recursive deletes of home or root and for writes to block devices. Add a server-side human confirmation via LangGraph `interrupt()` for risky classes. Test it. | M |
| F4 | Med-High | Security | VERIFIED | `plugin/chatEvents.js:53-55` | `safeMarkdown` can be bypassed. Two input forms still made Qt fetch a URL after sanitising (local request counter, `scratch/md/srv.py`). Untrusted model output can therefore trigger network requests from the desktop. | Escape `<` and remove image syntax in a loop until the text stops changing; add both cases to the QML test. | XS |
| F5 | Medium | Security | VERIFIED (server) / INFERRED (browser path) | `api/server.py` | No authentication, and a request with `Host: attacker.example` is served normally. Anything that can reach the loopback port with a matching Host (DNS-rebinding class) can read history and drive the agent. | Add `TrustedHostMiddleware` for localhost/127.0.0.1 and a random bearer token in a 0600 file that the plugin reads. | S |
| F6 | Medium | Security | VERIFIED | `kokki/tools.py:48`, `kokki/config.py:4` | `load_dotenv` puts `GROQ_API_KEY` into `os.environ`, and every shell command inherits it (`echo $GROQ_API_KEY` printed a dummy key). | Pass a filtered `env=` without secrets. | XS |
| F7 | Medium | Security | INFERRED (Medium) | `kokki/prompts.py` | Confirmation before disruptive actions exists only in the prompt, and tool output flows back into the model, so injected text can steer it. Mutants M13 and M14 (remove the system prompt or the safety rules) survived with 72/72 green. | Server-side confirmation (see F3) and a test asserting the safety text is present in the first SystemMessage. | M |
| F8 | Medium | Correctness | VERIFIED | `kokki/tools.py:57-60` | On a non-zero exit, stdout is dropped: `diff`, a `grep` with no match, and `echo x; exit 1` all return `"Error: "`. A command that succeeds with output only on stderr returns "Done!". | Return the exit code plus stdout and stderr, truncated. | XS |
| F9 | Medium | Performance | VERIFIED | `api/sessions.py:20-25`, SqliteSaver | 100 short turns stored 300 checkpoints totalling 6.07 MB, for about 41 KB of visible text (148x). Growth per 25 turns keeps rising (1.0, 1.7, 2.1 MB). One 5 MB message added 47.7 MB, and the next turn added about 38 MB more. `/threads` deserialises every checkpoint: 256 ms at about 300 threads, 1,085 ms at about 1,300. | One SQL query for the latest checkpoint per thread (or a small sessions table); prune old checkpoints; `max_length` on `message`. | S-M |
| F10 | Medium | Correctness | VERIFIED | `kokki/agent.py:110-114,153-158` | A locked DB hung 35 s, a corrupt DB failed, and other internal errors failed; all of them were reported as "couldn't reach the groq backend - is it actually running?". Errors are logged at INFO with `repr` and no traceback. `/health` returns ok even with a corrupt DB (history routes return 500). | Separate error classes; use `logger.exception`; have health check the DB. | S |
| F11 | Medium | Correctness | VERIFIED (Medium likelihood) | `KokkiAgent.astream_chat` | 10 concurrent turns on one thread all streamed `done`, but only 1 of 10 was persisted. | A per-thread `asyncio.Lock`, or return 409 while that thread is busy. | XS |
| F12 | Medium | Correctness/Cost | INFERRED | `kokki/agent.py:54` | The whole thread plus a 638-token system prompt is sent on every LLM call (twice for a turn that uses a tool). The plugin's default `bar` thread grows without limit and will eventually hit the provider's context or rate limits. | Use `trim_messages` to a token budget. | S |
| F13 | Medium | Tests | VERIFIED | `.github/workflows/ci.yml:26` | CI runs only `tests/test_tools.py` (5 of 72 offline tests) and does not install pytest-asyncio or httpx. HANDOFF says test_smoke also runs in CI; it doesn't. | Install `.[dev]` and run everything except live tests (mark those `@pytest.mark.live`). | XS |
| F14 | Low | Correctness | VERIFIED | `api/server.py:33-37` | A backend failure on `/chat` returns HTTP 200 with the error text as `reply`. | Return 502 with a detail message. | XS |
| F15 | Low | Correctness/Privacy | VERIFIED | `kokki/memory.py:5`, `kokki/observability.py:9` | The DB and log paths are relative to the cwd, so starting from another directory silently gives empty memory. The log never rotates (520 KB after about 1.3k short turns, +5 MB from one large message), is created 0644, and stores every prompt, command and reply. The test run writes `kokki.log` into the repo. | XDG state dir, `RotatingFileHandler`, 0600 permissions. | S |
| F16 | Low | Correctness | VERIFIED | `kokki/tools.py:48` | Output that isn't valid UTF-8 returns a decode error even though the command ran. | `errors="replace"`. | XS |
| F17 | Low | Correctness | VERIFIED | `api/schemas.py:18` | Thread ids containing `/` are accepted on POST but can never be read back (404). A 10,000-character id is accepted. The plugin's initial `sessionId` is the unsanitised setting. | Validate ids with `^[A-Za-z0-9_-]{1,128}$`. | XS |
| F18 | Low | Plugin | VERIFIED | `chatEvents.js:77-82` | "/tmp is full, clean it" is treated as the unknown command `/tmp` and never reaches Kokki. | Only treat known command names as commands. | XS |
| F19 | Low | Plugin | INFERRED | `Panel.qml:228-229,311,323` | `startGet` silently ignores a request while another GET is running (so `/open` during a history load does nothing). The 60 ms timers are a guess at the exit/stdout ordering. The `/open` last-row boundary is untested (M28 survived). | Queue the request or show a note; add a boundary test. | XS |
| F20 | Low | Performance | VERIFIED | `kokki/agent.py:33-36,50` | `get_llm()` builds a new ChatGroq and httpx pool on every LLM call: 12.35 ms of CPU on the event loop each time, and no connection reuse. | Build it once and cache it. | XS |
| F21 | Low | Architecture | VERIFIED | various | • `benchmark.py` crashes (async `chat` is never awaited).<br>• `kokki/ui_widget.py` is empty; 4 unused imports.<br>• HANDOFF.md is stale (says Panel.qml has "no network code").<br>• The schemas comment names `/chat/events`.<br>• The server calls private `_ensure_graph` and `graph.checkpointer`.<br>• No lifespan hook: the aiosqlite connection is never closed, leaving a 10 MB WAL.<br>• Dependencies are unpinned; `groq`, `aiosqlite` and `langgraph` are imported but not declared.<br>• 2 mypy implicit-Optional errors. | Clean up; add a lifespan hook and a lockfile. | S |
| F22 | Low | Security | INFERRED | `kokki_setup.py:314-317` | `.env` holding the API key is written with the default umask (0644). | Create it with 0600. | XS |

## 4. What I broke and what I could not break

**Broke (VERIFIED):**
- F1: dangling tool call, reproduced two ways (disconnect, and SIGKILL).
- F2: false timeout for a background launch.
- F3: guard probe, 25/32 destructive strings pass, 5/7 benign blocked.
- F4: two sanitizer bypasses.
- F5: foreign Host header accepted.
- F6: API key visible in the tool's environment.
- F8: three ways stdout gets dropped.
- F9: quadratic storage; `/threads` slows down; 5 MB message amplification.
- F10: locked DB (35 s hang), corrupt DB (2 variants), misleading message.
- F11: 1 of 10 same-thread turns persisted.
- F14: `/chat` returns 200 on failure.
- F16: invalid UTF-8.
- F17: thread ids with `/`, and a 10k-character id.
- F18: path-like messages swallowed.
- An error event without a message renders "undefined" (Nit).

**Could not break:**
- Malformed JSON, missing fields and wrong-type fields all return 422.
- Emoji, RTL, NUL and bell characters round-trip exactly; a lone surrogate is stored as "?" with no crash.
- SQL-looking thread ids are harmless.
- text/plain and no-Content-Type bodies return 422; CORS preflight returns 405.
- A backend failure mid-stream gives a token, then exactly one error event, over HTTP 200.
- A 3 s tool does not block the event loop (`/health` max 3.9 ms meanwhile).
- 5 mid-stream disconnects left no fd or thread leak, and the next turn was fine.
- 20 concurrent cold-start requests opened exactly 1 connection (the double-init race did not reproduce).
- 100 concurrent streams: 100/100 done.
- 1,000-turn soak: RSS flat, threads 5, fds 31.
- SIGTERM exit takes 0.18 s; restarting over a 91 MB DB answers `/health` in 1.25 s with history intact.
- NUL in a command gives a clean error; stderr is truncated to 2,035 chars.
- `repr()` in logging stops log-line injection.
- 5 random test orders all pass.
- qmllint shows nothing beyond the inherent QObject/ExitStatus warnings.
- pip-audit finds no vulnerabilities in 58 packages.

I ran over 45 experiments in total. Logs are in the scripts listed under Artifacts.

## 5. Test-suite quality

- **Baseline:** 72 passed, 7.39 s. The live-model files (test_api, test_memory, test_agent_integration) were excluded as instructed. That split is sensible, except that `test_health` and `test_create_thread` in test_api.py need no model and are skipped for no reason.
- **Coverage:** 90 % branch. Not covered: the `/chat` route, `KokkiAgent.chat`, `get_llm`, the real `memory.py`, and the tool's timeout and exception branches.
- **Mutation:** the control run passed (72/72). Kill rate **17/30 = 57 %.**
  - Survivors:
    - M01: truncate boundary.
    - M03: "dd if=" removed from the blocklist.
    - M05: timeout 20 s to 2,000 s.
    - M06: `stdin=DEVNULL` removed.
    - M07: "Done!" placeholder removed.
    - M09: tool event emitted for every chunk.
    - M13: system prompt never sent.
    - M14: safety rules removed.
    - M15: profanity setting ignored.
    - M24: `/chat` ignores `thread_id`.
    - M25: `/chat` APIError becomes a 500.
    - M28: `/open` rejects the last row.
    - M30: no tools bound by default. This also shows that no test checks a ToolMessage's content reaching the model.
  - Killed: every sessions.py mutant (6/6), 2/3 in server.py, 5/6 in the stream path, and 3/4 in the JS.
- **Isolation:** tests monkeypatch module globals and reset `server.kokki.graph`. `test_qml_logic` depends on `KOKKI_PLUGIN_DIR` pointing at `~/.config` by default, so it skips silently when that is missing.

## 6. Runtime numbers (fake model, 127.0.0.1:8123, SQLite in scratch)

| Metric | Value |
|---|---|
| Startup to first `/health` (91 MB DB) | 1.25 s |
| `/health` sequential, n=500 | p50 3.4, p95 4.0, max 5.2 ms |
| Stream, 20 tokens, sequential, n=100 | TTFB p50 10.5 / p95 11.8 ms; total p50 17.8 / p95 20.3 ms |
| 10 / 50 / 100 concurrent × 200 tokens | total p95 347 ms / 2,061 ms / 2,552 ms; all done; 5.7k / 4.8k / 7.6k tok/s |
| Tool round-trip (`echo`) | p50 24.7, p95 25.2 ms |
| `GET /threads` | 256 ms (about 300 threads), 1,085 ms (about 1,300 threads), 898 ms after a 5 MB row |
| `GET /threads/{id}/messages` | 3.5 ms |
| RSS | 95.8 MB at start, 107.6 MB after about 290 turns, still 107.6 MB after 1,000 more |
| Storage | 100 turns: 6.07 MB of blobs; 5 MB message: +47.7 MB |
| SIGTERM to exit | 0.18 s |
| `get_llm()` + `bind_tools` | 12.35 ms per LLM call |

## 7. Top 5 optimizations

1. **Replace the `/threads` full scan with a latest-per-thread SQL query, and prune old checkpoints.** Measured today: 1,085 ms and 148x storage amplification. The expected drop to milliseconds is an estimate.
2. **Trim history to a token budget.** This bounds per-call token cost, which today grows linearly with thread length plus 638 tokens per call (inferred).
3. **Cache the LLM client.** Measured saving: 12 ms of CPU per call. Reusing the connection also removes a TLS handshake per call (inferred).
4. **Cap message size and thread-id length.** A 5 MB message currently adds about 86 MB of storage over two turns.
5. **Rework the tool's output capture** (temp files, detached sessions, exit code plus stdout and stderr). This fixes F2 and F8 and removes 20 s false waits.

## 8. Strengths

- A clear, typed streaming contract (discriminated `ChatEvent`), with tests that hold under failure injection.
- A good fake-model harness.
- A sessions API with exact-assertion tests (every sessions.py mutant killed).
- The plugin keeps its logic in a pure-JS module tested headlessly under Qt, and passes curl an argv array.
- Stable memory, no leaks, clean shutdown, persistence across restart.
- Binds to localhost with no CORS.
- The comments explain *why*.

## 9. Limits and confidence

- No real Groq or Ollama calls. Model handling of a dangling tool call, the prompt-injection path, and real latencies are all INFERRED.
- The browser-side reachability in F5 is not tested.
- I did not execute any destructive command. The guard was judged with the executor stubbed.
- I did not run the plugin inside Quickshell; Reviewer B covers the live UI. Panel.qml state-machine issues (F19) come from reading the code.
- Mutations were hand-picked (30). They are not an exhaustive tool run.

## 10. Artifacts (all under `R/scratch`)

| Path | What it is |
|---|---|
| `guard/probe_guard.py` | Stubbed-executor probe of the command guard |
| `toolrt/tool_runtime.py` | Benign real runs of the tool |
| `server/fake_model.py`, `server/launch.py` | Directive-driven fake model and the uvicorn launcher on port 8123 |
| `client/adv1.py`, `adv2.py`, `load.py`, `storage.py`, `lock.py`, `restart.py`, `inspect_db.py` | Adversarial, load, storage and restart experiments, plus a checkpoint inspector |
| `run/`, `run2/`, `run3/` | Server DBs and logs, the corrupt-DB test, the crash-mid-tool test |
| `md/srv.py` | Markdown network-fetch harness |
| `qmlx/edge.qml` | JS edge-case probes |
| `lint/lint.txt` | qmllint output |
| `mut/run_mutants.py`, `mut/results.json`, `mut/base/`, `mut/.coverage` | Mutation runner and results, the control copy, coverage data |
| `llmcost/cost.py` | Client-construction cost measurement |
| `freeze.txt` | Package list fed to pip-audit |
| `toolvenv/` | Throwaway tools venv |

My servers are stopped and port 8123 is free.
