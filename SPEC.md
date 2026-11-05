# SPEC: Live Traffic Dashboard for the Agent Proxy

Status: **v3, ready to build.** v3 adds an **Auto** label for prompts Claude Code
writes itself, chat alignment, a "user traffic only" toggle, short collapsible
blocks, and thin rows for empty exchanges. v2 added what build 1 showed on live
traffic: suggestion requests, background errors, message normalization, badge help,
and system messages inside the conversation. Decisions are in section 9. Priorities:
**[M]** must be in the first build, **[S]** should, **[C]** could (later iterations).

## 1. Purpose

`proxy.py` prints every request Claude Code sends to the Anthropic API and every
streamed reply. That output is raw JSON and raw SSE text, tens of thousands of lines
per minute, and impossible to follow. This dashboard shows the same traffic in a
browser page that updates live and makes the conversation easy to read.

The main goal is **readability**. At a glance, a reader must tell apart:

- **their own prompt** (what they typed),
- **the model's reply text**,
- **a tool call** the model asked for,
- **the result** of that tool call,

and must be able to follow the conversation as it grows, request after request.

## 2. What we know about the traffic (observed through the proxy)

- Claude Code sends `POST /v1/messages?beta=true` with `stream: true`. It also sends
  other calls, for example `HEAD /api/hello` at startup and small calls without tools.
- Every request carries the **whole** conversation again: `system`, `tools`, and all
  `messages`. A request body is often 100 KB or more. The system prompt alone is
  thousands of characters and the tool list has dozens of tools.
- Each request has the header `X-Claude-Code-Session-Id`, which is the same for every
  request from one `claude` session.
- A tool call (`tool_use`) appears in a **reply**. Claude Code runs the tool locally
  and sends the result (`tool_result`) in the **next request**, inside a `user` message.
- `user` messages also hold text that the user did not type: blocks that start with
  `<system-reminder>`. These are not the user's prompt.
- Claude Code moves `cache_control` markers between messages from one request to the
  next, so an older message can differ only in that field.
- The `authorization` header holds a subscription token (`Bearer sk-ant-oat...`).
- **The same message changes shape between requests.** Message content can be a plain
  string in one request and a list of blocks (with `cache_control`) in the next.
  Comparing messages as they arrive fails, so every request looks like a new thread.
- **`role: "system"` messages appear inside `messages`**, between user and assistant
  turns, besides the top-level `system` field. They carry environment info and
  `tool_addition` blocks of the form
  `{"type": "tool_addition", "tool": {"type": "tool_definition", "definition": {"name": "Read", ...}}}`.
- **Suggestion requests.** After the model answers, Claude Code sends a request (with
  tools, in the same thread) whose last user message starts with
  `[SUGGESTION MODE: Suggest what the user might naturally type next`. It fills the
  gray hint in the input box. The user did not type it.
- At startup Claude Code sends a small request whose only message is `quota` (no
  tools). It can get `429 rate_limit_error` while everything the user does still works.
- 

## 3. Components and files

```
proxy.py          existing proxy + JSONL logging (section 4)
dashboard.py      new: serves the page and streams the log to it (section 5)
dashboard.html    new: the whole UI, inline CSS and JS, no build step (section 6)
traffic.jsonl     created at runtime; listed in .gitignore (it contains prompts)
```

Python standard library only, Python 3.10+. No npm, no CDN, no external files.

How to run (3 terminals):

```bash
python3 proxy.py --port 8041 --log traffic.jsonl
python3 dashboard.py --port 8050 --log traffic.jsonl     # open http://localhost:8050
ANTHROPIC_BASE_URL=http://localhost:8041 claude
```

## 4. proxy.py changes (logging)

- P1 [M] New flag `--log PATH` (default `traffic.jsonl`). The proxy **appends** to it.
- P2 [M] Forwarding is unchanged: same headers, same bytes, same streaming. The
  terminal output is unchanged, line for line.
- P3 [M] Logging can never break the proxy: every log write is inside `try/except`,
  and a failure prints one warning line and goes on.
- P4 [M] One JSON object per line. A single `threading.Lock` guards writes; each line
  is flushed right away. Every record has `t` (type), `id`, and `ts` (epoch seconds,
  float).
- P5 [M] `id` is `"<run>-<n>"`: `run` is the proxy start time (`HHMMSS`), `n` counts
  requests from 1. Unique across restarts.
- P6 [M] Record types, written in this order for each request:

