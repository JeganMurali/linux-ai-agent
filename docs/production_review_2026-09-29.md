# Kokki Kumar: production review and current state (29 Sep 2026)

Reference document. It lists every known issue, every measurement, and what is still undecided.
Evidence labels: **VERIFIED** = reproduced by a reviewer or by me; **INFERRED** = read from code, not run.

## 1. Verdict

**53.5 / 100, grade D.** On the scale given to the reviewers (50 = works on the author's machine,
70 = solid hobby project, 85 = safe to hand to strangers): the streaming and sessions core is solid,
but v0.1 is **not ready for the community**. Fine for personal use. Most fixes are small.

| Category | Score | Main reason |
|---|---|---|
| Correctness and robustness | 15 / 25 | Input handling, one-terminal-event rule, restart hold; launch hang, interrupted tool call, dropped stdout break |
| Test quality | 9 / 15 | 90% branch coverage but only 57% of deliberate breaks caught; CI runs 5 of 72 offline tests |
| Security and safety | **6 / 15** | Blocklist trivially bypassed, confirmation only in the prompt, API key visible to commands, no auth |
| Performance and efficiency | 7 / 10 | Fast streaming, flat memory; storage and history listing scale badly |
| Architecture and maintainability | 6 / 10 | Clean modules and typed schemas; singletons, relative paths, stale docs |
| Live behaviour and UX (visual) | 8 / 15 | Polished and fast for chat; tool output invisible, 25 s launch, misleading errors |
| Production readiness and docs | **2.5 / 10** | No README, LICENSE, plugin in repo, service unit; CI covers about 6% |
| **Total** | **53.5 / 100** | Reviewer A 43/75, Reviewer B 10.5/25 |

Confidence: medium-high. Reviewer A used a fake model, so real Groq/Ollama behaviour is inferred.
Reviewer B made 8 real requests on one theme.

### How the review was done
- Two independent reviewers (same written instructions, `.claude/agents/production-reviewer.md`) ran in parallel.
- **A (code and runtime):** a snapshot of `master` at `a8b4240` plus a copy of the plugin. 45+ experiments,
  30 hand-made mutations with a control run, load and failure injection against its own server on port 8123
  with a fake model, no real model calls, no destructive command executed (executor stubbed).
- **B (live and visual):** used the real popup and the real server like a user, 8 real Groq requests,
  47 popup-only screenshots, per-frame window lists, read the logs; plus repository readiness.
- I re-checked the claims marked "checked by me" below.

### Checked by me (independent of the reviewers)
| Claim | Result |
|---|---|
| Blocklist misses dangerous variants and blocks harmless commands | 10 of 10 dangerous strings pass (`rm -rf ~`, `rm -rf $HOME`, `rm  -rf /`, `RM -RF /`, `find / -delete`, `chmod -R 777 /`, fork bomb, ...); 3 of 3 harmless ones blocked (`rm -rf /tmp/build-cache`). String comparison only, nothing executed. |
| Command output never shown; model assumes it was | Log: `ls -1 /usr/bin` ran, reply was "Here's the glorious dump..." with no list. |
| `/tmp what is in this folder` is swallowed as a command | Headless Qt: parsed as command `tmp`, `known:false`. My bug. |
| Interrupted tool call leaves an unanswered call | Not present in my real database (22 threads); only reproducible with an interruption. |
| Cleanup after the live review | 3 windows before and after; server up; 6 review sessions left in history. |

## 2. Issue register

Reviewer IDs are kept for cross-reference (F = Reviewer A, B and P = Reviewer B). Effort: XS under 30 min,
S a few hours, M a day. **Design** = already addressed by `docs/system_control_tool.md` (branch `tool-upgradation`).

