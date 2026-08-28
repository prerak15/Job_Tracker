"""End-to-end checks for every backend domain, against a throwaway data dir.

Run it from the repo root:

    .venv/Scripts/python.exe backend/selftest.py

No test framework and no server needed — plain asserts, so a fresh clone can
verify itself before touching real data. `jsonstore.DATA_DIR` is repointed at a
temp directory *before* the domain modules are imported, so your own
`data/*.json` is never read or written by this file.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))

import jsonstore  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="tracker-selftest-"))
jsonstore.DATA_DIR = tmp
print(f"scratch data dir: {tmp}\n")

import design  # noqa: E402
import dsa  # noqa: E402
import prep  # noqa: E402
import resumes  # noqa: E402
import storage  # noqa: E402

# ------------------------------------------------------------------ jobs
job = storage.create_job(
    {
        "job_title": "Backend Engineer",
        "organisation": "Acme Corp",
        "status": "applied",
        "date_job_posted": "2026-07-20",
        "company_type": "startup",
        "industry": "fintech",
        "org_summary": "Payment infra for SMBs.",
        "source": "linkedin",
        "found_via": "post by their VP Eng",
        "job_description": "Python, Kafka, gRPC, distributed systems.",
    }
)
assert job["id"] and job["date_created"], job
assert job["latest_update"] == "Record created"
assert job["found_via"].startswith("post by"), job["found_via"]

storage.add_contact(
    job["id"],
    {"name": "Jane Doe", "role": "recruiter", "is_referral": True, "email": "j@acme.com"},
)
assert storage.get_job(job["id"])["referred_by"] == "Jane Doe"

storage.add_round(
    job["id"], {"name": "Online assessment", "result": "cleared", "feedback": "DP was hard"}
)
job = storage.get_job(job["id"])
assert job["status"] == "interviewing", job["status"]
assert job["rounds"][0]["round"] == 1

storage.update_round(job["id"], 1, {"feedback": "DP was hard; revise LIS"})
storage.add_followup(job["id"], "Emailed Jane")
job = storage.get_job(job["id"])
assert len(job["follow_ups_sent"]) == 1
assert job["rounds"][0]["feedback"].endswith("revise LIS")

job2 = storage.create_job(
    {"job_title": "SDE", "organisation": "Globex", "status": "rejected"}
)

s = storage.stats()
assert s["total"] == 2 and s["applied_total"] == 2, s
assert s["interview_rate"] == 50.0, s["interview_rate"]
assert s["response_rate"] == 100.0, s["response_rate"]
assert s["rejection_rate"] == 50.0, s["rejection_rate"]
assert s["by_company_type"]["startup"]["applications"] == 1
print("jobs OK    ", {k: s[k] for k in ("total", "response_rate", "interview_rate")})

# A freshly-created record must not mask a deliberately older update date, or
# nothing ever looks overdue.
storage.update_job(job2["id"], {"status": "applied", "latest_update_date": "2020-01-01"})
due = storage.followup_suggestions(stale_days=7)
assert len(due) == 1 and due[0]["organisation"] == "Globex", due
assert due[0]["days_since_activity"] > 1000
print("followups OK", due[0]["days_since_activity"], "days stale")

# ------------------------------------------------------------------ resumes
master = resumes.create_resume(
    {
        "name": "SDE master",
        "version_label": "v1",
        "is_master": True,
        "content": "Python, Django, Postgres",
    }
)
resumes.link_to_job(master["id"], job["id"])
assert storage.get_job(job["id"])["resume_id"] == master["id"]

resumes.add_tailoring(
    master["id"],
    {
        "job_id": job["id"],
        "missing_keywords": ["Kafka", "gRPC"],
        "suggestions": [{"section": "Experience", "change": "Reframe around event-driven"}],
    },
)
r = resumes.get_resume(master["id"])
assert r["tailoring"][0]["organisation"] == "Acme Corp", r["tailoring"][0]
assert r["tailoring"][0]["applied"] is False
resumes.set_tailoring_applied(master["id"], 0, True)
assert resumes.get_resume(master["id"])["tailoring"][0]["applied"] is True

# LaTeX-only version: plain text must be derived so the dashboard and the Word
# export still work.
latex_only = resumes.create_resume(
    {
        "name": "LaTeX master",
        "is_latex_template": True,
        "latex_content": (
            "\\documentclass{article}\\begin{document}"
            "\\textbf{Jane Roe} \\\\ jane@example.com"
            "\\section{Education}"
            "\\end{document}"
        ),
    }
)
assert latex_only["content"].strip(), "plain text should be derived from LaTeX"
assert "documentclass" not in latex_only["content"], latex_only["content"]

rs = resumes.stats()
version = next(v for v in rs["by_version"] if v["id"] == master["id"])
assert version["applications"] == 1 and version["interview_rate"] == 100.0, version
print("resumes OK ", {k: version[k] for k in ("applications", "interview_rate")})

# ------------------------------------------------------------------ dsa
p = dsa.create_problem(
    {
        "title": "Longest Increasing Subsequence",
        "difficulty": "medium",
        "topics": ["dp", "binary-search"],
        "status": "in_progress",
        "phase": "phase_4",
    }
)
assert p["date_started"] and p["date_completed"] is None, p
assert p["phase"] == "phase_4" and p["time_complexity"] == "", p
dsa.log_issue(p["id"], "Missed the patience-sorting angle")
p = dsa.update_problem(
    p["id"],
    {
        "status": "solved",
        "time_spent_minutes": 55,
        "attempts": 2,
        "used_hint": True,
        "confidence": 2,
        "time_complexity": r"O(n \log n)",
        "space_complexity": "O(n)",
    },
)
assert p["date_completed"] and len(p["issues"]) == 1
assert p["time_complexity"] == r"O(n \log n)", p["time_complexity"]

two_sum = dsa.create_problem(
    {
        "title": "Two Sum",
        "difficulty": "easy",
        "topics": ["hashmap"],
        "status": "solved",
        "confidence": 5,
        "time_spent_minutes": 10,
        "phase": "phase_1",
    }
)
dsa.create_problem(
    {"title": "Median of Two Sorted Arrays", "difficulty": "hard", "status": "stuck"}
)

ds = dsa.stats()
assert ds["total"] == 3 and ds["solved"] == 2, ds
assert ds["by_difficulty"]["hard"]["solved"] == 0
assert ds["avg_time_minutes"] == 32.5, ds["avg_time_minutes"]
assert ds["hint_rate"] == 50.0, ds["hint_rate"]
assert ds["by_phase"]["phase_4"]["solved"] == 1, ds["by_phase"]
assert ds["by_phase"]["unassigned"]["total"] == 1, ds["by_phase"]

# Two Sum is solved but unanalysed: it is counted, and it must NOT be pushed
# into the revision queue -- that queue means "re-solve this", and an
# unannotated solve needs a one-line note instead.
assert ds["missing_complexity"] == 1, ds["missing_complexity"]
assert [m["id"] for m in dsa.missing_complexity()] == [two_sum["id"]]

q = dsa.revision_queue()
assert len(q) == 1 and q[0]["title"].startswith("Longest"), q
assert "low confidence" in q[0]["reason"], q[0]["reason"]
print("dsa OK     ", {k: ds[k] for k in ("total", "solved", "missing_complexity")})

dsa.log_revisit(p["id"], "solved unaided in 20m", confidence=5)
assert len(dsa.revision_queue()) == 0, dsa.revision_queue()

# ------------------------------------------------------------------ design
t = design.create_topic(
    {
        "title": "Design a URL shortener",
        "kind": "hld",
        "concepts": ["consistent-hashing", "caching"],
        "status": "studying",
    }
)
assert t["date_started"] and t["date_completed"] is None
design.log_issue(t["id"], "Couldn't justify the sharding key")
t = design.update_topic(
    t["id"],
    {"status": "practiced", "time_spent_minutes": 90, "confidence": 3, "tradeoffs": "base62"},
)
assert t["date_completed"], t
design.add_artifact(t["id"], {"type": "diagram", "path_or_url": "design/url.excalidraw"})
design.create_topic(
    {"title": "Parking lot", "kind": "lld", "patterns": ["strategy"], "status": "practiced",
     "confidence": 5}
)

gs = design.stats()
assert gs["total"] == 2 and gs["practiced"] == 2, gs
assert gs["artifacts"] == 1
assert len(design.revision_queue()) == 1
print("design OK  ", {k: gs[k] for k in ("total", "practiced", "completion_rate")})

# ------------------------------------------------------------------ prep
prep.upsert_phase({"key": "phase_1", "name": "Trees", "status": "completed", "order": 1})
prep.upsert_phase({"key": "phase_4", "name": "DP", "status": "current", "order": 4})
prep.update_profile({"target_companies": ["Acme Corp"], "target_levels": ["SWE2"]})

profile = prep.get_prep()
assert [ph["key"] for ph in profile["phases"]] == ["phase_1", "phase_4"], profile["phases"]
# Counts are joined in from dsa by phase key.
assert profile["phases"][1]["problems"] == 1 and profile["phases"][1]["solved"] == 1

# Setting one phase current must demote the other, or current_phase is ambiguous.
prep.set_phase_status("phase_1", "current")
after = prep.get_prep()
assert after["profile"]["current_phase"] == "phase_1", after["profile"]
assert next(p for p in after["phases"] if p["key"] == "phase_4")["status"] == "upcoming"
assert prep.set_phase_status("nope", "current") is None

prep.set_milestone("Milestone 2 - cycle detection")
assert prep.get_prep()["profile"]["current_milestone"].startswith("Milestone 2")

habit = prep.add_standing_issue("Forgets to return the recursive call", "logic")
prep.flag_standing_issue(habit["id"], problem_id=p["id"])
prep.flag_standing_issue(habit["id"], problem_id=two_sum["id"])
typo = prep.add_standing_issue("Uses [r, c] in a set", "syntax")
assert prep.list_standing_issues()[0]["id"] == habit["id"], "most recurrent should sort first"
assert len(prep.list_standing_issues(active_only=True)) == 2

prep.resolve_standing_issue(typo["id"])
resolved = next(i for i in prep.list_standing_issues() if i["id"] == typo["id"])
assert resolved["active"] is False and resolved["date_resolved"], resolved
assert len(prep.list_standing_issues(active_only=True)) == 1

# Flagging a resolved habit reopens it -- the whole point of tracking recurrence.
prep.flag_standing_issue(typo["id"])
assert prep.list_standing_issues(active_only=True).__len__() == 2

ps = prep.stats()
assert ps["current_phase"] == "Trees", ps["current_phase"]
assert ps["phases_completed"] == 0 and ps["phases_total"] == 2, ps
assert ps["standing_issues_active"] == 2, ps
assert ps["recurring"][0]["times_seen"] == 2, ps["recurring"]
assert prep.delete_standing_issue(typo["id"]) is True
assert prep.delete_standing_issue("nope") is False
print("prep OK    ", {k: ps[k] for k in ("current_phase", "standing_issues_active")})

# ------------------------------------------------------------------ readiness
storage.add_round(job["id"], {"name": "Onsite", "date": "2099-01-01", "result": "pending"})
ready = prep.readiness()
assert len(ready["upcoming_rounds"]) == 1, ready["upcoming_rounds"]
assert ready["upcoming_rounds"][0]["organisation"] == "Acme Corp"
assert ready["next_round_in_days"] > 0
# Acme is live but nothing is tagged to it, which is exactly the gap to surface.
assert "Acme Corp" in ready["untagged_companies"], ready
assert [x["title"] for x in ready["dsa_stuck"]] == ["Median of Two Sorted Arrays"]

dsa.update_problem(two_sum["id"], {"company_tags": ["acme corp"]})
ready = prep.readiness()
coverage = next(c for c in ready["company_coverage"] if c["organisation"] == "Acme Corp")
assert coverage["dsa_tagged"] == 1 and coverage["dsa_solved"] == 1, coverage
assert "Acme Corp" not in ready["untagged_companies"]
print("readiness OK", {k: ready[k] for k in ("next_round_in_days", "dsa_missing_complexity")})

# ------------------------------------------------------------------ next up
# phase_1 ("Trees") is current at this point. Two fresh todos: one inside the
# current phase, one with no phase at all.
in_phase = dsa.create_problem(
    {"title": "Validate BST", "difficulty": "medium", "status": "todo", "phase": "phase_1"}
)
backlog = dsa.create_problem({"title": "Two Pointers Warmup", "difficulty": "easy"})

nxt = dsa.next_up()
assert [n["title"] for n in nxt] == [
    "Median of Two Sorted Arrays",  # stuck -- unblock before starting anything
    "Validate BST",  # todo, current phase
    "Two Pointers Warmup",  # todo, no phase, so it sorts below despite being easy
], [n["title"] for n in nxt]
assert "stuck" in nxt[0]["reason"], nxt[0]["reason"]
assert nxt[1]["in_current_phase"] and "Trees" in nxt[1]["reason"], nxt[1]
assert nxt[2]["in_current_phase"] is False, nxt[2]

# The two queues must stay disjoint: next_up() is "attempt this", the revision
# queue is "re-solve this". A solved problem can never appear here.
assert all(n["status"] in dsa.NEXT_UP_RANK for n in nxt), nxt
assert not {n["id"] for n in nxt} & {r["id"] for r in dsa.revision_queue()}

# Open work outranks the plan -- finish what is started before starting more.
dsa.update_problem(backlog["id"], {"status": "in_progress"})
assert dsa.next_up()[0]["title"] == "Two Pointers Warmup", dsa.next_up()
assert dsa.next_up()[0]["days_open"] == 0, dsa.next_up()[0]
assert len(dsa.next_up(limit=1)) == 1
dsa.delete_problem(in_phase["id"])
dsa.delete_problem(backlog["id"])
print("next up OK ", [n["title"] for n in nxt])

# ------------------------------------------------------------------ coach
# Nothing open, no entrenched habit yet, nothing due for revision: the coach
# falls through to the curriculum and behaves like next_up().
c = dsa.coach()
assert c["kind"] == "advance" and c["pick"]["title"].startswith("Median"), c

# Deferring pulls it off every queue but leaves a checkable way back in.
median_id = next(p["id"] for p in dsa.list_problems() if p["title"].startswith("Median"))
gate = dsa.create_problem({"title": "In-degree warmup", "difficulty": "easy", "phase": "phase_1"})
held = dsa.defer_problem(median_id, "too far ahead of the fundamentals", [gate["id"]])
assert held["status"] == "deferred" and held["defer"]["until_solved"] == [gate["id"]], held
assert not any(n["title"].startswith("Median") for n in dsa.next_up()), dsa.next_up()

c = dsa.coach()
assert [h["title"] for h in c["on_hold"]] == ["Median of Two Sorted Arrays"], c["on_hold"]
assert c["on_hold"][0]["blockers"] == ["In-degree warmup"], c["on_hold"]
assert c["kind"] == "advance" and c["pick"]["title"] == "In-degree warmup", c

# Solving the prerequisite reopens it on its own -- nobody has to remember.
dsa.update_problem(gate["id"], {"status": "solved", "confidence": 5})
c = dsa.coach()
assert c["kind"] == "unlocked" and c["pick"]["title"].startswith("Median"), c
assert c["on_hold"] == [] and len(c["unlocked"]) == 1, c

# Leaving deferred must clear the gate, or a live problem still reads as held.
assert dsa.update_problem(median_id, {"status": "todo"})["defer"] is None

# Open work outranks the plan.
dsa.update_problem(gate["id"], {"status": "in_progress"})
assert dsa.coach()["kind"] == "finish", dsa.coach()
dsa.update_problem(gate["id"], {"status": "solved"})

# A habit seen three times outranks the curriculum -- and the drill is a
# *different* problem on the same concept, because reproducing an answer you
# have already seen tests recall, not whether the idea transferred.
prep.flag_standing_issue(habit["id"], problem_id=two_sum["id"])
assert len(prep.list_standing_issues()[0]["seen_on"]) == 3
same_concept = dsa.create_problem(
    {"title": "Contains Duplicate", "difficulty": "easy", "topics": ["hashmap"]}
)
c = dsa.coach()
assert c["kind"] == "drill" and c["pick"]["action"] == "solve", c
assert c["pick"]["title"] == "Contains Duplicate", c["pick"]
assert any("recurred 3x" in b for b in c["because"]), c["because"]

# With nothing unsolved on that concept, the drill falls back to a redo.
dsa.delete_problem(same_concept["id"])
c = dsa.coach()
assert c["kind"] == "drill" and c["pick"]["action"] == "redo", c
assert c["pick"]["title"] == "Two Sum", c["pick"]

# Habit beaten, but three solves since the last revisit: revision cadence wins.
prep.resolve_standing_issue(habit["id"])
dsa.update_problem(two_sum["id"], {"confidence": 2})
c = dsa.coach()
assert c["kind"] == "revise" and c["pick"]["action"] == "redo", c
assert c["solved_since_last_revisit"] >= dsa.REVISE_EVERY, c
print("coach OK   ", {k: c[k] for k in ("kind", "revision_due")})

# ------------------------------------------------------------------ stopwatch
import datetime as _dt  # noqa: E402

timed = dsa.create_problem({"title": "Timed problem", "difficulty": "easy"})
assert timed["elapsed_seconds"] == 0 and timed["timer"]["started_at"] is None, timed

# Start is the clock *and* the status change -- two clicks is how a timer ends
# up never being used.
running = dsa.set_timer(timed["id"], "start")
assert running["status"] == "in_progress" and running["date_started"], running
assert running["timer"]["started_at"], running["timer"]
assert dsa.stats()["timer_running"]["id"] == timed["id"], dsa.stats()["timer_running"]

# Backdate the running segment rather than sleeping -- the selftest stays fast.
def _rewind(problem_id, seconds):
    data = dsa.load()
    for record in data[dsa.KEY]:
        if record["id"] == problem_id and record["timer"]["started_at"]:
            record["timer"]["started_at"] = (
                _dt.datetime.now() - _dt.timedelta(seconds=seconds)
            ).isoformat(timespec="seconds")
    dsa.write(dsa.FILE, data)

_rewind(timed["id"], 300)
assert 299 <= dsa.get_problem(timed["id"])["elapsed_seconds"] <= 302, dsa.get_problem(timed["id"])

paused = dsa.set_timer(timed["id"], "pause")
assert paused["timer"]["started_at"] is None, paused["timer"]
assert 299 <= paused["timer"]["accumulated_seconds"] <= 302, paused["timer"]
assert dsa.stats()["timer_running"] is None

# Paused time is not counted, and resuming adds to the total rather than
# restarting it -- that is the whole point of having a pause.
dsa.set_timer(timed["id"], "start")
_rewind(timed["id"], 120)
banked = dsa.update_problem(timed["id"], {"status": "solved"})
assert banked["timer"]["started_at"] is None, banked["timer"]
assert 419 <= banked["timer"]["accumulated_seconds"] <= 423, banked["timer"]
assert banked["time_spent_minutes"] == 7, banked["time_spent_minutes"]

# A hand-entered figure is an explicit act and must survive the roll-up.
manual = dsa.create_problem({"title": "Solved offline", "time_spent_minutes": 45})
dsa.set_timer(manual["id"], "start")
_rewind(manual["id"], 90)
manual = dsa.update_problem(manual["id"], {"status": "solved"})
assert manual["time_spent_minutes"] == 45, manual["time_spent_minutes"]

# A timer left running overnight would wreck avg_time_minutes on its own, so a
# single segment is banked at the cap and flagged rather than silently trusted.
forgotten = dsa.create_problem({"title": "Left running"})
dsa.set_timer(forgotten["id"], "start")
_rewind(forgotten["id"], (dsa.STALE_SEGMENT_HOURS + 9) * 3600)
forgotten = dsa.set_timer(forgotten["id"], "pause")
assert forgotten["timer"]["capped"] is True, forgotten["timer"]
assert forgotten["timer"]["accumulated_seconds"] == dsa.STALE_SEGMENT_HOURS * 3600, forgotten

assert dsa.set_timer(forgotten["id"], "reset")["elapsed_seconds"] == 0
try:
    dsa.set_timer(forgotten["id"], "rewind")
    raise AssertionError("an unknown timer action must not be accepted")
except ValueError:
    pass

# elapsed_seconds is derived, so it must never reach the file.
raw = json.loads((tmp / "dsa.json").read_text(encoding="utf-8"))
assert all("elapsed_seconds" not in p for p in raw["problems"]), "derived field was persisted"
print("stopwatch OK", {k: dsa.stats()[k] for k in ("avg_time_minutes", "timed")})

# ------------------------------------------------------------- patterns
import pattern_seed  # noqa: E402
import patterns  # noqa: E402

# The join key is namespaced by host: LeetCode and GfG both publish
# /problems/<slug>, and unnamespaced they would claim each other's problems.
assert patterns.slug_of("https://leetcode.com/problems/two-sum/description/") == "leetcode:two-sum"
assert patterns.slug_of("https://www.geeksforgeeks.org/problems/two-sum/1") == "geeksforgeeks:two-sum"
assert patterns.slug_of("https://leetcode.com/problems/two-sum/") != patterns.slug_of(
    "https://www.geeksforgeeks.org/problems/two-sum/1"
), "two sites must not share a slug"
assert patterns.slug_of("https://example.com/blog/two-sum") is None
# His titles carry the LeetCode number; the sheet's do not.
assert patterns.norm_title("LC 207 - Course Schedule") == patterns.norm_title("Course Schedule")
assert patterns.norm_title("leetcode 200: Number of Islands") == "numberofislands"

patterns.seed(
    [
        {
            "key": "sliding_window",
            "name": "Sliding Window",
            "domain": "dsa",
            "order": 1,
            "idea": "Both ends only move forward.",
            "problems": [
                {
                    "title": "Longest Substring Without Repeating Characters",
                    "url": "https://leetcode.com/problems/longest-substring-without-repeating-characters/",
                    "difficulty": "medium",
                },
                {"title": "Two Sum", "url": None},
                {"title": "Minimum Window Substring", "url": None, "difficulty": "hard"},
            ],
        },
        {
            "key": "hld_caching",
            "name": "Caching",
            "domain": "hld",
            "order": 2,
            "idea": "Every cache design is an invalidation design.",
            "problems": [{"title": "Design a news feed", "url": None}],
        },
    ]
)
again = patterns.seed(pattern_seed.PATTERNS)
assert again["skipped"] == 2 and again["added"] == len(pattern_seed.PATTERNS) - 2, again
assert patterns.seed(pattern_seed.PATTERNS)["added"] == 0, "seeding must be idempotent"

window = patterns.get_pattern("sliding_window")
# "Two Sum" has no URL in this catalogue, so it can only match by title -- and
# there is a solved Two Sum from the dsa section above.
by_title = next(q for q in window["problems"] if q["title"] == "Two Sum")
assert by_title["tracked"] and by_title["solved"], by_title
assert window["solved"] == 1 and window["total"] == 3, window
assert window["state"] == "learning" and window["coverage"] == 33.3, window

# A fresh solve joins by slug across two differently-worded titles.
lss = dsa.create_problem(
    {
        "title": "LC 3 - Longest Substring Without Repeating Characters",
        "url": "https://leetcode.com/problems/longest-substring-without-repeating-characters/description/",
        "status": "solved",
        "topics": ["sliding-window"],
        "confidence": 5,
    }
)
window = patterns.get_pattern("sliding_window")
assert window["solved"] == 2 and window["coverage"] == 66.7, window
assert window["state"] == "practiced", window["state"]
assert patterns.for_problem(lss["url"]) == [
    {"key": "sliding_window", "name": "Sliding Window", "domain": "dsa"}
], patterns.for_problem(lss["url"])

# Covered, never rated and never revisited -- that is the one due reason a
# freshly finished pattern can have, and re-deriving it is what clears it.
assert window["due"] and window["due_reason"] == "covered but never rated or revisited", window
patterns.log_revisit("sliding_window", "re-derived the shrink condition", confidence=4)
window = patterns.get_pattern("sliding_window")
assert not window["due"] and window["confidence"] == 4 and window["last_revised"], window

# A flag forces it back; a revisit is what takes it out again.
patterns.update_pattern("sliding_window", {"flagged": True})
assert patterns.get_pattern("sliding_window")["due_reason"] == "flagged for revision"
patterns.log_revisit("sliding_window", "clean second pass", confidence=5)
after = patterns.get_pattern("sliding_window")
assert not after["flagged"] and not after["due"], after

# Nothing untouched is ever due, a hand-set flag included -- that is what keeps
# the two queues disjoint by construction rather than by convention.
patterns.update_pattern("kadane", {"flagged": True})
assert patterns.get_pattern("kadane")["due"] is False, "an untouched pattern must not be due"
due_keys = {q["key"] for q in patterns.revision_queue()}
new_keys = {q["key"] for q in patterns.unstarted()}
assert not (due_keys & new_keys), due_keys & new_keys

# Solved work tagged with a pattern but not listed under it counts as activity,
# and deliberately NOT toward coverage -- a denominator that grows on tagging
# is a percentage that means nothing.
dsa.create_problem(
    {"title": "Fruit Into Baskets", "status": "solved", "topics": ["sliding-window"]}
)
after = patterns.get_pattern("sliding_window")
assert after["extra_solved"] == 1 and after["total"] == 3, after
assert after["coverage"] == 66.7, "off-catalogue work must not move coverage"

# Promotion queues a catalogue row as real work, tagged so it joins back.
promoted = patterns.promote("sliding_window", 2)
assert promoted["domain"] == "dsa"
assert promoted["record"]["status"] == "todo" and promoted["record"]["topics"] == ["sliding-window"]
assert promoted["record"]["difficulty"] == "hard", "the sheet's difficulty carries through"
assert promoted["record"]["phase"] is None, "pattern study must not claim a curriculum phase"
assert patterns.get_pattern("sliding_window")["problems"][2]["tracked"]
try:
    patterns.promote("sliding_window", 2)
    raise AssertionError("promoting an already-tracked problem must fail")
except ValueError:
    pass

design_side = patterns.promote("hld_caching", 0)
assert design_side["domain"] == "hld" and design_side["record"]["kind"] == "hld"
cache = patterns.get_pattern("hld_caching")
assert cache["tracked"] == 1 and cache["solved"] == 0, cache
design.update_topic(design_side["record"]["id"], {"status": "practiced"})
cache = patterns.get_pattern("hld_caching")
assert cache["solved"] == 1 and cache["state"] == "practiced", cache

try:
    patterns.add_problem("sliding_window", {"title": "two sum"})
    raise AssertionError("a duplicate catalogue title must be rejected")
except ValueError:
    pass

# Every progress number is joined at read time; none of it may be persisted.
raw = json.loads((tmp / "patterns.json").read_text(encoding="utf-8"))
derived = {"solved", "total", "coverage", "state", "due", "tracked", "extra_solved"}
assert all(not derived & set(p) for p in raw["patterns"]), "a derived field was persisted"
assert all("id" not in q for p in raw["patterns"] for q in p["problems"]), "catalogue rows are not records"

# The shipped curriculum itself: keys unique, order dense, every idea written.
keys = [p["key"] for p in pattern_seed.PATTERNS]
assert len(set(keys)) == len(keys), "duplicate pattern key in the seed"
assert [p["order"] for p in pattern_seed.PATTERNS] == list(range(1, len(keys) + 1))
for entry in pattern_seed.PATTERNS:
    assert entry["domain"] in patterns.DOMAINS, entry["key"]
    assert entry["idea"].strip(), f"{entry['key']} has no idea written"
    assert entry["problems"], f"{entry['key']} has no problems"

ps = patterns.stats()
assert ps["total"] == len(pattern_seed.PATTERNS), ps
assert ps["due"] + ps["unstarted"] <= ps["total"], ps
print(
    f"patterns OK {ps['total']} patterns, {ps['problems']} problems, "
    f"{ps['due']} due, {ps['unstarted']} unstarted"
)

# ------------------------------------------------------- companies + discovery
import companies  # noqa: E402
import company_seed  # noqa: E402
import discover  # noqa: E402

acme = companies.create_company(
    {
        "name": "Acme Corp",
        "category": "startup",
        "tier": "growth",
        "locations": ["Bengaluru"],
        "status": "target",
        "interest": 5,
    }
)
assert acme["applications"] == 1, acme  # the job created at the top of this file
assert acme["board_column"] == "applied", "a live application must beat the manual status"

# Name matching: postings carry legal entities, so a long name matches by
# prefix — but a short one must not, or "Ola" would claim every Olam job.
assert companies.matches(acme, "Acme Corp Private Limited")
assert companies.matches(acme, "acme corp")
short = companies.create_company({"name": "Zap", "aliases": ["Zap Technologies"]})
assert not companies.matches(short, "Zapier Inc"), "short names must match exactly"
assert companies.matches(short, "Zap Technologies Private Limited"), "aliases match by prefix"
assert companies.find_company("zap technologies")["name"] == "Zap"

try:
    companies.create_company({"name": "ACME CORP"})
    raise AssertionError("duplicate company should have been rejected")
except ValueError:
    pass

added = companies.seed(company_seed.SEED)
assert added["added"] == len(company_seed.SEED), added
again = companies.seed(company_seed.SEED)
assert again["added"] == 0 and again["skipped"] == len(company_seed.SEED), again

board = companies.list_companies()
assert len(board) == len(company_seed.SEED) + 2, len(board)
# Sorted by interest descending, so the one thing wanted at 5/5 leads.
assert board[0]["name"] == "Acme Corp", board[0]["name"]
assert all(c["ats_token"] for c in companies.fetchable()), "a wired company needs a token"

# A provider without a token can't be fetched and must not claim it can.
lying = companies.create_company({"name": "No Token Ltd", "ats_provider": "greenhouse"})
assert lying["ats_provider"] == "none", lying

cstats = companies.stats()
assert cstats["total"] == len(board) + 1, cstats["total"]
assert cstats["with_ats"] == len(companies.fetchable())
assert cstats["applied_to"] >= 1
gaps = [g["name"] for g in companies.target_gaps()]
assert "Acme Corp" not in gaps, "a target with an application is not a gap"
companies.update_company(short["id"], {"status": "target", "interest": 4})
assert "Zap" in [g["name"] for g in companies.target_gaps()]
print(f"companies OK {cstats['total']} on board, {cstats['with_ats']} wired")

# --- discovery: pure parsing, no network -----------------------------------
# Shapes mirror the live responses; each provider names things differently and
# only Lever dates in epoch milliseconds.
GREENHOUSE = {
    "jobs": [
        {
            "title": "Software Engineer II",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": {"name": "Bengaluru, India"},
            "first_published": "2026-07-20T04:52:12-04:00",
            "updated_at": "2026-07-30T00:00:00-04:00",
            "content": "&lt;p&gt;Build &amp;amp; scale services&lt;/p&gt;",
        },
        {
            "title": "Staff Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
            "location": {"name": "San Francisco"},
            "first_published": "2026-07-21T00:00:00-04:00",
        },
    ]
}
LEVER = [
    {
        "text": "Backend Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "categories": {"location": "Bengaluru", "department": "Engineering"},
        "createdAt": 1784539800000,  # 2026-07-20T09:30Z, in epoch milliseconds
        "descriptionPlain": "Go and Kafka.",
    }
]
ASHBY = {
    "jobs": [
        {
            "title": "ML Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/xyz",
            "location": "Bengaluru",
            "secondaryLocations": [{"location": "Chennai"}],
            "publishedAt": "2026-06-29T17:12:35.753+00:00",
            "isListed": True,
            "department": "Research",
        },
        {"title": "Hidden Role", "jobUrl": "https://x/y", "location": "Bengaluru", "isListed": False},
    ]
}

gh = discover.parse("greenhouse", GREENHOUSE, acme)
assert [r["title"] for r in gh] == ["Software Engineer II", "Staff Engineer"]
assert gh[0]["posted"] == "2026-07-20", "first_published wins over updated_at"
assert "Build & scale services" in gh[0]["description"], gh[0]["description"]
lv = discover.parse("lever", LEVER, acme)
assert lv[0]["posted"] == "2026-07-20", lv[0]["posted"]  # epoch ms -> ISO day
ash = discover.parse("ashby", ASHBY, acme)
assert [r["title"] for r in ash] == ["ML Engineer"], "isListed False must be dropped"
assert ash[0]["locations"] == ["Bengaluru", "Chennai"]

# Seniority is word-boundary matched. An earlier version looked for "i " and
# read "Principal AI Security Specialist" as entry level.
for title, want in [
    ("Principal AI Security Specialist", "senior"),
    ("Sr. Staff Software Development Engineer - AI Engineer", "senior"),
    ("Engineering Manager, AI", "senior"),
    ("Software Engineer II", "mid"),
    ("Associate Software Engineer", "entry"),
    ("Associate Director, Platform", "senior"),
    ("Senior Data Science Intern", "intern"),
    # The AI labs title every IC level this way; reading it as senior would
    # hide their whole board from a SWE2 search.
    ("Member of Technical Staff", "mid"),
]:
    assert discover.guess_seniority(title) == want, (title, discover.guess_seniority(title))

# Keywords anchor at the start of a word, so "ai" must not match "Retail".
assert not discover.matches_keywords({"title": "Retail Ops Manager", "department": ""}, ["ai"])
assert discover.matches_keywords({"title": "Engineering Manager", "department": ""}, ["engineer"])

everything = gh + lv + ash
india = discover.filter_roles(everything, keywords=["engineer"], exclude_seniority=["senior"])
# "Staff Engineer" is dropped twice over: senior, and San Francisco.
assert [r["title"] for r in india] == [
    "Software Engineer II",
    "Backend Engineer",
    "ML Engineer",
], india
assert discover.filter_roles(everything, keywords=["sales"]) == []
# Sales titles are dropped by default even when they match an engineering word.
noise = [{**gh[0], "title": "Sales Engineer", "url": "https://x/s"}]
assert discover.filter_roles(noise, keywords=["engineer"]) == []

undated = [{**gh[0], "posted": None}]
assert discover.filter_roles(undated, max_age_days=1), "undated postings must not be hidden"
assert not discover.filter_roles(gh[:1], max_age_days=1, as_of=jsonstore.date.today())

remote = [{**gh[1], "locations": ["Remote"], "remote": True, "seniority": "mid"}]
assert not discover.filter_roles(remote), "remote is opt-in"
assert discover.filter_roles(remote, include_remote=True)

# Dedupe: against what's tracked, by url and by (organisation, title).
# The Lever fixture is "Backend Engineer" at Acme Corp, which is the very job
# created at the top of this file — so a real tracked record must hide it.
kept, already = discover.dedupe(everything, storage.list_jobs())
assert already == 1, already
assert "Backend Engineer" not in [r["title"] for r in kept], kept
tracked = [{"url": gh[0]["url"], "organisation": "", "job_title": ""}]
kept, already = discover.dedupe(everything, tracked)
assert already == 1 and len(kept) == 3, (already, len(kept))
by_title = [{"url": None, "organisation": "Acme Corp", "job_title": "backend engineer"}]
_, already = discover.dedupe(everything, by_title)
assert already == 1, "a hand-added record has no url, so title matching must catch it"
twice = discover.dedupe(everything + everything, [])[0]
assert len(twice) == 4, "the same role listed twice collapses"

promoted = discover.to_job(lv[0])
assert promoted["status"] == "saved", "discovery finds leads, not applications"
assert promoted["source"] == "careers_page"
assert promoted["organisation"] == "Acme Corp" and promoted["date_job_posted"] == "2026-07-20"
print(f"discovery OK {len(everything)} parsed, {len(india)} after filters")

# ------------------------------------------------------------------ prompt
import ai  # noqa: E402

prompt = ai.system_prompt()
# The prompt carries LaTeX macro examples; an f-string would eat the braces and
# every chat turn would die before reaching the model.
for literal in (
    r"\resumeSubheading{org}{right}{role}{date}",
    r"\pdfgentounicode=1",
    r"O(n \log n)",
):
    assert literal in prompt, f"mangled in prompt: {literal}"
names = {tool.name for tool in ai.TOOLS}
import re  # noqa: E402

for candidate in set(
    re.findall(r"\b(?:add|get|list|log|update|save|link|set|flag|resolve)_[a-z_]+\b", prompt)
):
    assert candidate in names, f"prompt references a missing tool: {candidate}"
assert ai.build_options(None).system_prompt == prompt
print(f"prompt OK   {len(names)} tools, {len(prompt)} chars")

# The Windows loop bridge: uvicorn --reload hands us a SelectorEventLoop, which
# cannot spawn the CLI subprocess. Losing this bridge breaks every chat turn
# while leaving the rest of the app working, so it is easy to miss.
assert hasattr(ai, "_needs_proactor_bridge"), "Windows event-loop bridge is gone"
assert not ai._needs_proactor_bridge(), "no running loop should mean no bridge"


async def _is_bridged() -> bool:
    return ai._needs_proactor_bridge()


if sys.platform == "win32":
    selector_loop = asyncio.SelectorEventLoop()
    try:
        assert selector_loop.run_until_complete(_is_bridged()), "selector loop must bridge"
    finally:
        selector_loop.close()
    proactor_loop = asyncio.ProactorEventLoop()
    try:
        assert not proactor_loop.run_until_complete(_is_bridged()), "proactor needs no bridge"
    finally:
        proactor_loop.close()
    print("loop bridge OK  selector->bridged, proactor->direct")

print("\nALL CHECKS PASSED")