| `t`     | When                          | Extra fields                                                       |
|---------|-------------------------------|--------------------------------------------------------------------|
| `req`   | request body fully read       | `method`, `path`, `headers` (object), `body` (parsed JSON, or `null`), `body_text` (only if not JSON) |
| `resp`  | upstream status received      | `status`, `reason`, `headers`                                      |
| `chunk` | each chunk forwarded          | `text` (decoded with an incremental UTF-8 decoder, so a character split across chunks is not broken) |
| `end`   | reply finished                | `bytes` (total)                                                    |
| `err`   | any failure (cannot connect, timeout, client gone) | `message`. The proxy's own 502 is logged as `resp` + `err` + `end`. |

- P7 [M] **Secrets.** In logged headers, `authorization`, `x-api-key`, and `cookie`
  keep only their first 16 characters plus `...`, the same rule the terminal uses.
  The full value never reaches the file.
- P8 [M] An `end` record is always written, also after an error (use `finally`).

## 5. dashboard.py

- S1 [M] `python3 dashboard.py [--port 8050] [--log traffic.jsonl]`. Binds to
  `127.0.0.1` only. Starts fine when the log file does not exist yet.
- S2 [M] `GET /` returns `dashboard.html` (read from the same folder as `dashboard.py`).
- S3 [M] `GET /events` is a Server-Sent Events stream. It first sends every line
  already in the file, then tails the file (check every 200 ms) and sends each new line.
  Each SSE message is `id: <line number>` + `data: <the JSONL line, unchanged>`.
- S4 [M] Reconnect without duplicates: when the browser reconnects with
  `Last-Event-ID`, the server resumes after that line.
- S5 [M] If the file gets shorter (deleted or truncated), the server sends
  `event: reset` and starts again from line 1. The page clears its view on `reset`.
- S6 [M] A comment line (`: ping`) every 15 s keeps the connection open. A browser
  that disconnects ends its handler without a traceback.
- S7 [M] A partial last line (the proxy is in the middle of writing it) is held back
  until its newline arrives.
- S8 [M] The server does not parse traffic. All parsing is in the page (section 6), so
  live data and reloaded history go through the same code.

## 6. dashboard.html: the UI

### 6.1 Parsing (in the browser)

- U1 [M] Group records by `id` into one **exchange**: request + reply.
- U2 [M] Streaming replies (`content-type: text/event-stream`): join the `chunk` texts,
  split into SSE events on blank lines, and keep an unfinished tail for the next chunk.
  Handle `message_start` (id, model, usage), `content_block_start`,
  `content_block_delta` (`text_delta`, `input_json_delta`, `thinking_delta`; ignore
  `signature_delta`), `content_block_stop` (parse the joined tool input JSON; if it
  fails, show the raw string with a warning), `message_delta` (`stop_reason`, usage),
  `message_stop`, `ping`, `error`.
- U3 [M] Non-streamed replies: parse the joined text as JSON at `end`. If it is not
  JSON, show it as plain text.
- U4 [M] Unknown event types and block types are shown as raw JSON, never dropped.

### 6.2 Kinds of requests

- U5 [M] A request is **main** when it is `POST`, its path starts with `/v1/messages`
  (but not `/v1/messages/count_tokens`), its body has a non-empty `tools` list, and it
  is not a known automated request (U38). Everything else is **background**.
- U38 [M] **Known automated request**: the first text block of the last `user`
  message that is not a `<system-reminder>` (after normalization, U39) starts with
  one of the prefixes below. It is background, its row has the gray label from the
  table, and its `→` preview is the preview text from the table, never `You: "…"`.
  It still takes part in threads (U8) like any other request. The prefixes live in
  one list in the code.

| Prefix                                      | Label          | `→` preview          |
|---------------------------------------------|----------------|----------------------|
| `[SUGGESTION MODE`                          | **suggestion** | `suggestion request` |
| `The user stepped away and is coming back.` | **recap**      | `recap request`      |
- U42 [M] **Automated prompt**: user-role text in a background request, for example
  a suggestion request (U38), a thread-title request, or the startup `quota` request.
  Claude Code wrote it, not the user. It is labeled **Auto**, never **You**, in
  previews and in sections. Its `→` preview is `Auto: "…"`; suggestion requests keep
  `suggestion request`.
- U6 [M] Background requests are shown by default, in a smaller, muted row. A toggle in
  the header hides them and shows "N background hidden".


### 6.3 Sessions and threads

