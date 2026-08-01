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