### 2.1 Tool execution and launching
| # | Sev | Issue | Refs | Evidence | Fix | Effort | Design |
|---|---|---|---|---|---|---|---|
| 1 | **High** | A background or GUI launch holds the output pipe: false "timed out" after 20 s, output lost, model retries and opens a second window, orphan process | F2, B2 | `tools.py:47-55`; live: 25.3 s, 2 Nautilus windows; `sleep 24 & echo launched` = 20.02 s | Temp files instead of pipes; return on exit / new window / short wait | S | Yes |
| 2 | Med | On a non-zero exit stdout is dropped (`diff`, `grep` no match); stderr-only success returns "Done!" | F8 | `tools.py:57-60` | Return exit code + stdout + stderr, truncated | XS | Partly |
| 3 | Low | Output that is not valid UTF-8 becomes an error | F16 | `tools.py:48` | `errors="replace"` | XS | Yes |
| 4 | Med | Status shows "running system_control..." not the command; user cannot see what ran on their machine | B4 | screenshot 14a; `chatEvents.js:21` | Send the command in the `tool` event | S | No (v1 sends the name only) |
| 5 | **High** | Command output goes only to the model, the user never sees it, and the model assumes they did | B1 | screenshots 17b, 12-usrbin-t14; log 16:31 and 16:37 | Show a "ran `cmd`" row with truncated output; prompt rule "the user cannot see tool output" | S-M | No |
| 6 | Low | First window opens in the server's working directory, not home | B2 | window title `kokki-kumar` | `cwd=$HOME` | XS | No |
| 7 | Low | A new LLM client (and connection pool) is built for every call | F20 | `agent.py:33-36,50`; 12.35 ms each | Build once, reuse | XS | No |

### 2.2 Safety and security
| # | Sev | Issue | Refs | Evidence | Fix | Effort | Design |
|---|---|---|---|---|---|---|---|
| 8 | **High** | The "hard floor" is a substring match: 25 of 32 destructive probes pass (reviewer), 10 of 10 (mine); harmless commands blocked; the comment overstates the protection | F3 | `tools.py:15-17,38` | Parse commands and enforce a real policy; server-side confirmation (LangGraph `interrupt()`); test it | M | No |
| 9 | Med | Confirmation before disruptive actions exists only in the prompt; deleting the whole safety prompt keeps all 72 tests green; injected text in tool output can steer the model | F7 | mutants M13, M14 survived | Server-side confirmation; test that the safety text reaches the model | M | No |
| 10 | Med | `GROQ_API_KEY` is inherited by every shell command (`echo $GROQ_API_KEY` prints it) | F6 | `tools.py:48`, `config.py:4` | Pass a filtered `env=` | XS | No |
| 11 | Med | No authentication; a request with any `Host` header is served (DNS-rebinding class) | F5 | `api/server.py` | `TrustedHostMiddleware` + local token in a 0600 file | S | No |
| 12 | Med-High | Markdown sanitiser bypassed: two input forms still made Qt fetch a URL | F4 | `chatEvents.js:53-55`; request counter | Escape `<`, strip image syntax until stable; add both cases to tests | XS | No |
| 13 | Low | `.env` with the API key is written with the default umask (0644) | F22, P6 | `kokki_setup.py:314-317` | Create with 0600 | XS | No |

### 2.3 Reliability, data and cost
| # | Sev | Issue | Refs | Evidence | Fix | Effort | Design |
|---|---|---|---|---|---|---|---|
| 14 | **High** | If the client disconnects or the server dies while a tool runs, the thread keeps a tool call with no result; the next turn follows it and OpenAI-style APIs normally reject that shape | F1 | `agent.py:134-159`; reproduced two ways (Groq effect inferred) | Before each turn, add a synthetic "interrupted" tool result | S | No |
| 15 | Med | 10 concurrent turns on one thread all finish, only 1 is saved | F11 | astream_chat | Per-thread lock or 409 | XS | No |
| 16 | Med | Locked DB (35 s hang), corrupt DB and internal bugs all reported as "couldn't reach the groq backend"; INFO logs without traceback; `/health` ok with a corrupt DB | F10 | `agent.py:110-114,153-158` | Separate error classes, `logger.exception`, health checks the DB | S | No |
| 17 | Med | Checkpoint storage grows quadratically (148x the visible text; a 5 MB message adds 47.7 MB); `/threads` reads every checkpoint | F9 | `api/sessions.py:20-25` | Latest-per-thread SQL query, prune old checkpoints, cap message size | S-M | No |
| 18 | Med | Whole history plus a 638-token prompt is resent on every call, no trimming; the `bar` thread reached 3,554 tokens per call | F12, B5 | `agent.py:54`; 429 message | `trim_messages` to a token budget | S | No |
| 19 | Med | Misleading rate-limit message ("try rephrasing"), profanity hard-coded, shown green on this theme, logged at INFO | B3, F10 | `agent.py:108-109,150-151`; screenshot 23 | Specific messages with retry time, respect profanity setting, non-theme error colour | S | No |
| 20 | Low | `/chat` returns HTTP 200 with the error text as the reply | F14 | `api/server.py:33-37` | Return 502 | XS | No |
| 21 | Low | Thread ids with `/` can be written but never read; a 10,000-character id is accepted | F17 | `api/schemas.py:18` | Validate `^[A-Za-z0-9_-]{1,128}$` | XS | No |
| 22 | Low | DB and log paths depend on the working directory (empty memory if started elsewhere); log never rotates, is 0644, stores every prompt; tests write into the real `kokki.log` | F15, P4 | `memory.py:5`, `observability.py:9` | XDG paths, `RotatingFileHandler`, 0600, tests log to tmp | S | No |
| 23 | Low | The daily Groq token allowance runs out fast; the UI gives no warning or reset time | B5 | 429 body: 199,742 of 200,000 used | Lower per-call tokens (items 18, 7), show "limit reached, resets in X" | M | No |

