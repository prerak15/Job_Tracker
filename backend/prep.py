"""Interview-prep profile — data/prep.json.

Everything in dsa.py and design.py is scoped to a single problem or topic. This
module holds the state that sits *above* individual problems: which curriculum
phase is in flight, and the standing mistakes that keep resurfacing across
different problems.

Standing issues are the reason this file exists. A per-problem `issues[]` entry
records what went wrong *that time*; a standing issue is a habit ("returns the
recursive call's result instead of returning it directly") that shows up again
on unrelated problems. Those need one home and a recurrence count, otherwise
the same lesson is re-learned every few weeks and nothing tracks it.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, pct, read, today, write

FILE = "prep.json"
KEY = "phases"
_lock = lock_for(FILE)

PHASE_STATUSES = ["completed", "current", "upcoming"]

# What kind of mistake it is — drives which ones are worth drilling vs. which
# are a linter's job.
ISSUE_CATEGORIES = ["logic", "syntax", "complexity", "style", "process"]

_PROFILE_DEFAULTS: dict[str, Any] = {
    "target_levels": [],
    "target_companies": [],
    "current_phase": None,
    "current_milestone": "",
    "notes": "",
}

_PHASE_DEFAULTS: dict[str, Any] = {
    "key": "",
    "name": "",
    "status": "upcoming",
    "order": 0,
    "topics": [],
    "milestone": "",
}

_ISSUE_DEFAULTS: dict[str, Any] = {
    "issue": "",
    "category": "logic",
    "active": True,
    "date_added": None,
    "seen_on": [],
    "date_resolved": None,
}


def _normalize_phase(phase: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(phase, _PHASE_DEFAULTS)
    if out["status"] not in PHASE_STATUSES:
        out["status"] = "upcoming"
    return out


def _normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(issue, _ISSUE_DEFAULTS)
    if out["category"] not in ISSUE_CATEGORIES:
        out["category"] = "logic"
    if not out["date_added"]:
        out["date_added"] = today()
    # A resolved issue is never also active — the flag and the date can't
    # disagree, whichever way a hand-edit set them.
    if out["date_resolved"]:
        out["active"] = False
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = sorted(
        (_normalize_phase(p) for p in data[KEY]), key=lambda p: (p["order"], p["name"])
    )
    data["standing_issues"] = [
        _normalize_issue(i) for i in data.get("standing_issues") or []
    ]
    profile = dict(data.get("profile") or {})
    for field, default in _PROFILE_DEFAULTS.items():
        if profile.get(field) is None:
            profile[field] = copy.deepcopy(default)
    data["profile"] = profile
    return data


def get_prep() -> dict[str, Any]:
    """The whole profile, with per-phase problem counts joined in from dsa.

    dsa.json is read once and bucketed, not re-read per phase — this runs on
    every dashboard load.
    """
    import dsa  # local import keeps the domain modules independent of each other

    data = load()
    counts: dict[str, dict[str, int]] = {}
    for problem in dsa.list_problems():
        bucket = counts.setdefault(problem.get("phase"), {"problems": 0, "solved": 0})
        bucket["problems"] += 1
        if problem["status"] in dsa.SOLVED_STATUSES:
            bucket["solved"] += 1

    for phase in data[KEY]:
        bucket = counts.get(phase["key"], {"problems": 0, "solved": 0})
        phase["problems"] = bucket["problems"]
        phase["solved"] = bucket["solved"]
        phase["solve_rate"] = pct(bucket["solved"], bucket["problems"])
    return data


# --------------------------------------------------------------------------
# profile + phases
# --------------------------------------------------------------------------


def update_profile(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        data["profile"].update({k: v for k, v in patch.items() if v is not None})
        write(FILE, data)
        return get_prep()


def set_phase_status(phase_key: str, status: str) -> dict[str, Any] | None:
    """Mark a phase completed/current/upcoming.

    Setting one phase current demotes whatever was current before — two phases
    in flight would make `current_phase` ambiguous for the assistant.
    """
    if status not in PHASE_STATUSES:
        raise ValueError(f"status must be one of {PHASE_STATUSES}")
    with _lock:
        data = load()
        target = next((p for p in data[KEY] if p["key"] == phase_key), None)
        if target is None:
            return None
        if status == "current":
            for phase in data[KEY]:
                if phase["key"] != phase_key and phase["status"] == "current":
                    phase["status"] = "upcoming"
            data["profile"]["current_phase"] = phase_key
        target["status"] = status
        if status != "current" and data["profile"].get("current_phase") == phase_key:
            data["profile"]["current_phase"] = None
        write(FILE, data)
        return get_prep()


def upsert_phase(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a phase, or update it in place when the key already exists."""
    with _lock:
        data = load()
        key = payload.get("key") or new_id()
        payload = {**payload, "key": key}
        for idx, phase in enumerate(data[KEY]):
            if phase["key"] == key:
                data[KEY][idx] = _normalize_phase({**phase, **payload})
                break
        else:
            data[KEY].append(_normalize_phase(payload))
        write(FILE, data)
        return get_prep()


