# Job Tracker — working notes for Claude Code

Personal job-search tracker. Local only, single user, no auth by design.

You can maintain the data **directly from a Claude Code session in this folder**
by editing the JSON files under `data/` — that is a supported workflow, not a
workaround. The web app's AI chat writes the same files through the same schema.

## Layout

```
backend/     FastAPI + the Claude Agent SDK chat agent
  jsonstore.py   atomic JSON read/write shared by every domain
  storage.py     job applications
  companies.py   the company board — who to target
  company_seed.py curated India list, ~170 companies (data, not logic)
  discover.py    role discovery from public ATS boards
  resumes.py     resume versions + JD tailoring
  dsa.py         DSA practice
  design.py      system design study (LLD/HLD)
  patterns.py    pattern revision across DSA + design
  pattern_seed.py the sheet's 16 DSA patterns + an LLD/HLD set (data, not logic)
  skills.py      skill gaps, read out of the stored job descriptions
  skill_seed.py  the starting skill catalogue (data, not logic)
  prep.py        curriculum phases, standing weaknesses, cross-domain readiness
  ai.py          chat agent, ~70 in-process tools
  main.py        REST routes
  selftest.py    every domain, against a temp dir — no server needed
frontend/    Vite + React dashboard (7 tabs + chat drawer)
  src/cache.js   session cache — survives a browser refresh
  src/refresh.js the auto-refresh loop
data/        the database — eight JSON files, GITIGNORED
```

**Never commit anything under `data/`.** The repo is meant to be shareable; the
tracker's contents are private. The files are created on first run, so a fresh
clone works with an empty `data/`.

## Running it

Two terminals, from the repo root:

```bash
.venv/Scripts/python.exe -m uvicorn main:app --reload --app-dir backend --port 8000
```

```bash
cd frontend && npm run dev
```

Then open http://localhost:5173.

### Windows: --reload and the event loop

uvicorn chooses its loop with `asyncio_loop_factory(use_subprocess)` — Proactor
on Windows *unless* `use_subprocess` is set, which `--reload` and `--workers`
both set. The Agent SDK spawns the CLI as a subprocess, and Windows asyncio can
only do that on a **ProactorEventLoop**; on a selector loop it raises a bare
`NotImplementedError`, which surfaces as `CLIConnectionError: Failed to start
Claude Code: ` with nothing after the colon.

`ai.stream_chat` detects a non-Proactor loop and runs the turn on its own
Proactor loop in a worker thread, forwarding SSE frames back through an
`asyncio.Queue`. Keep that bridge if you touch `stream_chat` — without it,
`--reload` silently breaks every chat turn while the rest of the app works
fine.

## Auth — no API key

The chat runs on the **Claude Code CLI bundled with `claude-agent-sdk`**, which
reuses the existing Claude subscription login in `~/.claude`. Do not add an
`ANTHROPIC_API_KEY` — it isn't needed, and the account can't mint one. If the
chat panel says "not connected", run `claude` once in a terminal and sign in.

## Editing data directly

All dates are ISO `YYYY-MM-DD`. Files are pretty-printed with 2-space indent so
diffs stay readable — keep that formatting. `id` is a UUID string; never reuse
one. Missing keys are backfilled on read by each module's `_normalize`, so a
hand-written record only needs the fields you care about.

Prefer going through the API (`curl localhost:8000/api/...`) over hand-editing
when the server is running, so derived fields like `latest_update_date` stay
consistent.

### `data/jobs.json` — `{"jobs": [...]}`

| Field | Notes |
|---|---|
| `status` | `saved` `applied` `interviewing` `offer` `rejected` `ghosted` `withdrawn` |
| `latest_update` / `latest_update_date` | short description of the most recent change; drives the stale-follow-up detector |
| `rounds[]` | `{round, name, date, result, feedback}`; `result` is `pending` `waiting` `cleared` `rejected` |
| `contacts[]` | `{name, role, email, linkedin, phone, is_referral, notes}`; role is `recruiter` `hr` `hiring_manager` `referral` `employee` `other` |
| `follow_ups_sent[]` | `{date, note}` |
| `company_type` | `startup` `product` `service` `mnc` `agency` `nonprofit` `other` |
| `source` | `linkedin` `careers_page` `referral` `naukri` `job_board` `other` |
| `found_via` | free-text detail behind `source` — the specific post, person, or board |
| `org_summary` | 1–2 sentences on what the company does; AI-written on intake |
| `job_description` | raw JD text — the input for resume tailoring |
| `resume_id` | which resume version was sent (enables per-version response rates) |

