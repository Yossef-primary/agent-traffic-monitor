# Build notes

## Run (3 terminals)

```bash
python3 proxy.py --port 8041 --log traffic.jsonl
python3 dashboard.py --port 8050 --log traffic.jsonl     # open http://localhost:8050
ANTHROPIC_BASE_URL=http://localhost:8041 claude
```

## Choices where the spec is silent (one line each)

- proxy: the log file is opened in append mode for every record (simple, survives the file being deleted while running).
- proxy: an exception after the request (timeout, client gone) logs `err`, then is re-raised so the terminal shows exactly what the original proxy showed.
- proxy: `end.bytes` counts bytes forwarded from upstream; the proxy's own 502 page is not counted.
- proxy: a request body that is not JSON is logged as `body: null` + `body_text`.
- dashboard.py: if the browser resumes with a `Last-Event-ID` larger than the file's line count, the server sends `event: reset` and replays from line 1.
- dashboard.py: blank lines in the log still count as line numbers (ids stay equal to file line numbers) but are not sent.
- page: `#n` is the order of arrival in the log, not the number inside the record id.
- page: threads are named per session, so two sessions both have a `T1`; the thread tooltip shows the session id prefix.
- page: requests without `messages` (e.g. `HEAD /api/hello`) have no thread and no change markers.
- page: a request whose messages equal its parent's shows `+0 msgs`.
- page: in background rows the user text is shown as `sent: "…"` (gray), never `You:`, because Claude Code wrote it.
- page: user text blocks are split at `<system-reminder>…</system-reminder>`; reminder parts are gray, the rest is the typed prompt.
- page: a tool call or result is registered in the first request where it is a *new* message; that request is the target of the "↖ call from" / "↳ result in" links.
- page: row `in` is `input_tokens` only; cache read / write are shown separately (`cr`, `cw`), header totals are the plain sums of the rows.
- page: an exchange whose log ends with `end` but no `resp` is an error "no response".
- page: "errors only" shows main and background errors; the red count only counts main ones.
- page: "follow live" on = while you are at the top the newest row stays in view; off = the view never moves by itself (the "N new ↑" pill counts new rows).
- page: theme button cycles auto → light → dark; the choice is kept in localStorage (auto = follow the system).
- page: Raw request body JSON opens two levels deep; deeper objects are folded and built only when opened.
- page: JSON strings longer than 300 characters are cut with "show more".
- page: an empty `thinking` block (display omitted by the API) shows "empty".
- page: markdown supports headings, bold, italic, inline code, fenced code, lists and http(s) links; no tables.
- page: rendering is batched per animation frame, with a 150 ms timer fallback for hidden or throttled tabs.
- page: keyboard [S] `/`, `j`, `k`, `Enter` and the yellow `max_tokens` badge [S] are included.

### v3 (updated in place, not rebuilt)