def set_milestone(milestone: str, phase_key: str | None = None) -> dict[str, Any]:
    with _lock:
        data = load()
        data["profile"]["current_milestone"] = milestone
        key = phase_key or data["profile"].get("current_phase")
        for phase in data[KEY]:
            if phase["key"] == key:
                phase["milestone"] = milestone
        write(FILE, data)
        return get_prep()


# --------------------------------------------------------------------------
# standing issues
# --------------------------------------------------------------------------


def list_standing_issues(active_only: bool = False) -> list[dict[str, Any]]:
    issues = load()["standing_issues"]
    if active_only:
        issues = [i for i in issues if i["active"]]
    # Most-recurrent first: those are the habits actually costing interviews.
    return sorted(issues, key=lambda i: (-len(i["seen_on"]), i["date_added"] or ""))


def add_standing_issue(
    issue: str, category: str = "logic", on: str | None = None
) -> dict[str, Any]:
    if category not in ISSUE_CATEGORIES:
        raise ValueError(f"category must be one of {ISSUE_CATEGORIES}")
    with _lock:
        data = load()
        record = _normalize_issue(
            {
                "id": new_id(),
                "issue": issue,
                "category": category,
                "date_added": on or today(),
            }
        )
        data["standing_issues"].append(record)
        write(FILE, data)
        return record


def flag_standing_issue(
    issue_id: str, on: str | None = None, problem_id: str | None = None
) -> dict[str, Any] | None:
    """Record that a known habit resurfaced. Reopens it if it was resolved."""
    with _lock:
        data = load()
        for idx, record in enumerate(data["standing_issues"]):
            if record["id"] != issue_id:
                continue
            record["seen_on"].append(
                {"date": on or today(), "problem_id": problem_id}
            )
            record["active"] = True
            record["date_resolved"] = None
            data["standing_issues"][idx] = _normalize_issue(record)
            write(FILE, data)
            return data["standing_issues"][idx]
        return None


def resolve_standing_issue(issue_id: str, on: str | None = None) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, record in enumerate(data["standing_issues"]):
            if record["id"] != issue_id:
                continue
            record["date_resolved"] = on or today()
            record["active"] = False
            data["standing_issues"][idx] = _normalize_issue(record)
            write(FILE, data)
            return data["standing_issues"][idx]
        return None


def delete_standing_issue(issue_id: str) -> bool:
    with _lock:
        data = load()
        remaining = [i for i in data["standing_issues"] if i["id"] != issue_id]
        if len(remaining) == len(data["standing_issues"]):
            return False
        data["standing_issues"] = remaining
        write(FILE, data)
        return True


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------


