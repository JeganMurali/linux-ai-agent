# Kokki Kumar v0.1: Production Review B (live use + production readiness)

Reviewer B. Date: 2026-09-29, 16:27 to 16:42 local time.
Scope: the real running product (FastAPI server on 127.0.0.1:8000 with Groq `openai/gpt-oss-120b`, and the Omarchy bar-widget popup `jeganmurali.kokki`), driven through IPC and a few `wtype` keys. Production readiness was read from the code snapshot `R/app` and the public GitHub repo.
`R` = `/tmp/claude-1000/-home-jeganmurali-Work/82a7e7e3-5d05-4e0b-a4ba-ef9741c15496/scratchpad/prod-review`

Evidence labels: **[SS]** = I looked at a screenshot, **[LOG]** = `kokki.log` / server log / API output, **[CODE]** = read in source, **[GH]** = public GitHub API.
Every screenshot is cropped to the popup only (geometry `1175,29 346x414`). My first capture used the suggested `1030,10 500x520` region, which included content outside the popup, so I deleted it and re-cropped.

---

## 1. Verdict

**10.5 / 25 (42 %), grade D. Do not ship to the community yet.**
The popup itself is polished, fast for plain chat and well themed. But the core agent loop lets the user down on informational commands: tool output is never shown, and the model believes it was. Launching a GUI app blocks for 20 s and then opens the app twice. And there is no README, no LICENSE, and no plugin in the repo, so a stranger cannot install it at all.

## 2. Scorecard

| Category | Score | Evidence |
|---|---|---|
| Live behaviour and UX (visual) | **8 / 15** (cap applied: a core task failure caps this at 10) | Only 4 of my 8 real requests gave a clean, correct, visible result. "List the files in my home folder" got a roast and no list [SS 17b][LOG]. "Open files app" took 25.3 s and opened 2 Nautilus windows [LOG][windows.txt]. The rate-limit error advises "try rephrasing" and shows in green [SS 23]. On the plus side, chat replies take 0.9 to 2.7 s, the command menu, history and `/open` work, and Markdown and tables render well [SS 03-05, 07, 18b]. |
| Production readiness and docs | **2.5 / 10** (cap applied: with no install path for strangers this is capped at 4) | The repo has no README, no LICENSE and no `.env.example` [GH]. The QML plugin is not in the repo at all [GH][CODE tests/test_qml_logic.py:15]. CI runs 1 of 10 test files, which is 5 of 83 test functions [CODE ci.yml]. Dependencies are unpinned `>=` with no lockfile. There is no service unit, the log and DB paths are relative to the working directory, and HANDOFF.md is stale in several places. |
| **Total** | **10.5 / 25** | |

**Overall confidence: Medium-High.** Everything visual was observed directly and timed from logs. But there were only 8 model requests, the LLM is non-deterministic, only one theme was tested, and several states could not be reached safely (server down, history paging, Ollama backend).

## 3. Findings