### 2.4 Frontend and UX
| # | Sev | Issue | Refs | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| 24 | Med | Long unbroken words are clipped at the right edge | B6 | screenshot 13a; `Panel.qml:423` | `wrapMode: Text.Wrap` | XS |
| 25 | Med | A message starting with `/word ` is swallowed as an unknown command (my bug; the comment promised paths reach Kokki) | B7, F18 | `chatEvents.js:77-82`; verified by me | Only known command names are commands | XS |
| 26 | Low | `/open 9` typed in the history view gives no visible feedback | B8 | screenshots 08, 09 | Show the note inside the history view | XS |
| 27 | Low | Markdown links: 1.9:1 contrast, off-theme, not clickable | B9 | screenshot 18b | Theme link colour + open with an http(s) allow-check | XS |
| 28 | Low | Blank first-run screen: no intro, no "runs commands on this PC" notice, no server status, no current session; `/new` gives no confirmation | B10 | screenshots 01, 06, 25 | Empty-state intro with examples and a notice | S |
| 29 | Low | History titles are the raw first message; current session not marked; failed turns become 1-message threads | B11 | screenshots 07, 24 | Mark current; better titles later | S |
| 30 | Nit | One Esc closes the popup while a command is half-typed | B12 | screenshot 21c | First Esc clears, second closes | XS |
| 31 | Nit | Visual polish: menu columns, code spans look like body text, tiny emoji, static "thinking...", last chat line cut by the menu | B13 | screenshots 02, 18b, 17b, 21a | Small styling fixes | XS-S |
| 32 | Low | A second GET is silently dropped while one runs; the `/open` last-row boundary is untested; 60 ms timers are a guess | F19 | `Panel.qml:228-229,311,323` | Queue it or show a note; add the test | XS |
| 33 | Nit | An error event with no message renders "undefined" | A log | plugin | Default text | XS |

