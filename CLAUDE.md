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
  ai.py          chat agent, ~29 in-process tools
  main.py        REST routes
frontend/    Vite + React dashboard (4 tabs + chat drawer)
data/        the database — four JSON files, GITIGNORED
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
| `org_summary` | 1–2 sentences on what the company does; AI-written on intake |
| `job_description` | raw JD text — the input for resume tailoring |
| `resume_id` | which resume version was sent (enables per-version response rates) |

`saved` records are excluded from all rate denominators — they aren't
applications yet.

### `data/resumes.json` — `{"resumes": [...]}`

`content` holds the resume text. `tailoring[]` entries are
`{date, job_id, organisation, missing_keywords[], suggestions[{section, change}], applied}`.
Tailoring is advisory: never rewrite the resume automatically, and never invent
experience — suggest reframing what is already there.

### `data/dsa.json` — `{"problems": [...]}`

`status` is `todo` `in_progress` `solved` `revisit` `stuck`. Setting a status
stamps `date_started` / `date_completed` automatically. `issues[]` (`{date, issue}`)
is the most valuable field — always capture what actually went wrong.
`confidence` is 1–5 and feeds the revision queue.

### `data/design.json` — `{"topics": [...]}`

`kind` is `hld` or `lld`. `status` is `todo` `studying` `practiced` `revisit`
`stuck` — "practiced" means producible unaided, not just read. `concepts[]` is
the cross-cutting tag used for weak-area stats; `components[]` is HLD
vocabulary, `patterns[]` is LLD. `tradeoffs` is what interviewers probe.

## Conventions

- Derived numbers (rates, queues, weak topics) are computed in the backend, never
  stored. Add new stats to the domain module's `stats()`, not the frontend.
- The dashboard reads identity from row labels, not colour — a single hue is used
  for magnitude bars deliberately. Don't introduce a multi-colour categorical
  palette without validating it for colour-vision separation.
- Adding a field: update the domain module's `_DEFAULTS` + `_normalize`, the
  Pydantic model in `main.py`, and the AI tool schema in `ai.py` if the assistant
  should be able to set it.