- U7 [M] **Session** = value of `X-Claude-Code-Session-Id` (missing: "no session").
- U8 [M] **Thread** = a chain of requests in one session where each request's
  `messages` starts with the previous one's `messages`. **Normalize before comparing**
  (U39). The parent of a new request is the latest request in
  the same session whose messages are a prefix of its messages.
- U9 [M] If no parent is found, the request starts a **new thread** (a subagent, a
  compaction, or a new conversation). It gets the badge "new thread". Threads are
  named `T1`, `T2`, ... per session, and the name shows on every row.
- U10 [M] **New messages** of a request = its messages after the parent's messages.
  For the first request of a thread, all of them.
- U39 [M] **Normalization**, used for every comparison and every display decision: a
  message's content that is a string becomes one block `{"type": "text", "text": …}`;
  then every `cache_control` field is removed (at any depth). Compare messages by
  `role` + normalized content (for example as canonical JSON strings).

### 6.4 Page layout

```
┌ Header ────────────────────────────────────────────────────────────────────┐
│ ● live   42 requests (8 bg)   in 310k  out 9k  cache r 280k w 30k      [?] │
│ errors 1   tools: Read 6 · Bash 3 · Edit 2   [search ] [tool▾] [model▾]     │
│ [errors only] [hide background] [user traffic only] [follow live] [theme]  │
├ Feed (newest first) ───────────────────────────────────────────────────────┤
│ 13:54:43  #12  T1  opus-5-5  200  3.1s  in 31k / out 120   [tool_use]      │
│   → ↩ Read result (34 lines)                                               │
│   ← Read(file_path="…/proxy.py")                         +2 msgs           │
│ 13:54:40  #11  T1  opus-5-5  200  2.4s  …                  [end_turn]      │
│   → You: "read proxy.py and tell me what it does"                          │
│   ← Model: "It is a reverse proxy that …"                                  │
│ 13:54:38  #10  HEAD /api/hello  404  0.1s  bg                              │
└────────────────────────────────────────────────────────────────────────────┘
```

- U11 [M] One row per exchange, newest on top. Collapsed row shows: time, sequence
  number, thread, short model name, status, duration, input/output tokens,
  `stop_reason` badge, change markers (6.7), and **two preview lines**:
  - `→` what is new in the request: the user's prompt (`You: "…"`), an automated
    prompt (`Auto: "…"`, U42), or tool results (`↩ Read result (34 lines)`), never a
    system-reminder;
  - `←` the reply: first line of model text, or the tool calls (`Read(file_path=…)`).
- U12 [M] A request still waiting shows a spinner and "in progress"; the `←` line
  and the open reply fill in while the reply streams.
- U45 [M] **Empty rows stay thin.** When an exchange has no request messages and no
  model text or tool calls in the reply (for example a 404 to `HEAD /api/hello`), the
  row shows only its header line, with no `→`/`←` lines. Error marking (U19) still
  applies. Expanded, its empty sections are left out; **Raw** is always shown.
- U13 [M] Click a row to expand it. Expanding never moves the scroll position and
  never closes other rows. Expanded rows stay expanded when new rows arrive.
- U14 [M] New rows do not push the view down while the user reads: if the page is
  scrolled away from the top, show a "N new ↑" pill instead; clicking it goes to the
  top. "follow live" (on by default) keeps the newest row in view.
- U40 [M] **Every badge explains itself.** Each badge and header item has a tooltip
  (`title`) in plain words, for example: `T1` "thread 1: one conversation; a new
  thread is a subagent, compaction or new chat", `+2 msgs` "2 messages added since
  the previous request in this thread", `end_turn` "the model finished its answer",
  `tool_use` "the model stopped to ask for a tool", `cache r` "input tokens read from
  the prompt cache", `bg` "sent by Claude Code itself, not by you", `Auto` "text
  Claude Code wrote itself, not you", `user traffic only` "show only requests that
  carry a prompt you typed".
- `Prompt` "not known yet whether you typed this; it turns into You or Auto when the
next request arrives", `side request` "a one-off prompt Claude Code sent itself;
the conversation went on without it"
- U41 [M] A **?** button in the header opens a small legend panel: the five colors
  (You, Auto, Model, tool call, tool result), every badge with its meaning (same text
  as U40), and what `→` and `←` mean. Esc or a second click closes it.

### 6.5 Expanded exchange: sections, in this order

1. **New in this request** [M]: open. The new messages (U10), highlighted.
2. **Reply** [M]: open. Model text, thinking, tool calls; `stop_reason` and usage.
3. **Conversation so far** [M]: collapsed. Earlier messages; when opened, only the
   last 6 are shown with "show all N".
