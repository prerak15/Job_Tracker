# Job Tracker

A personal job-search tracker that runs on your own machine. Four things in one
dashboard — **applications**, **DSA practice**, **system design study**, and
**resume versions** — plus an AI assistant that fills it all in for you.

No login, no API key, no cloud. Your data is four JSON files in `data/`.

## What it does

**Talk to it instead of filling in forms.** Paste a job posting and it creates
the record: title, organisation, posted date, salary, location, company type,
industry, and a short summary of what the company actually does. Say "rejected
from Acme" and it finds the record and updates the status. Say "cleared round 2,
the DP question killed me" and it logs the round with the feedback.

**It tells you who to chase.** Applications that have gone quiet surface on the
dashboard and in the chat — ask "who should I follow up with?" and it answers
with names, how long they've been silent, and the contact you have on file.

**It tracks what went wrong, not just what happened.** Every DSA problem and
design topic has an issue log. Low-confidence and stale items come back around
in a revision queue, so weak areas resurface instead of being quietly forgotten.

**It separates one-off mistakes from habits.** A per-problem issue is what went
wrong that time. A *standing weakness* is the thing you keep doing on unrelated
problems — and those get their own list with a recurrence count, so the same
lesson isn't re-learned every few weeks. Practice is organised into curriculum
phases, and the dashboard shows how far through each one you are.

**It can interview you.** Ask for a problem and the assistant gives you the
LeetCode number and title — nothing else. No description, no function
signature, no starter template, no edge cases, no hints unless you ask for one.
Submit your solution and it grades correctness, time and space complexity,
cleanliness, edge cases, and the trade-offs you chose, then writes the result
into the tracker and cross-checks it against your standing weaknesses.

**It knows what's actually urgent.** Ask "what should I work on?" and it joins
all four domains: interview rounds on the calendar, what's stuck, what's due for
revision, and which live applications you have no practice tagged against.

**It shows which resume works.** Record which version you sent with each
application and the Resumes tab gives you a reply rate per version. Ask it to
tailor a resume against a stored job description and it lists the missing
keywords and concrete per-section rewrites — advisory only, nothing is
auto-rewritten, and it reports gaps rather than inventing experience.

**Resumes download as PDF, Word, or LaTeX.** If you keep your resume in LaTeX,
paste the `.tex` in and mark it as your template. The assistant then reuses
your own preamble and macros when tailoring, and the **PDF button compiles it
locally** — the same output you'd get from Overleaf, without leaving the app.
Readable text is derived from the LaTeX automatically, so the Word export and
the dashboard preview work too. The `.docx` is laid out for applicant tracking
systems — no tables, text boxes, or images, since those parse badly and cost
interviews.

PDF export needs a TeX engine (`pdflatex` from MiKTeX or TinyTeX). Without one
the button explains what's missing and the `.tex` and Word downloads still work.

## Setup

Requires Python 3.11+ and Node 18+.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
cd frontend && npm install
```

## Running it

Two terminals, from the repo root:

```bash
.venv/Scripts/python.exe -m uvicorn main:app --reload --app-dir backend --port 8000
```

```bash
cd frontend && npm run dev
```

Open <http://localhost:5173>.

To check the backend without starting anything:

```bash
.venv/Scripts/python.exe backend/selftest.py
```

It exercises every domain against a temporary directory, so it never reads or
writes your own `data/`.

## The AI, and why there's no API key

The assistant runs on the **Claude Agent SDK**, which drives the Claude Code CLI
bundled with it. That CLI reuses whatever Claude account you're already signed
in to (`~/.claude`), so a **Claude Pro/Max subscription works directly** — you
never generate or paste an API key.

If the chat panel shows "not connected", run `claude` once in a terminal and
sign in. The panel shows `Claude subscription` when it's authenticated.

The assistant only has the ~29 tools that read and write this tracker, plus web
search for looking up an unfamiliar company. It has no shell or filesystem
access.

## Your data stays on your machine

Everything lives in `data/`, as readable JSON:

| File | Holds |
|---|---|
| `jobs.json` | applications and leads, rounds, contacts, follow-ups |
| `resumes.json` | resume versions and tailoring suggestions |
| `dsa.json` | DSA problems, timings, issue log |
| `design.json` | LLD/HLD topics, tradeoffs, artifacts |

**`data/` is gitignored.** The repository is safe to share or make public — your
application history, recruiter names, and contact details are never committed.
The app creates the files on first run, so a fresh clone starts empty.

If you want your own history version-controlled, keep a separate private repo
inside `data/`, or back the folder up somewhere off-git.

You can also edit the files from a Claude Code session in this folder — see
[CLAUDE.md](CLAUDE.md) for the schema.

## Ideas for later

Browsing job boards for new leads and people to reach out to, fetching a posting
straight from a URL, drafting the follow-up message from the contact on file, a
pipeline funnel chart, spaced repetition for the revision queue, and a weekly
AI-written summary of what moved and what's gone stale.