- v3 changes are all in `dashboard.html`; `proxy.py` and `dashboard.py` are unchanged.
- U42: a session gets its `S#` from its first request carrying `X-Claude-Code-Session-Id`, including background ones.
- U42: the session strip is a 6 px inset stripe inside the row, so the red error left border (U19) still shows next to it.
- U42: the session select's prompt is the first typed prompt of a main, non-subagent request in that session; "(no prompt)" until there is one.
- U43 vs U38: the suggestion row's `→` keeps U38's wording `suggestion request` (A17); the row badge reads `suggestion`.
- U43: the `→` label applies to every background row; inside the expanded row the text is still shown, labeled "sent by Claude Code".
- U43: title/summary replies are parsed as JSON after stripping a ```json fence; other fields are shown only if `title` / `state`+`detail` are missing.
- U44: the subagent tag is the thread tag `S7·T2` plus a separate `subagent` badge next to it.
- U44: the prompt match is exact after trimming; the first user text is the typed text (system-reminder blocks removed).
- U44: later rows of a subagent thread inherit the tag and indent from their parent request.
- U45: "🔔 subagent finished" when a `<tool-use-id>` inside the notification is an `Agent`/`Task` call; otherwise the `<summary>` text, or the first line that is not a marker.
- U45: text holding `[SYSTEM NOTIFICATION` or `<task-notification>` is never the typed prompt; it shows as a gray "🔔 notification" block.
- U45: new messages that are not a prompt, result, notification or system message read `no new user input`.
- U46: if a row has both a real tool error and a permission denial, the red dot wins.
- U47: the injection badge is counted per row (`⚠ N` = rows), only for results that are new in that request.
- U47: phrases are marked in the visible part of a result; text behind "show more" is not marked after expanding.
- U48: sections split at `#`/`##` lines outside code fences; `###` stays inside its section.
- U48: the Intro category check ("Refuse" / "IMPORTANT") is case-sensitive, as written; heading categories are case-insensitive substrings.
- U48: "changed"/"new" compare sections with the same block number and title (nth occurrence) in the parent request; a first-in-thread request has no badges.
- U48: section cards render markdown and are never cut; a block with 3 or fewer sections opens them all.

### v4 (updated in place, not rebuilt)

- The Conversation view is a second renderer over the same parsed exchanges (U54); it adds no parsing.
- U49: the hash is set with `history.replaceState`; a missing or unknown hash opens Conversation.
- U49: in Conversation the Traffic-only header controls (tool chips, selects, errors only, hide background, follow live) are hidden; search, theme and `?` stay.
- U50: "most recently active" = latest request or reply-end time in the session; sessions with no requests left (none) are not listed.
- U50: counts: prompts = typed prompts in main, non-subagent requests; tools = tool calls in all replies of the session (subagents included); 🔒 = denied results; ⚠ = rows with an injection hint.
- U50: the newest session is selected until the user clicks a card; after that the choice stays.
- U51: each main thread is drawn from its latest main request plus its reply; several main threads are drawn one after another with a "new thread" divider.
- U51: an assistant message without a tool call is a Claude bubble; text in a message that also has a tool call is a step (D30). So text the model ends a turn with while a background subagent runs is a bubble too.
- U51: the bubble label is "Claude" as in the spec mock-up; Traffic keeps "Model".
- U51: "N steps" counts tool calls; model notes between calls are listed inside the opened line but not counted.
- U51: an Agent/Task call is its own 🤖 line under the 🔧 line of its turn; if a turn has only the Agent call, there is no 🔧 line.
- U51: "Claude is working…" shows while the latest main request has no `end`, or its reply stopped with `tool_use`.
- U51: while a reply streams its text shows as a Claude bubble; when a tool call follows, it moves into the steps.
- U52: a subagent line, opened, shows the task it was given, its steps, and its last text as "report".
- U53: `↗ #n` points to the request whose reply produced the item (tool calls, Claude text) or that carried it (prompts, results).
- U53: going to Traffic sets the session filter and clears the error/tool/model/injection filters so the row is visible.
- U53: `↙ chat` returns to the element `↗` came from; otherwise to the last bubble from that request, else the nearest earlier item, opening its steps line.
- U54: with a search, the session list keeps only matching sessions, and steps lines with a match open by themselves.
- U55 [S] is included: `c` / `t` switch views, `↑` / `↓` move in the session list.

### v5 (updated in place, not rebuilt)

- U56: each markdown paragraph line, list item and heading, and each line of plain prose (prompts, reminders, system messages), is its own element with a direction.
- U56: on top of `dir="auto"`, a line with more Hebrew letters than Latin ones is set `rtl`, because `auto` alone makes "SQL injection היא…" left-to-right (it decides by the first letter).
- U56: my markdown renderer has no tables, so there are no table cells to mark.
- U56: in `→`/`←` previews the label (`You:`, `Model:`) stays outside, and only the quoted text gets a direction, so the label never flips and long Hebrew text is cut at its end, not its start.
- U56: code blocks, JSON, tool input and tool output are `dir="ltr"`; inline `code` is isolated left-to-right inside Hebrew lines.
- U57: a subagent's tag is `Session N · Subagent` (it replaces the separate `subagent` badge); its thread number stays in the tooltip and in the call card's link.
- U58: *sent* = new input + read from cache + written to cache; *received* = output. Row, Reply section, session card, conversation header and header all use the same breakdown popover (hover; click pins it, Esc or a click elsewhere closes it).
- U58: the model for pricing is the reply's `model`, else the request's; a request with no usage costs nothing and is not "without a price".
- U58: a request without a price keeps its tokens in the token totals (A14 still holds) but adds nothing to any cost; the breakdown says how many there are.
- U58: the "$ / 1M" column shows the price when all priced requests in the group use one model, else "by model".
- U58: the old `in / out / cache r / cache w` header and row numbers are replaced; the four token kinds now appear only in the breakdown.

### v6 (updated in place, not rebuilt)

- U59: a session-less request goes into a session when that session's first request comes 0–5 s after it; it is moved there at that moment (it waits in **No session** until then). No session is always the last section.
- U59: section order is by latest activity (request or reply end); sections are moved only when the order changes, never re-created.
- U60: the counts, cost and badges in a section header include the session-less rows pulled into it; the Conversation view still counts only requests that carry the session id.
- U61: the open/closed state is stored per session id in `localStorage` (`secOpen:<id>`). The first burst of records after load is history: when it has been quiet for 800 ms, the most recently active section without a stored state is opened and the others are closed (and stored). A session that first appears after that opens.
- U61: open all / close all sit above the sections and store every section's state.
- U62: "main request" for chart 1 = the main lane of chart 2: a main request that is not part of a subagent thread (subagent requests would break the growing-conversation picture).
- U62: colors: cache read `#c6dbef`, cache write `#6baed6`, new input `#fd8d3c`, output `#a63603` (blue/orange, light to dark); the U58 breakdown shows the same swatches.
- U62/U63: the hover text is the SVG `<title>` tooltip.
- U63: overlapping bars in a lane are spread over up to 3 sub-rows so parallel requests stay visible; the ⚠ mark sits above the bar, the permission dot at its right end.
- U63: lane labels are main / subagent / background; the hover label is the U43 purpose for background requests.
- U64: a 1 s timer redraws charts of open sections that changed or have a running request, and updates header text (the live dot ages without new data); it never re-creates elements.
- U64: row headers and preview lines are replaced only when their content changed (HTML compared). The global header's token group and the Conversation session cards are persistent elements whose text is updated. Cards are moved only when the order changes.
- U64: the Conversation chat itself is still rebuilt when its session's data changes (that is a data change, not a timer).
- U65 [S] is included: chart 1 says "not enough requests yet" with fewer than 2 main requests.
- `[hidden]` always hides (some badges set `display`).

## Self-test (ports 8141 / 8150, `test.jsonl`)

Real traffic: `claude -p "read proxy.py and summarize it in one sentence"`, plus one
`claude -p --input-format stream-json` session with two prompts (a missing-file read, then
a short poem). A 502 came from a second proxy with `--upstream http://127.0.0.1:9`.
A suggestion request and a `quota` 429 were appended as synthetic records, because
`claude -p` does not send them. Streaming was watched by replaying a captured exchange
into the log slowly (with half-written lines).

| Check | Result |
|-------|--------|
| A2 row appears with "in progress", text grows while streaming | pass (slow replay; real replies were too fast to watch) |
| A3 `←` shows `Read(file_path="…/build2/proxy.py")`, next row `→ ↩ Read result (214 lines)`, links scroll + flash | pass |
| A4 `You: "read proxy.py…"`, no reminder shown as a prompt | pass |
| A5 second request: `+N msgs`, "unchanged since #2", "unchanged" tools, same thread | pass (`+3 msgs` here, because Claude Code also sent a system message) |
| A6 six sections in order, System/Tools collapsed with size/count | pass |
| A7 missing file → red result card, red dot on row | pass |
| A8 502 row red, header errors goes up | pass |
| A10 Read filter leaves only Read rows | pass |
| A11 reload and dashboard restart: same rows, no duplicates | pass |
| A12 `grep -E 'sk-ant-[A-Za-z0-9_-]{20,}' test.jsonl` prints nothing | pass |
| A13 proxy terminal output identical to the original, line for line | pass (diffed against a local fake upstream) |
| A14 header totals = sum of rows | pass |
| A15 375 exchanges: rows open in 2–13 ms | pass |
| A16 page follows system light/dark | pass |
| A17 suggestion row muted, labeled **suggestion**, preview "suggestion request" | pass (synthetic record) |
| A18 `quota` 429 → "bg errors" up, red count unchanged | pass (synthetic record) |
| A19 second prompt of one session stays in `T1`, no "new thread" | pass |
| A20 tooltips on badges, `?` legend, Esc closes | pass |
| A21 environment message is a gray **System message**, `+ tool: <name>` chips | pass |
| S5 truncating the log clears the page | pass |
| A1, A9 | pass |

Not checked with a real interactive `claude`: suggestion and `quota` requests (A17, A18) were synthetic.

### v3 checks (A22–A28)

Test folder outside the repo with `notes.txt` (injection comment) and `app.py` (SQL by
string concatenation); the three `claude -p` commands of section 8 ran through the test
proxy (8141 → `test.jsonl`, dashboard 8150). All earlier rows were re-checked on the same log.

| Check | Result |
|-------|--------|
| A22 each session has its own strip color and `S#` tag (S1–S7); the session select shows only that session's rows | pass |
| A23 no row shows `sent: "…"`; `startup check`, `quota check` (synthetic 429 record), and one `status summary` per turn reading `state: done · detail: …` | pass |
| A24 subagent rows (S7·T2) indented, tagged `subagent`, first row `subagent: "List and describe folder files"` + `↖ started by #32`; the Agent call card shows `→ subagent S7·T2` | pass |
| A25 the row with the report shows `🔔 subagent finished`; no row says "previous reply only" | pass |
| A26 app.py run: blocked Edit is an orange **🔒 permission denied** card, row has an orange dot, no red dot | pass |
| A27 notes.txt run: result card has **⚠ possible injection**, "IGNORE ALL PREVIOUS INSTRUCTIONS" highlighted, header `⚠ 3` | pass (the model read the file with `cat` via Bash, not Read) |
| A28 System instructions: contents bar (Intro, Harness, Session-specific guidance, Memory, Environment, Context management), collapsed category cards, Intro `safety`, Memory's code fence renders as code, Raw unchanged | pass |
| Regression: A3–A5, A8, A12, A14, A17, A18 previews/badges/counts unchanged | pass |
| Regression A15: 400 rows / 70 sessions, opening a row with System + Raw ≤ 26 ms | pass |

`changed` / `new` section badges were checked with a synthetic parent/child pair, because
the system text did not change inside any real thread.

### v4 checks (A29–A34)

Same log as A22–A28, plus one two-prompt session (`claude -p --input-format stream-json`,
both prompts using Read) run through the test proxy (8141 → `test.jsonl`, dashboard 8150).

| Check | Result |
|-------|--------|
| A29 opens on Conversation; every session with its first prompt; notes.txt run `⚠ 1`, app.py run `🔒 1` (and `⚠ 1`, because it also read notes.txt) | pass |
| A30 two-prompt session reads exactly You, steps, Claude, You, steps, Claude; no system-reminder, `Current state`, suggestion or `quota` text | pass |
| A31 subagent run: one `🤖 subagent` line; opened: Bash, Glob, Read, Read steps and the report | pass |
| A32 `↗ #49` on a Claude bubble opens Traffic with #49 expanded and flashed; `↙ chat` returns to that same bubble (also checked from a step) | pass |
| A33 during the run: "Claude is working…" and steps filling in live (`Read app.py` → `Bash …`); reload keeps `#conversation` | pass |
| A34 `PWNED`: the list keeps only sessions with a match and the match is highlighted in the opened step | partial: 4 sessions match, not 1, because the app.py run, the subagent run and the two-prompt run also read notes.txt in this log |
| Regression: Traffic rows, previews, header counts unchanged | pass |

### v5 checks (A35–A39)

Same log as before, plus one `claude -p` run with a Hebrew prompt (test proxy 8141 → `test.jsonl`, dashboard 8150).
I used a harmless Hebrew prompt that asks for a short Python example, because A35 needs a code block inside the
Hebrew answer, and the spec's example request would only get a refusal. A35 also had no hacking request to check.
A request with an unknown model (`claude-mystery-9-9`) was appended as a synthetic record for A39.

| Check | Result |
|-------|--------|
| A35 Hebrew question and answer right-to-left in Conversation and Traffic, full stops on the left; English bubbles stay left-to-right; the Python code block inside the Hebrew answer stays left-to-right | pass |
| A36 no `S1`-style labels left: tags `Session 9 · Thread 1`, `Session 7 · Subagent`, cards `Session 9`, select `Session 1 · 12:14 · "…"` | pass |
| A37 header `Tokens sent 1.20M · received 13k · ≈ $0.04 est.`; breakdown has the four lines with explanations and the subscription note; the four costs sum exactly to the total | pass |
| A38 each card shows tokens and `≈ $… est.`; the cards sum to the header total (0.0392 = 0.0392) | pass |
| A39 the unknown model shows `cost ?` on its row and card, is left out of the cost totals, and the breakdown says "1 request without a price" | pass |
| Regression: A30 order, subagent line, permission/injection/notification previews, header counts, reload keeps the view | pass |

### v6 checks (A40–A45)

Same log as before (sessions 1–11; session 11 is a new two-prompt `stream-json` run through the
test proxy 8141 → `test.jsonl`, dashboard 8150). For A44 a slow replay of session 11 under a new
session id (session 12) gave about a minute of continuous live updates, because a real reply finishes in a few seconds.

| Check | Result |
|-------|--------|
| A40 one section per session, newest activity on top, only the top one open on a fresh load; header shows name, time span, first prompt, counts, tokens, cost, badges; No session last | pass |
| A41 Session 7 open with row #39 expanded and Session 8 closed; two new sessions streamed in; states and the expanded row unchanged; after reload all 13 sections keep their state | pass |
| A42 Session 7 chart 1: bars #32, #34, #39 with cache read 22,256 → 34,204 → 36,790; the hover numbers match the row; clicking bar #34 opens row #34 | pass |
| A43 Session 7 chart 2: subagent bars (#33, #36–#38) overlap main #34 in time; status summaries and the startup check in the background lane; #38 (injection) has the ⚠ mark, #36 the permission dot | pass |
| A44 10 real mouse clicks on the Session 12 header while #66 streamed: 10 of 10 toggled (closed/open alternating); the running bar is striped | pass |
| A45 each startup `HEAD /api/hello` sits in the session it started (#1 → Session 1 … #51 → Session 9); one synthetic HEAD with no session after it stays in No session | pass |
| Regression: Conversation (A30 order), filters and search per section, `↗ #n` opens a closed section, header counts | pass |
