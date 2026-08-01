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
  resumes.py     resume versions + JD tailoring
  dsa.py         DSA practice
  design.py      system design study (LLD/HLD)
  prep.py        curriculum phases, standing weaknesses, cross-domain readiness
  ai.py          chat agent, ~38 in-process tools
  main.py        REST routes
  selftest.py    every domain, against a temp dir — no server needed
frontend/    Vite + React dashboard (4 tabs + chat drawer)
data/        the database — five JSON files, GITIGNORED
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

### Cross-domain: `prep.readiness()`

The one view that joins all four domains — scheduled rounds from `jobs.json`
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

## Conventions

- Derived numbers (rates, queues, weak topics) are computed in the backend, never
  stored. Add new stats to the domain module's `stats()`, not the frontend.
- The dashboard reads identity from row labels, not colour — a single hue is used
  for magnitude bars deliberately. Don't introduce a multi-colour categorical
  palette without validating it for colour-vision separation.
- Adding a field: update the domain module's `_DEFAULTS` + `_normalize`, the
  Pydantic model in `main.py`, and the AI tool schema in `ai.py` if the assistant
  should be able to set it. Then add a check to `backend/selftest.py`.
- The assistant has an **interview mode** in `ai.py`'s system prompt: when asked
  for a problem it gives the LeetCode number and title and nothing else — no
  description, signature, template, edge cases or hints. That restraint is the
  feature; don't soften it into "helpfully" including a starting point.