### 2.5 Tests, CI, packaging and docs
| # | Sev | Issue | Refs | Evidence | Fix | Effort |
|---|---|---|---|---|---|---|
| 34 | **High** | The QML plugin is not in the repo; a stranger gets a backend with no UI; plugin tests skip elsewhere | P1 | GitHub contents; `test_qml_logic.py:15` | Own repo with `manifest.json` at the root (Omarchy's installer requires it); decision pending | S |
| 35 | **High** | No README, no LICENSE (manifest claims MIT), no `.env.example`, no install or run guide | P2 | repo root; GitHub `license: null` | Write them | S |
| 36 | Med | CI runs 5 of 72 offline tests and does not install pytest-asyncio/httpx | F13, P3 | `ci.yml:26` | Install `.[dev]`, run everything except live tests | XS |
| 37 | Med | No supervision or restart story; server started by hand from the repo directory | P4 | HANDOFF.md | systemd user unit with `WorkingDirectory` | S |
| 38 | Med | Dependencies all `>=`, no lockfile; `groq`, `aiosqlite`, `langgraph` imported but not declared | P5, F21 | `pyproject.toml:10-20` | Declare and pin | XS |
| 39 | Med | Tests execute code without protecting behaviour: 17 of 30 mutants killed. Survivors: blocklist entry, timeout, stdin guard, truncation boundary, "Done!" placeholder, safety prompt, profanity setting, `/chat` thread id, no tools bound, `/open` last row | A s.5 | mutation runs | Add the missing assertions | S |
| 40 | Low | Setup wizard says `python setup.py`, ends with the CLI, says nothing about the server or plugin, defaults to profane | P6 | `kokki_setup.py:5,97,113` | Update text and defaults | XS |
| 41 | Low | HANDOFF.md is stale (117-line Panel.qml, "21+ tests", CI claim); versions disagree (pyproject 0.1.0, manifest 0.3.0) | P7, F21 | HANDOFF.md | Refresh; one version source | XS |
| 42 | Low | Hygiene: `benchmark.py` crashes (async never awaited), empty `ui_widget.py`, unused imports, private `_ensure_graph` reach-in, no lifespan hook (10 MB WAL), 2 mypy errors | F21 | various | Clean up | S |

### 2.6 Found after the review (thread-switching investigation, same day)
| # | Sev | Issue | Evidence | Fix | Effort |
|---|---|---|---|---|---|
| 43 | **High** | **Kokki asks for the sudo password in chat, and the user typed it.** It is sent to Groq, stored in plain text in the SQLite history, and written to `kokki.log`. The prompt's "confirm before sudo" rule is what makes the model ask | real conversation `bar-1790680305541`, messages 12-13 | Tell the user to change that password; never solicit secrets (prompt rule + refuse to store); a proper approval flow instead of typing passwords; scrub the DB and log | S (rule) / M (flow) |
| 44 | Med (**FIXED and verified live, 29 Sep**) | **Screen mixes two conversations if a message is sent while `/open` (or `/history`) is still loading.** The reply for thread X is drawn under thread Y's messages and the sent message disappears from view. Storage stays correct (message saved in X, Y untouched). The window is about 50 to 150 ms, reproduced with two back-to-back IPC calls | screenshot `switch-3-race.png`; database check | Treat a running GET as busy in `send()`; tag each stream with the session it started in and ignore it if the session changed | XS |
| 45 | Med | A failed turn (for example the 429) leaves the user's message with no reply, because the error is never saved. Later turns then show several unanswered messages and the model answers the old one too (verified: it answered an earlier "what time is it?" along with the new message) | real threads `bar-1790680305541` (messages 17-19), `bar-1790687324172`; test session `bar-1790680180517` | Save a short "could not answer" marker, or show failed turns in history | S |
| 46 | Low | After a shell restart the popup returns to the default `bar` conversation (56 messages), so a user expecting a fresh chat continues an old thread; the header does not say which conversation is active | live behaviour after each restart | Start a new session on open or restore the last one, and show the session in the header | S |

## 3. Benchmarks and measurements

### 3.1 Launching an app: how long the caller waits (stand-in program, 8 trials, timeout capped at 2 s)
| Method | Waited | App started |
|---|---|---|
| pipes, as `tools.py` does today | **2003 ms, timed out** | 8/8 |
| temp files instead of pipes | 9 ms | 8/8 |
| `Popen` fully detached | 1 ms | 8/8 |
| shell `>/dev/null 2>&1 &` | 6 ms | 8/8 |
| `setsid -f` + redirect | 9 ms | 8/8 |
| `uwsm-app -- app` | **timed out** (waits for the app) | killed at timeout |
| Omarchy Files pattern (`setsid uwsm-app -- app &`) | **timed out** (holds the pipes) | 8/8 |
| Omarchy browser pattern (`systemd-run ... StandardOutput=null`) | 23 ms | 8/8 |
| `hyprctl dispatch exec_cmd` | 30 ms | 8/8 |

Building blocks (no windows opened): plain `true` 8 ms; `xdg-settings get default-web-browser` 165 ms;
`xdg-mime query` 115 ms; `uwsm-app` wrapper 65 ms; `systemd-run` 32 ms; window list plus `jq` 32 ms;
`hyprctl clients -j` alone 14 ms. `omarchy launch browser` is about 215 ms (computed, not measured whole).

### 3.2 Does a clear result plus a system profile help the model? (real gpt-oss-120b, simulated machine)
27 clean runs (scenarios 1 to 3, before the daily cap); 3 runs per cell.

| Condition | Success | Commands per run | Duplicate windows | 20 s stalls | AI seconds per run |
|---|---|---|---|---|---|
| today's tool (bare text) | 1/9 | 3.44 | 11 | 15 | 6.0 |
| clear JSON result | 6/9 | 1.22 | 0 | 0 | 3.4 |
| clear JSON + system profile | 9/9 | 1.00 | 0 | 0 | 2.3 |

"open chrome" (not installed): 0/3, 0/3, 3/3. Limits: simulated machine, small sample, one model;
the simulation wrongly assumed `xdg-open` exits quickly (on this machine it stays running).
The last two scenarios hit the daily token cap and were discarded.

### 3.3 Live latency, real Groq (Reviewer B)
| Request | Time to result |
|---|---|
| greeting | first text about 0.5 to 0.9 s |
| default browser | 2.2 s |
| chrome? | 2.5 s |
| list home | 1.7 s |
| markdown answer | partial at 1.46 s, full 1.73 s |
| `ls /usr/bin` | about 21 s (first LLM call 19.46 s, unexplained) |
| open files | 25.3 s (20 s tool timeout, then a retry) |
| what time | HTTP 429 after 240 ms |

Log history (273 real Groq calls): median 1.1 s, p90 4.4 s, worst 173.7 s. Local popup actions instant; history loads in under 0.6 s.

### 3.4 Backend runtime (Reviewer A, fake model, own server on port 8123)
| Metric | Value |
|---|---|
| Startup to first `/health` (91 MB DB) | 1.25 s |
| `/health` sequential | p50 3.4 ms, p95 4.0 ms, max 5.2 ms |
| Stream, 20 tokens, time to first byte | p50 10.5 ms, p95 11.8 ms |
| 10 / 50 / 100 concurrent streams x 200 tokens | total p95 347 ms / 2,061 ms / 2,552 ms, all done, about 5.7k / 4.8k / 7.6k tokens/s |
| Tool round trip (`echo`) | about 25 ms |
| `GET /threads` | 256 ms (about 300 threads), 1,085 ms (about 1,300 threads) |
| `GET /threads/{id}/messages` | 3.5 ms |
| Memory (RSS) | 95.8 MB at start, 107.6 MB after about 290 turns, still 107.6 MB after 1,000 more |
| Storage | 100 short turns: 6.07 MB (148x the visible text); one 5 MB message: +47.7 MB |
| SIGTERM to exit | 0.18 s |
| `get_llm()` + `bind_tools` | 12.35 ms per call |

Event layer versus the old raw token loop (my benchmark): +2 ms per 2,000 tokens (+4%); noise at realistic pacing.
Session listing on my real database: 355 ms for 15 threads / 289 snapshots. My real database now: 5.2 MB, 348 snapshots, 22 threads.

### 3.7 Thread isolation tests (29 Sep, evening)
| Test | Result |
|---|---|
| Audit of the real database (24 threads, 233 messages): same message id in 2+ threads | **0**. Nothing was ever copied between conversations. (3 long texts repeat across threads: my own test prompts, different ids.) |
| 160 turns on 40 threads running concurrently, real SQLite saver, model that echoes every foreign secret it sees | **0 leaks**, 160/160 finished cleanly, every thread stored exactly its own 8 messages |
| 11 awkward ids on a fresh database (`bar`, `bar-1`, `bar-10`, `Bar`, `bar `, `bar%`, `bar_`, `b_r`, Tamil text, `a/b`, empty) | all isolated; the empty id is stored as `main` (the shared default) |
| Live popup: `/history` then `/open` a session, then send | message saved only in that session; `bar` and other sessions unchanged |
| Live popup: `/new`, then send | message saved only in the new session; previous session unchanged |
| Live popup: send while `/open` is loading | before the fix: storage correct, **screen mixed** (issue 44). After the fix: the message is refused with `loading`, nothing saved, the screen shows only the opened conversation |
| 4 turns fired at the same thread at once | only 2 of 8 messages persisted: known lost-update race inside one thread (issue 15), not a cross-thread leak |

Conclusion: the backend keeps conversations separate. Confusing behaviour comes from the popup (issues 44, 45, 46) and from unanswered messages after failed turns.

### 3.5 Test suite
- Master: 83 test functions in 10 files; 72 run offline (the three model-backed files are excluded); all pass in about 7.4 s, stable over 5 random orders.
- 90% branch coverage. Not covered: `/chat`, `KokkiAgent.chat`, `get_llm`, the real `memory.py`, the tool's timeout and exception branches.
- Mutation: control passed; 17 of 30 killed (57%). All 6 sessions mutants killed; 13 survivors listed in issue 39.
- CI on GitHub: green, but runs 1 file, 5 tests.
- Tools: `qmllint` clean apart from inherent warnings; `pip-audit` found nothing in 58 packages.

### 3.6 Groq limits (gpt-oss-120b)
1,000 requests per day; 8,000 tokens per minute; 200,000 tokens per day, counted over a rolling 24 hours (it does not refill steadily).
Counters are per model: `gpt-oss-20b` showed its own fresh request allowance. A minimal fresh-session call asked for 985 tokens; one call on the long `bar` thread asked for 3,554.

## 4. What is solid
- Streaming contract: typed events, exactly one terminal event even under failure, verified by failure injection.
- Sessions and history API: exact-assertion tests, every mutant caught.
- Memory flat over 1,000 turns, no leaked handles, clean shutdown, history survives restart, 100 concurrent streams finished.
- Malformed input handled (422), unicode and NUL survive, localhost only, no CORS.
- Popup: native Omarchy look, command menu (filter, highlight, Tab, Enter), busy guard, safe close and reopen mid-request, drafts kept, history and `/open`, Markdown safe against image fetches.
- Plugin keeps logic in a pure JS module tested headlessly, and passes `curl` an argument array.

## 5. Current state
- `master` at `a8b4240`, pushed; CI green. Branch `tool-upgradation` (local, not pushed) at `f3c6e3c` holds the design doc, red contract tests and evals.
- Not in git: the plugin (`~/.config/omarchy/plugins/kokki`). Untracked here: `.claude/agents/production-reviewer.md`, this report, `docs/reviews/`.
- Live: server on :8000. 6 sessions created by the review sit in the history list.
- Corrections made during this work: the Groq daily allowance is a rolling 24 hours (not a steady refill); Qt's JavaScript parses microsecond timestamps fine (my guess was wrong); my first mutation check was invalid (missing config) and was redone with a control.

## 6. Decisions still open
1. **Safety model** (issues 8-11): honest and modest ("best effort, runs as you") with cheap fixes, or server-enforced confirmation?
2. **Tool design**: the six decisions in `docs/system_control_tool.md` section 10 (one tool, window detection, 3 s wait, stderr only on failure, profile in the prompt, evals on `gpt-oss-20b`).
3. **Visibility**: show each command and its output in the chat (issues 4-5).
4. **History size** sent to the model, and whether to prune stored checkpoints (17-18).
5. **Plugin repo** name and visibility (34), README and LICENSE choice (35).
6. Which issues belong in v0.1.
7. Secrets policy: what happens when a user types a password into the chat (issue 43).

## 7. Suggested order for v0.1 (proposal)
1. Tool upgrade (issues 1, 2, 3, 6) plus showing commands and output (4, 5).
2. Cheap safety fixes (10, 11, 12, 13) and an honest statement of the safety model; then decide 8-9.
3. Reliability: interrupted-tool repair (14), error messages (16, 19, 20), trim history (18), cache the client (7).
4. Ship bundle: plugin repo, README, LICENSE, `.env.example`, CI runs offline tests, pinned dependencies, service unit, XDG paths (22, 34-38, 40-41).
5. Frontend one-liners (24-27, 30-33) and the missing test assertions (39).
6. Re-run the reviewer agent and compare the score.

## 8. Artifacts and how to repeat
- Full reviewer reports: `docs/reviews/review-A-backend.md`, `docs/reviews/review-B-live.md`.
- Reviewer instructions: `.claude/agents/production-reviewer.md`.
- Screenshots and scratch (temporary folder, may be cleared): `/tmp/claude-1000/-home-jeganmurali-Work/82a7e7e3-5d05-4e0b-a4ba-ef9741c15496/scratchpad/prod-review/` (`screens/` has 47 popup-only PNGs).
- Benchmarks and evals on branch `tool-upgradation`: `evals/`, `docs/system_control_tool.md`.