`saved` records are excluded from all rate denominators — they aren't
applications yet.

### `data/companies.json` — `{"companies": [...]}`

The shortlist you work *from*, MNC and startup, seeded from `company_seed.py`
(`POST /api/companies/seed`, idempotent — re-running only adds what's new and
never clobbers a status or note you've set).

| Field | Notes |
|---|---|
| `category` | reuses `storage.COMPANY_TYPES`, so promoting a company into an application carries its type through |
| `tier` | `faang` `tier1` `tier2` `growth` `early` — the interview bar you'd prepare for, not a prestige ranking |
| `status` | `researching` `target` `on_hold` `not_interested` |
| `aliases[]` | other names the same employer posts under ("Eternal" for Zomato, the legal entity on a posting) |
| `ats_provider` / `ats_token` | `greenhouse` `lever` `ashby` `none` — the discovery wiring |
| `focus[]` | role families; `interest` is 1–5 and drives the default sort |
| `discovery` | `{last_checked, last_count, last_error}` — a record of the last fetch, not a derived number |

Two things are **joined in at read time and never stored**: `applications` /
`leads` / `board_column` come from `jobs.json`, so the board can't disagree with
the application list. `status` has no `applied` value on purpose — that is
derived, so the board can never claim you applied when you didn't.

Name matching (`companies.matches`) is exact on the name or an alias, plus a
prefix match when the name is ≥5 characters — postings carry legal entities
("Razorpay Software Private Limited"), but a 3-letter name matching by prefix
would have "Ola" claiming every Olam job.

### Role discovery — `discover.py`

**Do not add HTML scraping.** Greenhouse, Lever and Ashby each publish a
documented public JSON endpoint that aggregators are meant to consume, and it is
both stabler and more polite than parsing a careers page that changes on the
next redesign. Companies with no supported board keep `ats_provider: "none"`,
and the assistant falls back to `WebSearch` + `save_discovered_role` for those.

Everything from `parse` down is a pure function over a decoded payload, so the
normalise → filter → dedupe pipeline is tested against fixtures with no network
call. Keep it that way — `selftest.py` must stay hermetic.

Results are deliberately **not persisted**. `jobs.json` is already the ledger;
a second store of "roles I saw once" would need its own expiry and would drift
out of agreement with it. A discovered role becomes real when it is promoted
into a job record, which defaults to `saved` — discovery finds leads, and leads
are outside every rate denominator, so bulk-saving can't distort response rates.

Two matching rules earn their comments in the source, because both were bugs:
`guess_seniority` and `matches_keywords` anchor on **word boundaries**. An
earlier version searched for the substring `"i "` to catch "Engineer I" and
classified "Principal AI Security Specialist" as entry level; keyword `"ai"`
matched "Ret**ai**l". `staff` carries a `(?<!technical )` guard because the AI
labs title every IC level "Member of Technical Staff".

**Verify an ATS token before committing it.** A wrong token does not error — it
silently lists another company's jobs. Six plausible guesses turned out to be
somebody else (`tcs` is a UK care provider, `slice` a US pizza company,
`linkedin` a Greenhouse test board, and `navi`/`porter`/`purestorage` all
belonged to unrelated US firms). Fetch the board and check `company_name`
(Greenhouse) or a sample posting URL (Lever, Ashby). An honest `none` beats a
guess.

### `data/resumes.json` — `{"resumes": [...]}`

`content` holds the resume text; `latex_content` optionally holds LaTeX source,
and the version with `is_latex_template` set is the user's canonical template.
When only LaTeX is present, `resumes._normalize` derives `content` from it via
`latex_export.to_plain_text`, so the dashboard and the Word export still work.

`tailoring[]` entries are
`{date, job_id, organisation, missing_keywords[], suggestions[{section, change}], applied}`.
Tailoring is advisory: never rewrite the resume automatically, and never invent
experience — suggest reframing what is already there and state the gaps.

### Resume export

`backend/docx_export.py` parses the plain text back into name / contact /
sections and renders it with python-docx. It is deliberately ATS-safe — no
tables, images, text boxes, headers, or columns; bullets come from the real
`List Bullet` style rather than literal characters. If you change the text
layout the assistant writes, update `docx_export.parse` and the layout
description in `ai.py`'s system prompt together, or the Word export degrades
silently.

`backend/latex_export.py` serves stored LaTeX byte-for-byte and converts the
Jake Gutierrez / sb2nov macros (`\resumeSubheading`, `\resumeItem`, …) to
readable text. Use `latex_export.escape` for any plain text written *into*
LaTeX.

`backend/pdf_export.py` compiles LaTeX to PDF with whichever engine is
installed, preferring `pdflatex` because the template uses `\pdfgentounicode`
(a pdfTeX primitive the XeTeX engines lack). Compilation runs in a temp
directory with shell-escape disabled, `openin_any`/`openout_any` restricted,
and a 120s timeout — a pasted resume must not be able to read or write the
machine. Two passes, so `\titlerule` and hyperref anchors settle.

`GET /api/resumes/{id}/download?format=pdf|docx|tex` (pdf is the default).
`GET /api/latex/status` reports whether an engine is present, so the UI can
explain a disabled PDF button rather than failing silently.

### `data/dsa.json` — `{"problems": [...]}`

`status` is `todo` `in_progress` `solved` `revisit` `stuck`. Setting a status
stamps `date_started` / `date_completed` automatically. `issues[]` (`{date, issue}`)
is the most valuable field — always capture what actually went wrong.
`confidence` is 1–5 and feeds the revision queue.

`time_complexity` / `space_complexity` hold LaTeX math **without** delimiters
(`O(n \log n)`, `O(h)`) so the same string renders in the dashboard and pastes
into a write-up. `phase` links the problem to a curriculum phase in
`prep.json`, which is what drives per-phase progress.

A solved problem with no complexity recorded is counted in
`stats()["missing_complexity"]` and listed by `missing_complexity()`, but is
**deliberately kept out of `revision_queue()`**. That queue means "re-solve
this"; an unannotated solve needs a one-line note instead, and conflating the
two makes the queue noisy enough to be ignored.

There are **two queues, and they must stay disjoint**. `revision_queue()` is
"re-solve something you already solved"; `next_up()` is "attempt something you
never finished" — `in_progress`, then `stuck`, then `todo`, current curriculum
phase before everything else, difficulty ascending, file order last. Merged into
one list they compete for the same slot and the redo always loses. `next_up()`
reads `current_phase` from `prep.json` with a local import, the same direction
`prep.get_prep()` reads `dsa.json`; neither module imports the other at load.

Entries carry the number, title, topics and a reason and **nothing else** — no
solution notes, no complexity, no approach. The assistant's interview mode gives
a LeetCode number and stops, so the queue must not be the hint leak that undoes
it. The assistant reads the same list via `get_dsa_next_up`, so its pick and the
dashboard's can't disagree.

### `coach()` — the one recommendation

`next_up()` and `revision_queue()` answer "what is outstanding". `coach()` picks
*between* them and answers "what now", in this order:

`unlocked` → `finish` → `drill` → `revise` → `advance` → `idle`

It is **weakness-first, not curriculum-first**. A standing issue that has
recurred `DRILL_AFTER_RECURRENCES` (3) times is a concept that hasn't landed,
and new material stacked on top only manufactures more instances of it. The
drill deliberately prefers a *different unsolved problem sharing a topic* with
where the habit last appeared, falling back to a redo only when none exists —
the user learns concepts and refuses to memorise patterns, so reproducing a seen
answer is the wrong rep. Keep that preference in mind anywhere the assistant
justifies a pick; `prep.profile.notes` carries it for the chat agent.

`revise` fires on a cadence measured in **solves, not days** (`REVISE_EVERY`) —
days punish a slow week, solves track what actually creates revision debt.

Every branch appends to `because[]`. A recommendation nobody can audit is one
that gets ignored the first time it looks wrong, and this one overrides the
curriculum order, so it has to show its working. Keep `because[]` to reasoning
the caller can't derive from the other fields — `on_hold` and `unlocked` are
returned separately, so restating them as prose only lengthens the list.

The dashboard renders all of this as **one card**, not two: the pick, then the
rest of `next_up()` under "Then" with the pick filtered out, then what's on
hold. The pick is normally the head of the queue, so separate cards showed the
same problem twice — and when they do differ (a redo, or a deferral returning)
the queue is only useful as context for the pick anyway.

### The stopwatch — `timer`

```
"timer": {"started_at": ISO8601 | None, "accumulated_seconds": int, "capped": bool}
```

`started_at` is the segment currently running (`None` when paused);
`accumulated_seconds` is everything already banked. `POST /api/dsa/{id}/timer`
takes `start` / `pause` / `reset`, and **start is also the status change** —
splitting "begin the problem" and "begin timing it" into two clicks is how a
timer ends up never being used.

Four things that are load-bearing:

- **Server-side, not sessionStorage.** A refresh, a second tab and the chat
  agent must all read the same clock.
- **`elapsed_seconds` is derived and never persisted.** It is attached by
  `_public()` on the read paths, deliberately *not* by `_normalize()`, which
  also runs on the write path. `selftest.py` asserts it never reaches the file.
- **Timer stamps carry a time of day**, unlike every other date in `data/` — a
  stopwatch can't work at day resolution. They're the one exception to the ISO
  `YYYY-MM-DD` rule above.
- **A segment over `STALE_SEGMENT_HOURS` (4) is banked at the cap**, with
  `capped` set. One timer left running overnight would wreck
  `avg_time_minutes`, which is the only reason the stopwatch exists; the flag
  keeps the number auditable rather than quietly wrong.

Marking a problem solved banks the running segment and fills
`time_spent_minutes` — but only if the clock actually ran **and** the field is
empty. A hand-entered figure for a problem solved away from the app is an
explicit act and always wins.

### Deferral — `status: "deferred"`

For a problem that is genuinely too far ahead. A `stuck` problem stalls the
phase and quietly becomes a wall; a deferred one is off every queue with a
stated, checkable way back:

```
"defer": {"reason": ..., "until_solved": [problem_id], "review_on": date|None}
```

`until_solved` is the point — "I'll come back to it" is a note to nobody, while
a prerequisite list makes the problem resurface on its own as `coach()["kind"]
== "unlocked"`. `_normalize` **clears `defer` whenever the status is not
`deferred`**, so a resurfaced problem can never still read as on hold. Because
`deferred` is absent from `NEXT_UP_RANK`, it drops out of `next_up()` for free.

### `data/design.json` — `{"topics": [...]}`

`kind` is `hld` or `lld`. `status` is `todo` `studying` `practiced` `revisit`
`stuck` — "practiced" means producible unaided, not just read. `concepts[]` is
the cross-cutting tag used for weak-area stats; `components[]` is HLD
vocabulary, `patterns[]` is LLD. `tradeoffs` is what interviewers probe.

### `data/prep.json` — `{"phases": [...], "profile": {...}, "standing_issues": [...]}`

The state that sits *above* individual problems. Note the shape: unlike the
other four files this one is not a single list, so `jsonstore.read` is called
with `"phases"` as the list key and the other two blocks ride alongside.

`profile` holds `target_levels[]`, `target_companies[]`, `current_phase`,
`current_milestone`. `phases[]` are `{key, name, status, order, topics[],
milestone}` where `status` is `completed` `current` `upcoming` — setting one
phase `current` demotes the previous one, so `current_phase` is never
ambiguous. Per-phase solve counts are joined in from `dsa.json` at read time by
matching `problem.phase` to `phase.key`; they are never stored.

`standing_issues[]` are `{issue, category, active, date_added, seen_on[],
date_resolved}`. The distinction that matters: a **per-problem** `issues[]`
entry is what went wrong *that time*; a **standing** issue is a habit that
recurs across unrelated problems. `seen_on[]` (`{date, problem_id}`) is what
makes the recurrence count real — flag it every time, or the list degrades into
a static checklist. `category` is `logic` `syntax` `complexity` `style`
`process`.

### `data/patterns.json` — `{"patterns": [...]}`

The third axis. `dsa.json` tracks a problem, `prep.json` tracks the phase above
it, and this tracks the **technique** — which cuts across both other domains
and across every phase, so "what do I still not have" is a question neither of
the other two can answer.

Seeded from `pattern_seed.py` (`POST /api/patterns/seed`, idempotent): the
sixteen patterns from the DSA sheet, in the sheet's order and with its
sub-groupings, plus ten LLD/HLD techniques that have no equivalent sheet.

| Field | Notes |
|---|---|
| `key` | the identity, not `id` — routes take the key, the way `prep.py` phases do |
| `domain` | `dsa` `lld` `hld`; decides which file the join reads and which file `promote` writes to |
| `idea` | the invariant that makes the technique correct — **not** a template and not a recognition cue |
| `problems[]` | the catalogue: `{title, url, difficulty, group, challenge, refs[]}` |
| `confidence` | 1–5, self-rated — the one progress signal the joins cannot supply |
| `flagged` | forces it into the revision queue before the cadence would |

**Everything about progress is joined in at read time and never stored.**
`solved`, `coverage`, `state`, `last_worked` and `due` are recomputed from
`dsa.json` and `design.json` on every read — the same choice `companies.py`
makes against `jobs.json`, for the same reason. A stored copy of "have I done
this" eventually disagrees with the tab that owns it, and the stale one is the
one being read. `selftest.py` asserts none of it reaches the file.

The join key is the **URL slug, namespaced by host** (`leetcode:two-sum`), with
a normalised title as the fallback for a record entered by hand with no URL.
Namespacing matters: LeetCode and GfG both publish `/problems/<slug>`. Title
matching strips his `LC 207 - ` prefix, which is why the sheet's "Contruct tree
from preorder and inorder" and `LC 105 - Construct Binary Tree from Preorder
and Inorder Traversal` are correctly the same problem — by slug, not by title.

Two lists, and like `dsa.py`'s pair they **must stay disjoint**:

- `revision_queue()` — patterns with real work behind them that has since
  decayed. Re-derive these.
- `unstarted()` — patterns with nothing solved at all.

You cannot revise what you never learned, so **nothing untouched is ever due, a
hand-set flag included**. That is what makes the two lists disjoint by
construction rather than by convention, and the frontend disables the flag
button on an untouched pattern rather than letting it look set and do nothing.

There is deliberately **no second coach**. `dsa.coach()` answers "which problem
now" and stays the only thing that does; this module answers "which technique
has gone stale", a different question at a different altitude. Two competing
"do this next" cards would eventually disagree, and both would stop being read.

Work tagged with a pattern but not listed under it (a DSA problem topic'd
`sliding-window`, a design topic tagged with the pattern key) counts as
**activity** — it feeds `last_worked` and stops the pattern reading as
untouched — but deliberately not toward `coverage`. The catalogue is the
curriculum; a denominator that grows every time something is tagged is a
percentage that means nothing.

`promote` turns a catalogue row into real work: a `todo` in `dsa.json`, or a
`todo` topic in `design.json` tagged with the pattern so it joins straight
back. It sets **no phase** — stamping the current phase onto a tree problem
promoted mid-Phase-2 would let it jump `next_up()` as "next in Graph
Foundations", which it isn't. Pattern study is a parallel track to the
curriculum, so promoted work lands in the backlog until a phase is set
deliberately.

### `data/skills.json` — `{"skills": [...]}`

The fourth axis, and the only one that points outward. `dsa.json` tracks a
problem, `prep.json` the phase above it and `patterns.json` the technique —
all three measure work already chosen. This one measures the **market**: what
the postings in `jobs.json` keep asking for that he cannot supply.

Seeded from `skill_seed.py` (`POST /api/skills/seed`, idempotent).

| Field | Notes |
|---|---|
| `key` | the identity, not `id` — routes take the key, like `patterns.py` and `prep.py` |
| `aliases[]` | **the join wiring.** What matches the skill against a JD and against a resume; see the matching rules below |
| `level` | 0 none · 1 aware · 2 used · 3 built · 4 shipped. The one signal neither join can supply |
| `target_level` | what "closed" means here; defaults to 3 (`built`), not `shipped` — a bar only production work can clear is one no personal project reaches |
| `effort` | `days` `weeks` `months`, and it feeds the rank: this is a work queue, not a wishlist |
| `status` | `wanted` `learning` `declined` `done`. `declined` is the load-bearing one — see below |
| `plan` | the concrete closing move, not the topic. "Deploy the tracker to a kind cluster", not "learn Kubernetes" |
| `log[]` | `{date, note, level}` — what actually moved the level |

**Everything about demand and claims is joined in at read time and never
stored.** `demand`, `mentions`, `organisations`, `claimed`, `state`, `score`
and `rank` are recomputed from `jobs.json` and `resumes.json` on every read —
the same choice `companies.py` and `patterns.py` make, for the same reason.
This is also the whole feature: paste a posting on the Applications tab and the
ranking reorders itself, with nothing to refresh and nothing that can drift.
`selftest.py` asserts none of it reaches the file.

#### Two joins, and the second is the interesting one

`jobs.json` supplies demand. `resumes.json` supplies `claimed`, and
**claimed with nothing behind it is not a gap, it is a live credibility risk** —
the reader has already been told he has it, so the question is coming. That
state (`exposed`) is worth more than any count, and neither file can see it
alone.

The resume join reads the **skills section only**, via `skills.claim_text`.
A skills row is where a claim is *made*; prose is evidence, and evidence is
fine. Matching the whole document flagged half the catalogue: a bullet reading
"raised outreach throughput from 30 to 200 emails/hour" contains "throughput"
and claims nothing about performance engineering.

#### Matching — `skills.mentions`, and why it looks paranoid

Same lesson as `discover.py`, learned the same way. Every one of these actually
fired against `data/jobs.json`:

| Alias | Matched | Fix |
|---|---|---|
| `eks` | "features live within w**eeks**" | boundary anchors |
| `scala` | "**scala**ble solutions" | boundary anchors |
| `ai` | "Ret**ai**l" | boundary anchors |
| `design document` | *missed* "design documents" | optional plural |
| `voice pipeline` | *missed* the entire Weekday posting | optional plural + `_VOICE` |
| `Go` | "**Go** ahead, apply anyway" | `_GO` guard |
| `streaming` | "SSE **Streaming**" in seven resumes | `_STREAMING` guard |

So: aliases anchor on identifier boundaries (not `\b`, which falls in the
middle of `C++`, `.NET` and `CI/CD`), tolerate a trailing plural, and an alias
prefixed **`re:`** is a raw pattern matched case-sensitively. Every `re:` alias
in `skill_seed.py` carries a comment naming the false positive it kills — the
last two above cannot be fixed by anchoring, because they are real
word-boundary matches on real English.

`_normalize` inserts the name as an alias **only when the list is empty**. An
earlier version always appended it, which quietly put the bare `Go` back behind
the guard written to exclude it. If the author supplied aliases, the author is
in charge.

#### The ranking

`gap_queue()` is ordered by

```
round(10 * log2(1 + weighted_demand)) + gap * 5 + effort_bonus + exposed_bonus
```

where a mention is weighted by the job's status (`interviewing` 4 … `rejected`
1 — a live application is a question that could be asked next week; a rejected
one is still market signal), `effort_bonus` is 4/2/0 for days/weeks/months, and
`exposed_bonus` is 6.

Demand **saturates** rather than accumulating: one posting to four is a real
change in what the market is saying, eight to nine is noise. Counted straight,
a word every JD uses in passing ("code review") outranks a stated hard
requirement ("Kubernetes") on frequency alone, and a ranked list that does that
stops being read.

Every branch appends to `because[]`, for the same reason `dsa.coach()` does —
this one reorders itself whenever a job is added, so it *will* look wrong
eventually and has to defend itself when it does.

Rows with no demand are **out of the queue entirely**. The board is driven by
the pipeline; a catalogue row nothing has asked for is a row waiting for a
posting to justify it, and `stats()["no_demand"]` counts those.

#### `declined`, and why demand still counts under it

A skill only one posting ever wanted is a real requirement and still the wrong
thing to learn. `decline(key, reason)` — **a reason is required**, because "not
doing this" with no why is indistinguishable from having forgotten — drops it
from the queue while its demand keeps updating. That is what makes the decision
re-readable later against a number that has moved, instead of a dead entry
nobody revisits.

#### Two lists, and these ones may overlap

`gap_queue()` says "acquire this"; `exposed()` says "this claim is unbacked".
Unlike `dsa.py`'s and `patterns.py`'s pairs they are **deliberately not
disjoint** — they are not two answers to the same question, and a skill that is
both in demand and falsely claimed genuinely needs both actions. Forcing them
apart would mean dropping one of two things that are both true.

#### Skills already held belong in the catalogue

They are the denominator for `stats()["coverage"]`. A file containing only gaps
reports 0% forever and says nothing. Rows at or above `target_level` drop out of
the queue on their own.

**Only `log_evidence` moves a level**, and it requires a note. Self-ratings
drift upward without a record behind them, and an inflated level becomes a
question that cannot be answered in an interview — which is the exact failure
`exposed` exists to catch. `for_job(job_id)` is the pre-application view: what
*this* posting screens on, rather than the pipeline's average.

### Cross-domain: `prep.readiness()`

The one view that joins the practice domains — scheduled rounds from `jobs.json`
are the deadline, and the DSA queue, design queue and standing weaknesses are
what you have to turn up with. Prep coverage is matched by **company tag**
(case-insensitive against `organisation`), so `untagged_companies` lists live
applications with no practice tagged against them. Tagging practice with a
company is what makes it show up here.

## Testing

`backend/selftest.py` runs every domain against a temp directory — no server,
no test framework, and it never touches `data/`:

```bash
.venv/Scripts/python.exe backend/selftest.py
```

It repoints `jsonstore.DATA_DIR` *before* importing the domain modules; keep
that ordering if you add to it. The final block guards the AI system prompt,
which contains LaTeX braces that an f-string would eat — that bug once killed
every chat turn before it reached the model.

## Frontend: session cache and auto-refresh

`src/cache.js` wraps **sessionStorage** — per browser tab, gone when the tab
closes. Not localStorage: two tabs on the tracker are two working contexts, and
resume text and contact details shouldn't outlive the window they were read in.
It degrades to an in-memory Map when storage is unavailable; a cache must never
be the reason the app breaks.

Three things it holds. **UI state** (open tab, chat drawer, auto-refresh on/off)
through the `useCached` hook. **The dashboard snapshot**, so a browser refresh
redraws the page you were on instead of flashing "Loading…" — hydrated once into
a ref at mount, spread over `EMPTY` so a snapshot from before a field existed
can't hand a child `undefined`. **The chat transcript and session id**, written
at turn boundaries only; `messages` changes on every streamed token, so a
`useCached` there would be hundreds of storage writes a second.

Two rules that are load-bearing:

- **`CACHE_VERSION` is how you invalidate.** Bump it when a cached shape changes
  in a way `{...EMPTY, ...snapshot}` can't absorb. Old entries are swept at load.
- **The timestamp lives under its own key.** Folded into the snapshot it would
  change on every poll and defeat the unchanged-value check, turning each tick
  into a 200 KB synchronous write. As it is, an unchanged poll writes 13 bytes.

`src/refresh.js` polls every 30s. It exists because the dashboard isn't the only
writer — the chat agent and hand-edits to `data/` change the same files. The
loop **skips hidden tabs** (one left open overnight would be ~2,880 pointless
requests, and still stale the moment it's looked at) and catches up on
`visibilitychange`; it holds the callback in a ref so a parent re-render can't
reset the interval; and it drops overlapping ticks. A failed poll **keeps the
last good screen** and marks the topbar "stale · offline" — the full error card
is only for having nothing to show at all.

## Conventions

- Derived numbers (rates, queues, weak topics) are computed in the backend, never
  stored. Add new stats to the domain module's `stats()`, not the frontend.
- The dashboard reads identity from row labels, not colour — a single hue is used
  for magnitude bars deliberately. Don't introduce a multi-colour categorical
  palette without validating it for colour-vision separation.
- Adding a field: update the domain module's `_DEFAULTS` + `_normalize`, the
  Pydantic model in `main.py`, and the AI tool schema in `ai.py` if the assistant
  should be able to set it. Then add a check to `backend/selftest.py`.
- A pattern's `idea` is revision material, not a hint. It belongs in a revision
  session or a post-mortem — never alongside a problem just handed over. The
  system prompt says so, and interview mode overrides that section rather than
  the other way round.
- The assistant has an **interview mode** in `ai.py`'s system prompt: when asked
  for a problem it gives the LeetCode number and title and nothing else — no
  description, signature, template, edge cases or hints. That restraint is the
  feature; don't soften it into "helpfully" including a starting point.
- Interview mode runs in the **doc format**, modelled on a Google onsite: the
  solution is typed into the chat — no IDE, no autocomplete, nothing executes —
  and is worked through in full *before* it is submitted on LeetCode. This
  applies to a Claude Code session in this folder exactly as it does to the web
  chat; both read the same spec in `ai.py`.

  Two consequences. **Pause the stopwatch the moment a solution arrives**, and
  restart it only if he goes back to rewrite — `time_spent_minutes` means time
  to produce a solution, and folding the review into it makes
  `avg_time_minutes` measure how talkative the reviewer was. And **review the
  mistakes an IDE would have caught** — typos, unbound names, missing imports —
  because in a doc round those are the candidate's to catch. Dry-run against a
  concrete input and hand back expected-vs-actual rather than a corrected
  listing; the failing case is the thing that teaches.