| ID | Sev | Category | Label | Where | What happens | Fix | Effort | Conf |
|---|---|---|---|---|---|---|---|---|
| B1 | **High** | UX / agent loop | VERIFIED [SS][LOG] | `screens/17b-home-list-answer.png`, `12-usrbin-t14.png`; log 16:37:00 and 16:31:32; `kokki/tools.py`, `prompts.py` | Command output goes only to the model. The user never sees it, and the model assumes they did. "list the files in my home folder" ran `ls -A ~`, then replied "Nice try, but your home looks like a junk drawer" with **no file names**; the model's thinking says "We already did." "/usr/bin has what" gave "Here's the glorious dump of every binary…" and nothing was shown. The API history also stores only the reply, with no output. | Show each tool call in the chat as a small "ran `cmd`" row with the truncated output (collapsible). And add a fixed prompt rule: "the user cannot see tool output; put the answer data in your reply." | S–M | High |
| B2 | **High** | UX / reliability | VERIFIED [LOG][windows list][SS] | `scratch/seq5/windows.txt`; log 16:35:06–16:35:31; `screens/16a-files-busy-12.8s.png`, `16b`; `kokki/tools.py:48-54` | "open files app": the model ran `xdg-open .`. Nautilus appeared at 3.2 s, but `subprocess.run(capture_output=True, timeout=20)` waited on the pipe until the 20 s timeout. The model saw "Command timed out", retried `xdg-open $HOME`, and a **second window** opened at 24.3 s. The reply appeared at 25.3 s. For 23 s the only feedback was a static "running system_control…". The first window opened in the **server's working directory** (window title `kokki-kumar`), not home. | Launch GUI and detached commands without holding the pipes (`start_new_session=True` with stdout/stderr to DEVNULL for launchers, or return after N ms if the process is still alive). Set `cwd=$HOME`. A dedicated app-launch tool is worth discussing. | S | High |
| B3 | Medium | UX / errors | VERIFIED [SS][LOG][CODE] | `screens/23-reopen-after-close-midrequest.png`; log 16:39:41; `kokki/agent.py:108-109,150-151` | Hitting Groq's **daily** quota (TPD 200,000, used 199,742, "try again in 5m14s") shows "Fuck, Groq choked on that one - try rephrasing it." The advice is wrong, and the profanity is hard-coded (ignores `KOKKI_PROFANITY=false`). The error text is bright green (theme `Color.urgent` is green here), so it reads like success. The failure is logged at INFO. The failed turn leaves a 1-message thread, and the error is not persisted. | Map `RateLimitError` / 401 / timeout / connection to specific messages that include the retry time. Respect the profanity setting. Use a red or dim-italic error style that doesn't rely on theme `urgent`. Log at WARNING. | S | High |
| B4 | Medium | UX / transparency | VERIFIED [SS] | `screens/14a-browser-status-running.png`; `chatEvents.js:21` | The status shows the internal tool name, "running system_control…", never the actual shell command. For an agent that runs arbitrary shell commands, the user cannot see what was run on their machine. | Send the command string in the `tool` event and show "running `xdg-settings get …`". | S | High |
| B5 | Medium | Cost / availability | VERIFIED [LOG], extrapolation INFERRED | log 16:39:41 (429 body) | The Groq free-tier daily token cap was exhausted during this review (my 7 successful requests plus the day's other use). A fresh-session "what time is it?" asked for 985 tokens, and every tool turn needs 2 LLM calls plus reasoning tokens. Community users on the free tier will hit the daily cap, and the UI gives no warning or quota hint. | Lower the reasoning effort for gpt-oss, shorten the system prompt, trim history per call, and show "daily limit reached, resets in X". | M | Medium |
| B6 | Medium | UX / rendering | VERIFIED [SS] | `screens/13a-greeting-0.51s.png`; `Panel.qml:423` | A long unbroken token (URL, path, hash) is **clipped** at the right edge instead of wrapping (`Text.WordWrap`). | `wrapMode: Text.Wrap` (breaks at word boundaries, falls back to anywhere). | XS | High |
| B7 | Medium | UX / input parsing | VERIFIED [IPC return words][SS] | `chatEvents.js:77-82`; `screens/12-usrbin-t1.png` | "/tmp what is in this folder" is swallowed as "Unknown command /tmp" (returned `unknown`). "/usr/bin has what" goes to Kokki (returned `ok`, used a real request). The code comment promises that path messages reach Kokki; only multi-segment paths do. | Treat a `/word` as a command only when `word` is a known command (or a prefix of one while the menu is open); send everything else to Kokki. | XS | High |
| B8 | Low | UX / feedback | VERIFIED [SS] | `screens/08-open-bad-number-in-history.png`, `09-history-toggled-closed.png`; `Panel.qml:220-222,392` | `/open 9` typed while the history list is showing gives **no visible feedback**. The note goes into the hidden chat view and only appears after leaving history. | Show the note inside the history view, or close history before adding the note. | XS | High |
| B9 | Low | UX / links | VERIFIED [SS] contrast; clickability INFERRED [CODE] | `screens/18b-markdown-final.png`; `Panel.qml:421-431` | Markdown links render in Qt's default blue `(2,2,222)`: **1.9:1 contrast** on the `(11,12,22)` background (WCAG needs 4.5), and off-theme. The `Text` has no `onLinkActivated`, so the links look clickable but do nothing. | `linkColor: Color.accent`, and `onLinkActivated: Qt.openUrlExternally(link)` after an http(s) allow-check. | XS | Medium |
| B10 | Low | Discoverability | VERIFIED [SS] | `screens/01-open-initial.png`, `06-help.png`, `25-final-before-close.png` | First run shows a big blank panel with "KOKKI" and "type / for commands". Nothing says what Kokki can do, that it **runs real shell commands on your machine**, whether the server is reachable, or which conversation you are in. `/new` gives no confirmation, and `/new extra words` silently ignores the words. `/help` lists 4 commands but not Esc, Tab or clicking. | A one-line empty-state intro with 2 or 3 example prompts, a "runs commands on this PC" notice, a health check on open, and the current session title in the header. | S | High |
| B11 | Low | History UX | VERIFIED [SS][API] | `screens/07-history.png`, `24-history-final.png` | Titles are the raw first message ("hi", "hii", "hi"), so sessions are hard to tell apart. There is no marker for the current session. A failed turn becomes a "1 msg" thread whose reopened view has no reply. | Mark the current session, and later derive a title from the first real request. | S | Medium |
| B12 | Nit | Keyboard | VERIFIED [SS] | `screens/21c-esc-with-arg.png` | Esc clears the input only while the menu is visible. With "/open " typed, one Esc closes the whole popup. The draft survives the reopen, which is good [SS 22]. | Let the first Esc clear non-empty input and the second close. | XS | High |
| B13 | Nit | Visual polish | VERIFIED [SS] | `02-typed-slash.png`, `18b`, `17b` | Menu description columns don't line up. Inline `code` looks identical to body text. The emoji renders tiny. "thinking…" is static text with no motion over long waits. The menu squeezes the chat and cuts the last line mid-glyph (`21a`). | Fixed-width usage column, a code-span background, a subtle animated indicator. | XS–S | High |
| P1 | **High** | Packaging | VERIFIED [GH][CODE] | GitHub `contents/` lists `.github, .gitignore, HANDOFF.md, api, benchmark.py, evals, kokki, kokki_setup.py, main.py, pyproject.toml, tests` | **The QML plugin is not in the repo.** It exists only at `~/.config/omarchy/plugins/kokki/`. `tests/test_qml_logic.py:15` reads it from there and skips otherwise. A stranger gets a backend with no UI. | Add a `plugin/` directory, and an install step that symlinks or copies it. | S | High |
| P2 | **High** | Docs | VERIFIED [GH] | repo root; GitHub `license: null` | No README, no LICENSE (while `manifest.json` claims `"license": "MIT"`), no `.env.example`, no install or run instructions for strangers. | README (what it is, the safety model, install, run, plugin enable, config table), `LICENSE` (MIT), `.env.example`. | S | High |
| P3 | Medium | CI | VERIFIED [CODE][GH runs green] | `.github/workflows/ci.yml` | CI runs only `pytest tests/test_tools.py` (5 of 83 test functions). The fake-LLM offline suites (`test_stream_contract.py` with 19, `test_sessions.py` with 20, `test_sessions_api.py` with 13, `test_smoke.py` with 6) never run in CI, and `pytest-asyncio` isn't installed there. HANDOFF claims CI also runs `test_smoke`. | Run all offline suites with `pip install -e .[dev]`, and add a job with `qml6` for the plugin tests. | XS | High |
| P4 | Medium | Supervision / paths | VERIFIED [CODE][LOG] | `kokki/observability.py:9`, `kokki/memory.py:5`, `HANDOFF.md:195-205` | The server is started by hand (`uvicorn … --port 8000` from the repo directory). No systemd user unit, no restart story. `kokki.log` and `kokki_memory.sqlite` are relative to the working directory, and the log is not rotated. Test runs write into the real `kokki.log` (fake 2 ms "Ran it." entries for `bar-1` / `bar-9` at 15:52 in the author's log). The 429 log line includes the Groq org id. | Use XDG paths (`~/.local/state/kokki/`, `~/.local/share/kokki/`), a `RotatingFileHandler`, a shipped `kokki.service` user unit, and tests that log to tmp. | S | High |
| P5 | Medium | Dependencies | VERIFIED [CODE] | `pyproject.toml:10-20` | All dependencies are `>=` with no lockfile. `langgraph`, `groq` and `aiosqlite` are imported directly but only arrive transitively. | Declare the direct imports, and pin with an upper bound or a lock (`uv lock` / `pip-compile`). | XS | High |
| P6 | Low | Setup wizard | VERIFIED [CODE]; file mode INFERRED | `kokki_setup.py:5,97,113` | The docstring says `python setup.py` (the old name). It writes the plaintext API key to `./.env` with default permissions (usually 0644). It ends with "Run `python main.py`" (the CLI) and says nothing about the server or the plugin. It defaults to the profane personality with profanity on. | `os.open(..., 0o600)`, correct next steps, and consider a clean default for a community release. | XS | Medium |
| P7 | Low | Docs accuracy | VERIFIED [CODE] | `HANDOFF.md:115-124,168-182,77-81` | HANDOFF says Panel.qml is 117 lines with "no network code", and that Sections 2 and 3 are not started. The live file is 561 lines, with streaming, history and commands. It also says "21+ passing" (83 exist) and says CI runs `test_smoke` (it doesn't). Versions disagree: pyproject 0.1.0, manifest 0.3.0. | Refresh HANDOFF, and use one version source. | XS | High |

## 4. What I broke and what I could not break (experiment log)

| # | Action | Result | Evidence |
|---|---|---|---|
| 1 | Open popup (IPC) | Clean themed panel, accent border, input focused. Blank empty state. | [SS 01] |
| 2 | `wtype "/"` | Landed in the popup input; menu of 4 commands, first highlighted | [SS 02] |
| 3 | Type `h`, Down, Tab | Filter narrowed to /history, /help. Highlight moved. Tab completed to `/help ` and the menu closed | [SS 03-05] |
| 4 | Enter on `/help ` | Help note in dim italic, 4 commands | [SS 06] |
| 5 | `/hi` + Enter (menu pick) | History opened; 4 sessions with relative times | [SS 07] |
| 6 | `/open 9` while history shows | No visible feedback (**B8**) | [SS 08, 09] |
| 7 | `/foo`, `"   "`, `/HELP`, `/open`, `/new extra words` | `unknown`, `empty`, `help` (case-insensitive, good), `bad-number`, new id (args ignored) | IPC words |
| 8 | `/tmp what is in this folder` | Swallowed as unknown command (**B7**) | IPC `unknown`, [SS 12-t1] |
| 9 | `/usr/bin has what` (real request 1, unintended) | Went to the model. 19.5 s first LLM call, `ls -1 /usr/bin`, reply claims a "dump" that is never shown (**B1**) | [LOG][SS 12-t1, t14] |
| 10 | Greeting with a 76-char unbroken word (req 2) | Reply in under 0.9 s; the long word is clipped (**B6**) | [SS 13a, 13b] |
| 11 | "what is my default browser?" (req 3) | `xdg-settings get default-web-browser`, correct answer "Chromium", 2.2 s. Status shows the tool name (**B4**) | [SS 14a, 14b][LOG] |
| 12 | "do we have chrome?" (req 4) | `which google-chrome ‖ …`, correct "no", 2.5 s | [SS 15][LOG] |
| 13 | `/new`, "open files app" (req 5) | 25.3 s busy, 2 Nautilus windows, the first in the repo directory (**B2**). I closed both (my windows only) | [LOG][windows.txt][SS 16a-c] |
| 14 | "list the files in my home folder" + `/new` and `ask` while busy (req 6) | `/new` gave the note "Kokki is busy - wait for the reply first." and `ask` returned `busy` (good guarding). The reply lists nothing (**B1**) | [SS 17a, 17b][LOG] |
| 15 | Markdown list + table + `![img](…)` + link (req 7) | Visible streaming (partial at 1.46 s, full at 1.73 s). Bold, bullets and a bordered table render; the user's own text stays literal; the image is neutralised to a link (**safeMarkdown holds**). The link is low-contrast and not clickable (**B9**) | [SS 18a, 18b] |
| 16 | `/history`, `/open 4` | Restored conversation scrolled to the bottom | [SS 19, 20] |
| 17 | `/o` + Enter | Filled `/open ` (argument needed), good | [SS 21a, 21b] |
| 18 | Esc with `/open ` typed | Closed the whole popup (**B12**) | [SS 21c] |
| 19 | Reopen + type `2` | Focus back in the input, draft preserved | [SS 22] |
| 20 | "what time is it?", close popup at 0.3 s, reopen at 5 s (req 8) | **HTTP 429 (daily tokens)**. The error reply was delivered while the popup was closed and visible on reopen (closing mid-request is safe). Message misleading and green (**B3**). **Stopped all model requests here.** | [SS 23][LOG] |
| 21 | Final `/history` | 10 sessions (4 original + 6 mine); exactly 10, so "Show more" could not appear | [SS 24] |

**Could not break:** the busy guard (commands and asks during a reply are refused cleanly), Markdown image fetching (neutralised), user-text Markdown injection (shown literally), and closing the popup mid-stream (the reply is not lost). Draft and focus persistence across close and reopen also held.

## 5. Test-suite quality (my scope: CI versus what exists)

- The repo has 10 test files with 83 `def test` functions. CI runs **1 file, 5 tests** (`test_tools.py`) on Python 3.13, and is green on GitHub (last 5 runs `success`) [GH].
- Offline suites that could run in CI but don't: `test_stream_contract.py` (19), `test_sessions.py` (20), `test_sessions_api.py` (13), `test_smoke.py` (6), all fake-backed via `tests/fakes.py`.
- Plugin logic tests (`test_qml_logic.py`) need `qml6` and a plugin copy in `~/.config`, so they are unreproducible for anyone else.
- Coverage and mutation testing are Reviewer A's scope; I did not repeat them.

## 6. Runtime numbers (live, real Groq)

| Request | LLM call(s) | Tool | First visible text | Done |
|---|---|---|---|---|
| greeting (no tool) | 775 ms | none | between 0.51 and 0.89 s after send | about 0.9 s |
| default browser | 1,038 + 794 ms | `xdg-settings` (~5 ms) | status at 1.15 s, text by 2.18 s | about 2.2 s |
| chrome? | 1,976 + 642 ms | `which` | about 2.5 s | about 2.5 s |
| list home | 1,000 + 597 ms | `ls -A ~` | about 1.7 s | about 1.7 s |
| markdown | 1,581 ms (streamed) | none | partial at 1.46 s | 1.73 s |
| /usr/bin | **19,460** + 1,302 ms | `ls -1 /usr/bin` | about 21 s | about 21 s |
| open files | 1,908 + 1,555 + 1,062 ms | `xdg-open .` **20 s timeout**, then `xdg-open $HOME` | 25.28 s | 25.3 s; windows 3→4 at 3.18 s, 4→5 at 24.29 s |
| what time | 429 after 240 ms | none | error on reopen | n/a |

- Local actions (`/help`, the menu, `/new`) felt instant; history fetch and render took under 0.6 s. Frames were sampled every 0.2 to 0.3 s.
- Token baseline: 985 tokens requested for a minimal fresh-session call (from the 429 body). The daily cap is 200,000 tokens.
- The 19.5 s first call is unexplained (Groq queueing, or an SDK retry near the limit). It is INFERRED, and I could not reproduce it within budget.

## 7. Top 5 optimizations (by payoff)

1. **Surface tool calls and results in the chat, and tell the model the user can't see them** (fixes B1 and B4). Highest payoff: turns silent failures into answers and adds transparency. (measured symptom; fix estimated)
2. **Don't block on GUI launches, and run in `$HOME`** (B2): 25 s drops to about 2 s and duplicate windows go away. (measured 20 s timeout)
3. **Specific error messages plus quota handling** (B3, B5): the right advice, profanity respected, a real error colour, a lower token cost per call (reasoning effort, prompt size). (estimated savings)
4. **Ship-ability bundle** (P1 to P5): plugin in the repo, README, LICENSE, `.env.example`, a systemd user unit, XDG paths, CI running all offline suites, pinned dependencies. About a day of work, and it takes readiness from 2.5 toward 7/10.
5. **Rendering one-liners** (B6, B7, B8, B9): `Text.Wrap`, known-command-only parsing, a visible `/open` error in history, a themed and clickable link colour. Each is an XS change with a visible payoff.

## 8. Strengths (with evidence)

- **Native Omarchy look:** built on `qs.Commons` / `qs.Ui` (`KeyboardPanel`, `PanelSectionHeader`, `TextField`, `Button`), theme font (JetBrains Mono), accent border. Body text contrast is 13.6:1, and the dim captions measure 4.7 to 5.8:1 [SS, measured].
- **Command menu is genuinely good:** prefix filter, wrap-around highlight, Tab completes, Enter runs or fills the argument, case-insensitive [SS 02-05, 21a-b].
- **Fast plain chat** (0.9 to 2.7 s end to end), real visible streaming, and follow-the-bottom only when you are already at the bottom [SS 13, 18a].
- **Robust state handling:** busy guard, safe close and reopen mid-request, draft and focus kept, history and `/open` restore properly scrolled [SS 17a, 22, 23, 20].
- **Safe Markdown:** images neutralised, user text never rendered as Markdown [SS 18b].
- **Hygiene:** `.gitignore` covers `.env`, SQLite and the log; no secrets in the public repo [GH]; configuration comes from env vars, including the model name [CODE config.py].

## 9. Limits and confidence

- There were only 8 real requests, and the LLM is non-deterministic. B1 reproduced twice (two different informational requests) and B2 once. B2's mechanism, a pipe held open by the GUI child, is INFERRED from code; the 20 s and the second window are VERIFIED.
- Could not test safely: server down (the message code says "Can't reach the Kokki server. Is it running?", INFERRED), history "Show more" paging (exactly 10 sessions, page size 10), the Ollama backend, other themes (green error colour is theme-dependent), or link clicks.
- Request 1 was unintended: I expected `/usr/bin …` to be parsed locally. It was benign (`ls -1 /usr/bin`, read-only).
- The daily quota was shared with other use today, so B5 is not all attributable to this review.
- A stray "6" appeared in the popup input between my actions without me typing it. Possibly the user at the keyboard; I cleared it.
- The popup is left closed, on a fresh empty session id (`bar-1790680305541`, no messages), not the id it had before. Its prior id was unknown to me (the chat was empty).
- Windows: 3 at the start, 5 after the files test, 3 at the end. I closed only my two Nautilus windows (`0x57b971d46560`, `0x57b9712145a0`).

**Sessions I created (6):** `bar-1790679658137` ("/usr/bin has what"), `bar-1790679765504` (greeting, browser, chrome), `bar-1790679906409` ("open files app"), `bar-1790680018689` ("list the files…"), `bar-1790680067379` (markdown), `bar-1790680180517` ("what time is it?", failed, 1 msg). The original 4 are untouched.

## 10. Artifacts

- Report: `R/REVIEW-B.md`
- Screenshots (popup-only, `R/screens/`): `01-open-initial`, `02-typed-slash`, `03-filter-h`, `04-filter-h-down`, `05-tab-complete`, `06-help`, `07a-history-loading`, `07-history`, `08-open-bad-number-in-history`, `09-history-toggled-closed`, `10-edge-commands`, `11-path-message-swallowed`, `12-usrbin-t1…t14`, `13a-greeting-0.51s`, `13b-greeting-0.89s`, `14a-browser-status-running`, `14b-browser-answer`, `15-chrome-answer`, `16a-files-busy-12.8s`, `16b-files-answer`, `16c-files-after` (a system battery notification overlaps the popup), `17a-busy-probe`, `17b-home-list-answer`, `18a-markdown-streaming`, `18b-markdown-final`, `19-history-after`, `20-open-4-restored`, `21a-menu-open-filter`, `21b-enter-on-open-fills-arg`, `21c-esc-with-arg`, `22-reopen-focus`, `23-reopen-after-close-midrequest`, `24-history-final`, `25-final-before-close` (all `.png`)
- Frame sequences: `R/scratch/seq2` … `seq7` (plus `seq5/windows.txt`, the per-frame window list)
- Montages: `R/scratch/montage-*.png`
- Baselines: `R/scratch/threads-before.json`, `threads-after.json`, `windows-before.txt`, `windows-after.txt`, `geom.txt`
