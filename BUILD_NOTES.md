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