4. **System instructions** [M]: collapsed. Shows its size (characters) and
   "unchanged since #n" or "changed". Opened, it shows the full text, never cut.
5. **Tools (N)** [M]: collapsed. Opened, tool names as chips; click a chip to see
   its description and input schema (formatted JSON). "unchanged" / "+added −removed".
6. **Raw** [M]: collapsed. Request headers, request body JSON, and the reply as a
   list of SSE events, each as formatted JSON.

### 6.6 Blocks: one look per kind

| Block                         | Look                                                         |
|-------------------------------|--------------------------------------------------------------|
| User prompt (typed text)      | Blue bubble, label **You**, aligned right                    |
| Automated prompt (U42)        | Gray background, muted text, label **Auto**, full width      |
| `<system-reminder>` text      | Gray, dashed border, label **reminder**, collapsed to one line |
| Model text                    | Neutral bubble, label **Model**, aligned left, basic markdown |
| `thinking`                    | Muted italic, label **thinking**, collapsed                  |
| `tool_use`                    | Amber card: `ToolName` + short summary + input JSON          |
| `tool_result`                 | Green card, red when `is_error`; shows the tool name of its call |
| `role: "system"` message      | Gray bubble, label **System message**, collapsed to its first line; never labeled **You**, **Auto** or **Model** |
| `tool_addition` block         | One small chip `+ tool: <name>` (name from `tool.definition.name`); full JSON when clicked |
| Image / document              | Gray placeholder with type and size                          |
| Unknown                       | Raw JSON                                                     |

- U15 [M] Short summary for common tools: `Read`/`Write`/`Edit` show the file path,
  `Bash` shows the command, `Grep`/`Glob` show the pattern. Other tools: the first
  input field. The full input is always below the summary.
- U16 [M] The five main kinds (prompt, automated prompt, model text, tool call, tool
  result) use the same color and label everywhere: in previews, in sections, in the
  header. Automated prompts and background rows are grayed so typed prompts stand out.
- U43 [M] **Chat alignment.** **You** bubbles sit on the right and **Model** bubbles
  on the left, each at most 85% of the width. Tool cards, **Auto**, reminders, and
  system messages use the full width. Collapsed-row previews are not aligned. U36
  still holds.

### 6.7 Tool pairing and changes

- U17 [M] Match `tool_use.id` with `tool_result.tool_use_id` across all exchanges.
  Each call is shown **beside its result**: once the result arrives, the call card
  shows it right under the call (first 15 lines, "show more"), with
  "↳ result in #13"; until then, a **no result yet** badge. The result
  card shows "↖ call from #12" (or an **orphan result** badge). Clicking either one
  scrolls to the other, expands its row, and flashes it.
- U18 [M] Change markers on each row, compared with its parent: `+N msgs`,
  `system changed`, `tools changed`, `new thread`. Markers only, no diff text.

### 6.8 Errors

- U19 [M] An exchange is an error when: status is not 2xx, the stream has an `error`
  event, there is an `err` record, or the reply ended without `message_stop`.
  Error rows have a red left border and a red badge with a short reason.
- U20 [M] A `tool_result` with `is_error: true` is a red card, and its row gets a
  small red dot (the exchange itself is not counted as an error).
- U21 [S] `stop_reason: max_tokens` gets a yellow warning badge.
- U22 [M] The header shows two counts: **errors** (main requests only, red) and
  **bg errors** (background requests, gray). Clicking either turns on "errors only".
  A background error row is still marked red in the feed, but it never raises the red
  count. Example: the startup `quota` request getting 429 adds to "bg errors" only.

### 6.9 Stats

- U23 [M] Per exchange: input, output, cache read, cache write tokens (from
  `message_start` and `message_delta` usage) and duration (`req` to `end`).
- U24 [M] Header totals: requests (with background count), the four token totals,
  error count, and tool calls by name. A tool chip in the header sets the tool filter.
- U25 Tokens only, no cost.

### 6.10 Filters and search

- U26 [M] Tool filter: show only exchanges with a call or result of that tool.
- U27 [M] Model filter, "errors only", "hide background", "user traffic only".
  Filters combine (AND).
- U44 [M] **User traffic only** toggle, next to "hide background": shows only main
  exchanges whose new messages (U10) contain a typed prompt, that is, rows whose `→`
  line is `You: "…"`. It hides all background requests and the tool-loop requests
  that only carry tool results. The header shows "N hidden" while it is on.