def readiness() -> dict[str, Any]:
    """What to drill before the interviews that are actually on the calendar.

    This is the one view that joins all four domains: a scheduled round in
    jobs.json is the deadline, and the DSA queue, design queue and standing
    weaknesses are what you have to turn up with. Prep coverage is matched by
    company tag, so tagging practice with a company is what makes it show here.
    """
    import design  # noqa: PLC0415
    import dsa  # noqa: PLC0415
    import storage  # noqa: PLC0415
    from jsonstore import parse_date  # noqa: PLC0415

    current = date.today()
    upcoming: list[dict[str, Any]] = []
    awaiting: list[dict[str, Any]] = []
    live_orgs: dict[str, str] = {}

    for job in storage.list_jobs():
        if job["status"] in ("interviewing", "applied"):
            live_orgs[job["organisation"].strip().lower()] = job["organisation"]
        for rnd in job.get("rounds", []):
            if rnd.get("result") not in ("pending", "waiting"):
                continue
            when = parse_date(rnd.get("date"))
            if not when:
                continue
            entry = {
                "job_id": job["id"],
                "organisation": job["organisation"],
                "job_title": job["job_title"],
                "round": rnd.get("round"),
                "name": rnd.get("name"),
                "date": rnd.get("date"),
                "days": (when - current).days,
            }
            live_orgs.setdefault(job["organisation"].strip().lower(), job["organisation"])
            (upcoming if when >= current else awaiting).append(entry)

    upcoming.sort(key=lambda r: r["date"])
    awaiting.sort(key=lambda r: r["date"], reverse=True)

    problems = dsa.list_problems()
    topics = design.list_topics()
    coverage = []
    for key, label in sorted(live_orgs.items(), key=lambda kv: kv[1].lower()):
        tagged_problems = [
            p for p in problems if any(t.strip().lower() == key for t in p["company_tags"])
        ]
        tagged_topics = [
            t for t in topics if any(c.strip().lower() == key for c in t["company_tags"])
        ]
        coverage.append(
            {
                "organisation": label,
                "dsa_tagged": len(tagged_problems),
                "dsa_solved": sum(
                    1 for p in tagged_problems if p["status"] in dsa.SOLVED_STATUSES
                ),
                "design_tagged": len(tagged_topics),
                "design_practiced": sum(
                    1 for t in tagged_topics if t["status"] in design.DONE_STATUSES
                ),
            }
        )

    return {
        "upcoming_rounds": upcoming,
        "awaiting_result": awaiting,
        "next_round_in_days": upcoming[0]["days"] if upcoming else None,
        "company_coverage": coverage,
        # Companies you are live with but have zero tagged practice against.
        "untagged_companies": [
            c["organisation"]
            for c in coverage
            if not c["dsa_tagged"] and not c["design_tagged"]
        ],
        "dsa_revision_due": len(dsa.revision_queue()),
        "design_revision_due": len(design.revision_queue()),
        "dsa_missing_complexity": len(dsa.missing_complexity()),
        "dsa_stuck": [
            {"id": p["id"], "title": p["title"]}
            for p in problems
            if p["status"] == "stuck"
        ],
        "design_stuck": [
            {"id": t["id"], "title": t["title"]}
            for t in topics
            if t["status"] == "stuck"
        ],
        "active_standing_issues": sum(1 for i in load()["standing_issues"] if i["active"]),
    }


def stats() -> dict[str, Any]:
    data = get_prep()
    phases = data[KEY]
    issues = data["standing_issues"]
    active = [i for i in issues if i["active"]]

    by_category = {c: 0 for c in ISSUE_CATEGORIES}
    for issue in active:
        by_category[issue["category"]] = by_category.get(issue["category"], 0) + 1

    current = next((p for p in phases if p["status"] == "current"), None)
    return {
        "target_levels": data["profile"]["target_levels"],
        "target_companies": data["profile"]["target_companies"],
        "current_phase": current["name"] if current else None,
        "current_milestone": data["profile"]["current_milestone"],
        "phases_total": len(phases),
        "phases_completed": sum(1 for p in phases if p["status"] == "completed"),
        "curriculum_progress": pct(
            sum(1 for p in phases if p["status"] == "completed"), len(phases)
        ),
        "phase_progress": [
            {
                "key": p["key"],
                "name": p["name"],
                "status": p["status"],
                "problems": p["problems"],
                "solved": p["solved"],
                "solve_rate": p["solve_rate"],
            }
            for p in phases
        ],
        "standing_issues_total": len(issues),
        "standing_issues_active": len(active),
        "standing_issues_resolved": len(issues) - len(active),
        "standing_issues_by_category": by_category,
        "recurring": [
            {
                "id": i["id"],
                "issue": i["issue"],
                "category": i["category"],
                "times_seen": len(i["seen_on"]),
            }
            for i in sorted(active, key=lambda i: -len(i["seen_on"]))[:5]
        ],
    }
