# Build notes: home build of SPEC.md v1

## Run

```bash
python3 proxy.py --port 8041 --log traffic.jsonl
python3 dashboard.py --port 8050 --log traffic.jsonl     # open http://localhost:8050
ANTHROPIC_BASE_URL=http://localhost:8041 claude
```

Files: `proxy.py` (logging added), `dashboard.py` (server), `dashboard.html` (whole UI).
`traffic.jsonl` and `test*.jsonl` are in `.gitignore`.

## Acceptance checks (tested on live traffic, ports 8141/8150)

| Check | Result |
|-------|--------|
| A1 page loads, "● live", no console errors | pass |
| A2 row appears "in progress", reply grows while streaming | pass (text grew in 22 steps over 5 s) |
| A3 `Read(file_path=…proxy.py)`, "no result yet", next row `↩ Read result`, links jump and flash | pass |
| A4 `You: "read proxy.py…"`, no reminder shown as the prompt | pass |
| A5 second request: `+N msgs`, system/tools "unchanged since #…", same thread | pass after a fix (see below) |
| A6 six sections in order, system and tools collapsed with size/count | pass |
| A7 reading a missing file gives a red result card and a red dot on the row | pass |
| A8 `--upstream http://127.0.0.1:9` gives a red 502 row and the error count goes up | pass (sent with curl) |
| A9 `HEAD /api/hello` is a muted background row; the toggle hides it | pass |
| A10 tool filter `Read` leaves only rows with Read | pass |
| A11 reload page / restart `dashboard.py`: same rows, no duplicates | pass (11 ids in file, 11 rows) |
| A12 `grep -E 'sk-ant-[A-Za-z0-9_-]{20,}' traffic.jsonl` prints nothing | pass |
| A13 proxy terminal output unchanged | pass |
| A14 header token totals equal the sum of the rows | pass |
| A15 165 exchanges: opening a row 4–67 ms, search 63 ms | pass |
| A16 dark and light follow the system | pass |

## Choices where the spec was silent

- "in" tokens on rows and in the header = input + cache read + cache write (otherwise
  "in" is only a few tokens when caching is on). Cache read/write are also shown apart.
- "follow live": when the page is at the top, new rows appear there; when scrolled
  down, the view stays on what you read and a "N new ↑" pill appears.
- In the Reply section, each tool call shows its result under it. In a request's
  messages the result card already follows in the next turn, so it is not repeated.
- When more than one Claude session is in the log, thread tags get a session prefix
  (`98e3/T1`).
- Background rows still show their errors (the 502 in A8 is a background request,
  because a request without tools is background under U5).

## Findings in the traffic (not in the spec, worth adding in the lab)

- **`role: "system"` messages in the middle of the conversation.** Besides the
  top-level `system` field, Claude Code sends system messages inside `messages`
  (environment info, "tools just became available").
- **The same message changes shape between requests.** A message sent as a block list
  with `cache_control` in one request comes back as a plain string in the next. The
  thread rule (U8) failed until messages were normalized (string → one text block,
  `cache_control` removed). The spec should say this.
- **`tool_addition` blocks**: new tools are announced inside a system message
  (`{type: "tool_addition", tool: {definition: {name, …}}}`), not only in `tools`.
- `claude -p` used `claude-haiku-5-5` here; thinking blocks arrive with empty text
  (only a signature), so they show as "thinking (0 chars)".
- Every `claude` start sends `HEAD /api/hello` before the first message.

## Suggested spec changes for the next iteration

1. Section 2/6.3: normalize messages before comparing (string vs block list), and
   handle `role: "system"` messages and `tool_addition` blocks (6.6 table).
2. 6.6: say where the result appears when the call and result are in the same view.
3. 6.9: define what "in" tokens mean (with or without cache).
4. Background rule (U5): decide whether errors in background requests count in the
   header error count (they do now).
5. Markdown tables in model replies are shown as plain text; decide if they matter.

## Build 2: dashboard.html updated to SPEC.md v3

Changes in `dashboard.html` only (proxy and server untouched):

- U38/U5: suggestion requests (`[SUGGESTION MODE…` in the last user message) are background, with a
  gray **suggestion** badge and the preview `suggestion request`. They still join threads (`threaded`
  vs `main` in the code).
- U42: user-role text in a background request is an **Auto** block / `Auto: "…"` preview, never **You**.
- U43: **You** bubbles right, **Model** left (max 85%); cards, Auto, reminders, system messages full width.
- U44: "user traffic only" toggle plus an "N hidden" count.
- U30: text blocks show their first 80 characters with a ▸/▾ chevron; a search match opens a block on its own.
- U45: empty exchanges (e.g. `HEAD /api/hello` 404) are a single header line; background rows show method + path there.
- U22: "errors" counts main requests only; new "bg errors" count for background requests.
- U40/U41: tooltips on every badge and header item, and a **?** legend panel (Esc closes).
- 6.6: `role: "system"` messages are a gray **System message**; `tool_addition` blocks are `+ tool: <name>` chips.

Choices where the spec was silent:

- Text already inside a collapsed container (reminders, system message, thinking, tool descriptions, raw)
  skips the 80-character step but keeps the 15-line cut.
- "Typed prompt" for U44 = the last user message of the new messages has non-reminder text.
- Tested by replaying a real `traffic.jsonl` (123 records, 9 requests) in headless Chrome: no console errors.
  Not run: A8 and the long-session checks (A15) on the new build.

## Build 3: dashboard.html updated to the newer SPEC.md v3

- U38: known automated requests come from one list in the code (`AUTO_KINDS`): `[SUGGESTION MODE` (label
  **suggestion**) and `The user stepped away and is coming back.` (label **recap**). Both are background rows
  with their own preview text. The last user message's first non-reminder text is what gets matched.
- **Prompt** / **side request** (new tooltips): a main request with a prompt starts as `Prompt` (shown as
  `Prompt: "…"`). It becomes **You** when a later request in the session has it in its history, and **Auto**
  (badge `side request`) when a later request continues from the same parent without it.
- Choices where the spec was silent: if a later request rewrote the message but still contains the typed
  text (seen with a safety-classifier retry), the prompt counts as typed (You). A prompt that starts a
  thread stays `Prompt` until a later request confirms it. "User traffic only" shows `You:` rows only, so a
  still-pending `Prompt` row is hidden until it resolves.
- The `?` legend lists the new badges. Replayed the real log (11 requests) in headless Chrome: no console
  errors; recap shows as a muted `recap` row, typed prompts end as You. A27 not checked on live idle recap.

## Build 4: pending prompt is an orange "Auto"

- The word **Prompt** is gone: a prompt not yet known to be typed now reads **Auto**, in orange (`--pend`),
  in the row preview, the badge, and the block label, so it no longer looks like the blue **You**.
  When it resolves it turns into blue **You** or gray **Auto** (side request).
- The `?` legend has a new "Auto (orange)" entry. The note at the end of SPEC.md was a to-do for the spec
  itself; only its behavior (orange, word Auto) was built.