- U28 [M] Search box: case-insensitive, over prompts, model text, tool inputs, and
  tool results (not system or tool definitions). Non-matching rows hide; matches are
  highlighted in opened sections.
- U29 [S] Keyboard: `/` focuses search, `j`/`k` move between rows, `Enter` expands.

### 6.11 Formatting

- U30 [M] Every text block (prompt, Auto, model text, tool input, tool result) shows
  only its first 80 characters, with a chevron (▸/▾) to expand or collapse the full
  text. Blocks the 6.6 table already collapses keep their own rule. An expanded block
  longer than 15 lines is cut with "show more (N lines)". A block with a search match
  (U28) opens on its own. The copy button (U34) always copies the full text.
- U31 [M] JSON is indented, colored (keys, strings, numbers), and each object/array
  can fold. Long strings in JSON are cut with "show more".
- U32 [M] Monospace for code, tool input, tool output, JSON. Proportional font for
  prose.
- U33 [M] Basic markdown in model text, by a small hand-written renderer: headings,
  bold, italic, inline code, code blocks, lists, links. All text is HTML-escaped first;
  the page never inserts traffic text as HTML.
- U34 [M] Every block has a copy button (copies its full text or JSON).
- U35 [M] Light and dark themes; default follows the system; the toggle overrides.
- U36 [M] Works at 1280 px wide with no horizontal scroll of the page. Long lines wrap.

### 6.12 Performance

- U37 [M] Sections of a row are built only when first opened, not before. With 300
  exchanges the page stays smooth, and opening a row takes under 200 ms.

## 7. Non-goals

- Editing, replaying, or blocking requests. The proxy stays read-only.
- Cost in dollars. Multi-user access. Any access from other machines.
- Hiding secrets other than the auth headers (P7).

## 8. Acceptance checks

Run section 3's three commands. Then, in the Claude terminal:

- A1 [M] The page at `http://localhost:8050` loads and shows "● live". No console errors.
- A2 [M] Send `read proxy.py and tell me in one sentence what it does`. Within 2 s a
  row appears with "in progress", and the reply text grows while it streams.
- A3 [M] That row's `←` line shows `Read(file_path=…proxy.py)` and its call card has
  "no result yet". The next row's `→` line shows `↩ Read result`. Both cards are
  linked: clicking one scrolls to and flashes the other.
- A4 [M] The row with the typed prompt shows `You: "read proxy.py…"`; no row shows a
  system-reminder as the user's prompt.
- A5 [M] The second request of the thread shows `+2 msgs`, "system unchanged since #…",
  "tools unchanged", and the same thread name.
- A6 [M] An expanded row shows the 6 sections in the order of 6.5. System and Tools
  are collapsed and show size / count.
- A7 [M] Ask Claude to read `does-not-exist.txt`: the tool result is a red card.
- A8 [M] Stop the proxy and restart it with `--upstream http://127.0.0.1:9`, send a
  prompt: a red 502 row appears and the header error count goes up.
- A9 [M] `HEAD /api/hello` appears as a muted background row; "hide background" hides it.
- A10 [M] Choosing `Read` in the tool filter leaves only rows with Read calls/results.
- A11 [M] Reload the page and restart `dashboard.py`: the same rows come back, with no
  duplicates.
- A12 [M] This prints nothing (no full token in the log):
  `grep -E 'sk-ant-[A-Za-z0-9_-]{20,}' traffic.jsonl`
- A13 [M] The proxy terminal prints the same lines as before the change.
- A14 [M] The header token totals equal the sum of the rows.
- A15 [M] After 100+ exchanges, scrolling is smooth and a row opens in under 200 ms.
- A16 [M] Switching the system to dark mode switches the page.
- A17 [M] After the model answers, the `[SUGGESTION MODE…` request appears as a muted
  row labeled **suggestion**; no row shows it as `You:`. "hide background" hides it.
- A18 [M] Start `claude` fresh. If the `quota` request gets 429, "bg errors" goes up
  and the red "errors" count stays 0.
- A19 [M] Send two prompts in one session: the second prompt's requests are in the
  same thread (`T1`), with no "new thread" badge, although Claude Code changed the
  shape of earlier messages between requests.
- A20 [M] Hovering `T1`, `+N msgs`, `end_turn`, `tool_use`, and `bg` shows a tooltip;
  the **?** button opens the legend and Esc closes it.
- A21 [M] In "New in this request" of the first main request, the environment message
  is a gray **System message** (not **You**), and its `tool_addition` blocks show as
  `+ tool: <name>` chips.
- A22 [M] The suggestion request and any thread-title request show their text as a
  gray **Auto** block; no row or section shows it as **You**.
- A23 [M] In an expanded exchange, **You** bubbles are on the right and **Model**
  bubbles on the left; tool cards use the full width.
- A24 [M] "User traffic only" leaves only rows whose `→` line is `You: "…"`; the
  `HEAD /api/hello` row, suggestion rows, and tool-result rows are hidden.
- A25 [M] A long model reply shows its first 80 characters and a chevron; clicking
  the chevron shows the full text.
- A26 [M] The `HEAD /api/hello` 404 row is a single header line with no `→`/`←` lines.
- A27 [M] No row ever shows Claude Code's own prompt as **You**. Check with a
  suggestion request, a recap request (leave the session idle until Claude Code
  shows a recap), and the thread-title request: each ends up as a gray **Auto**
  block. Every prompt you typed ends up as **You** within a few seconds of its reply.

## 9. Decisions

| ID  | Topic              | Decision                                                                  |
|-----|--------------------|---------------------------------------------------------------------------|
| D1  | Data source        | `proxy.py` appends records to a JSONL file: `req`, `resp`, each `chunk`, `end`, `err` (section 4). Terminal output unchanged. |
| D2  | Architecture       | A separate `dashboard.py` tails the file and serves the page.             |
| D3  | Live updates       | Server-Sent Events, with `Last-Event-ID` resume.                          |
| D4  | Streaming          | Reply text fills in while it streams (needs the per-chunk records of D1). |
| D5  | Changes view       | Markers only (6.7), no diff text.                                         |
| D6  | Cost               | Tokens only.                                                              |
| D7  | Requests shown     | Everything; background requests muted, with a toggle to hide them.       |
| D8  | Markdown           | Small hand-written renderer, text escaped first.                          |
| D9  | First-version scope | Everything marked [M].                                                    |
| D10 | Unpaired items     | "no result yet" and "orphan result" badges; nothing hidden.               |
| D11 | Tech stack         | One HTML file with inline CSS/JS; Python standard library only.           |
| D12 | Conversations      | Session = `X-Claude-Code-Session-Id`; thread = message-prefix chain (6.3). |
| D13 | Background rule    | Main = POST to `/v1/messages` with tools, not a suggestion request; everything else background. |
| D14 | Parsing location   | In the browser only, so live and reloaded data use the same code.        |
| D15 | Persistence        | The log is appended across restarts; deleting it resets the view (S5).    |
| D16 | Section order      | New messages and reply first; system and tools collapsed below.          |
| D17 | Suggestion requests | Background with a **suggestion** label (U38), because the user did not type them. |
| D18 | Background errors  | Counted apart as "bg errors" (U22), so a failed startup probe does not look like a broken session. |
| D19 | Normalization      | String content → one text block, `cache_control` removed, before any comparison (U39). |
| D20 | Badge help         | Tooltips on every badge plus a **?** legend (U40, U41); build 1 showed that the badges alone were not understood. |
| D21 | Automated prompts  | Labeled **Auto**, grayed, never **You** (U42). Not "System", which already names system messages and system instructions. |
| D22 | Chat alignment     | You right, Model left; cards and Auto full width (U43).                   |
| D23 | User traffic only  | Shows only exchanges with a typed prompt, so it does more than "hide background" (U44). |
| D24 | Block length       | 80 characters by default with a chevron; the 15-line cut applies once expanded (U30). |
| D25 | Empty rows         | Header line only, no previews (U45).                                      |

## 10. Instructions for the agent that builds this

- Build exactly what is marked [M]. Add [S] items only if all [M] items work.
- Do not ask questions. Where this spec is silent, choose the simplest option and
  write it down in `BUILD_NOTES.md` (one line each), together with the run commands.
- Do not add dependencies or change how the proxy forwards traffic.
- Add `traffic.jsonl` to `.gitignore`.
- Test it yourself before you finish. Use other ports so you do not clash with a proxy
  that is already running, for example:
  `python3 proxy.py --port 8141 --log test.jsonl`,
  `python3 dashboard.py --port 8150 --log test.jsonl`,
  `ANTHROPIC_BASE_URL=http://localhost:8141 claude -p "read proxy.py and summarize it"`.
    Then check the parsed result against acceptance checks A2–A6, A12, A14, A17,
  A19, A21, A22, A24, and A26, and
  report which checks pass and which you could not check.
