"""DSA problem practice tracking — data/dsa.json.

Tracks when a problem was started and finished, how much effort it took, and
— the point of the whole thing — what went wrong, so weak topics surface and
low-confidence problems come back around in the revision queue.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, parse_date, pct, read, today, write

FILE = "dsa.json"
KEY = "problems"
_lock = lock_for(FILE)

PLATFORMS = ["leetcode", "codeforces", "gfg", "hackerrank", "codechef", "other"]
DIFFICULTIES = ["easy", "medium", "hard"]
DSA_STATUSES = ["todo", "in_progress", "solved", "revisit", "stuck"]

SOLVED_STATUSES = {"solved", "revisit"}

# A solved problem is due for revision below this confidence, or after this gap.
LOW_CONFIDENCE = 3
REVISIT_AFTER_DAYS = 21

_DEFAULTS: dict[str, Any] = {
    "title": "",
    "platform": "leetcode",
    "url": None,
    "difficulty": "medium",
    "topics": [],
    "status": "todo",
    "date_started": None,
    "date_completed": None,
    "time_spent_minutes": None,
    "attempts": 0,
    "used_hint": False,
    "issues": [],
    "solution_notes": "",
    # Complexity is graded in every FAANG loop, so it is a first-class field
    # rather than prose buried in solution_notes. Stored as LaTeX math without
    # the delimiters -- "O(n \\log n)" -- so it renders in the dashboard and
    # pastes straight into a write-up.
    "time_complexity": "",
    "space_complexity": "",
    # Which curriculum phase in prep.json this problem belongs to.
    "phase": None,
    "confidence": None,
    "revisits": [],
    "company_tags": [],
    "linked_job_id": None,
}


def _normalize(problem: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(problem, _DEFAULTS)
    for issue in out["issues"]:
        issue.setdefault("date", out.get("date_started") or today())
        issue.setdefault("issue", "")
    for revisit in out["revisits"]:
        revisit.setdefault("date", today())
        revisit.setdefault("outcome", "")
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = [_normalize(p) for p in data[KEY]]
    return data


def list_problems() -> list[dict[str, Any]]:
    return load()[KEY]


def get_problem(problem_id: str) -> dict[str, Any] | None:
    return next((p for p in load()[KEY] if p["id"] == problem_id), None)


def find_problems(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        p
        for p in load()[KEY]
        if needle in p["title"].lower() or any(needle in t.lower() for t in p["topics"])
    ]


def create_problem(payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        problem = _normalize({**payload, "id": new_id()})
        # Starting a problem stamps the start date; solving stamps completion.
        if problem["status"] in ("in_progress", *SOLVED_STATUSES) and not problem["date_started"]:
            problem["date_started"] = today()
        if problem["status"] in SOLVED_STATUSES and not problem["date_completed"]:
            problem["date_completed"] = today()
        data[KEY].append(problem)
        write(FILE, data)
        return problem


def update_problem(problem_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            updated = {**problem, **{k: v for k, v in patch.items() if k != "id"}}
            status = updated.get("status")
            if status in ("in_progress", *SOLVED_STATUSES) and not updated.get("date_started"):
                updated["date_started"] = today()
            if status in SOLVED_STATUSES and not updated.get("date_completed"):
                updated["date_completed"] = today()
            if status in ("todo", "stuck"):
                # Moving back out of solved clears the completion stamp.
                updated["date_completed"] = None
            data[KEY][idx] = _normalize(updated)
            write(FILE, data)
            return data[KEY][idx]
        return None


def delete_problem(problem_id: str) -> bool:
    with _lock:
        data = load()
        remaining = [p for p in data[KEY] if p["id"] != problem_id]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        write(FILE, data)
        return True


def log_issue(problem_id: str, issue: str, on: str | None = None) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            problem["issues"].append({"date": on or today(), "issue": issue})
            data[KEY][idx] = _normalize(problem)
            write(FILE, data)
            return data[KEY][idx]
        return None


def log_revisit(
    problem_id: str, outcome: str, confidence: int | None = None, on: str | None = None
) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            problem["revisits"].append({"date": on or today(), "outcome": outcome})
            if confidence is not None:
                problem["confidence"] = confidence
            if problem["status"] == "revisit":
                problem["status"] = "solved"
            data[KEY][idx] = _normalize(problem)
            write(FILE, data)
            return data[KEY][idx]
        return None


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------


def _last_touched(problem: dict[str, Any]) -> date | None:
    candidates = [
        parse_date(problem.get("date_completed")),
        parse_date(problem.get("date_started")),
    ]
    candidates += [parse_date(r.get("date")) for r in problem.get("revisits", [])]
    real = [c for c in candidates if c]
    return max(real) if real else None


def _has_complexity(problem: dict[str, Any]) -> bool:
    return bool(problem.get("time_complexity")) and bool(problem.get("space_complexity"))


def _days_to_solve(problem: dict[str, Any]) -> int | None:
    started = parse_date(problem.get("date_started"))
    done = parse_date(problem.get("date_completed"))
    if started and done:
        return (done - started).days
    return None


def stats() -> dict[str, Any]:
    problems = list_problems()
    total = len(problems)
    solved = [p for p in problems if p["status"] in SOLVED_STATUSES]

    by_status = {status: 0 for status in DSA_STATUSES}
    for problem in problems:
        by_status[problem["status"]] = by_status.get(problem["status"], 0) + 1

    by_difficulty = {}
    for level in DIFFICULTIES:
        at_level = [p for p in problems if p["difficulty"] == level]
        solved_at_level = [p for p in at_level if p["status"] in SOLVED_STATUSES]
        by_difficulty[level] = {
            "total": len(at_level),
            "solved": len(solved_at_level),
            "solve_rate": pct(len(solved_at_level), len(at_level)),
        }

    topics: dict[str, dict[str, Any]] = {}
    for problem in problems:
        for topic in problem["topics"] or ["untagged"]:
            bucket = topics.setdefault(
                topic, {"total": 0, "solved": 0, "stuck": 0, "hints": 0, "issues": 0}
            )
            bucket["total"] += 1
            if problem["status"] in SOLVED_STATUSES:
                bucket["solved"] += 1
            if problem["status"] == "stuck":
                bucket["stuck"] += 1
            if problem["used_hint"]:
                bucket["hints"] += 1
            bucket["issues"] += len(problem["issues"])
    for bucket in topics.values():
        bucket["solve_rate"] = pct(bucket["solved"], bucket["total"])

    # Weakest topics = most struggle signals per problem attempted.
    weak_topics = sorted(
        (
            {"topic": name, **bucket}
            for name, bucket in topics.items()
            if bucket["total"] >= 1
        ),
        key=lambda t: (t["solve_rate"], -(t["issues"] + t["stuck"] + t["hints"])),
    )[:5]

    by_phase: dict[str, dict[str, Any]] = {}
    for problem in problems:
        bucket = by_phase.setdefault(
            problem["phase"] or "unassigned", {"total": 0, "solved": 0, "stuck": 0}
        )
        bucket["total"] += 1
        if problem["status"] in SOLVED_STATUSES:
            bucket["solved"] += 1
        if problem["status"] == "stuck":
            bucket["stuck"] += 1
    for bucket in by_phase.values():
        bucket["solve_rate"] = pct(bucket["solved"], bucket["total"])

    times = [p["time_spent_minutes"] for p in solved if p.get("time_spent_minutes")]
    attempts = [p["attempts"] for p in solved if p.get("attempts")]
    spans = [d for d in (_days_to_solve(p) for p in solved) if d is not None]

    cutoff = date.today() - timedelta(days=28)
    recent = [
        p
        for p in solved
        if (parse_date(p.get("date_completed")) or date.today()) >= cutoff
    ]

    return {
        "total": total,
        "solved": len(solved),
        "solve_rate": pct(len(solved), total),
        "in_progress": by_status.get("in_progress", 0),
        "stuck": by_status.get("stuck", 0),
        "by_status": by_status,
        "status_percentages": {k: pct(v, total) for k, v in by_status.items()},
        "by_difficulty": by_difficulty,
        "by_topic": dict(sorted(topics.items())),
        "by_phase": dict(sorted(by_phase.items())),
        "weak_topics": weak_topics,
        # A solve with no complexity stated is an incomplete rep by FAANG
        # standards, so it gets counted rather than passing silently.
        "missing_complexity": sum(1 for p in solved if not _has_complexity(p)),
        "avg_time_minutes": round(sum(times) / len(times), 1) if times else 0,
        "avg_attempts": round(sum(attempts) / len(attempts), 1) if attempts else 0,
        "avg_days_to_solve": round(sum(spans) / len(spans), 1) if spans else 0,
        "hint_rate": pct(sum(1 for p in solved if p["used_hint"]), len(solved)),
        "issues_logged": sum(len(p["issues"]) for p in problems),
        "solved_last_28_days": len(recent),
        "solved_per_week": round(len(recent) / 4, 1),
        "revision_due": len(revision_queue()),
    }


def missing_complexity() -> list[dict[str, Any]]:
    """Solved problems with no complexity recorded — an annotation gap, not a
    practice gap, so it is kept out of the revision queue."""
    return [
        {
            "id": p["id"],
            "title": p["title"],
            "difficulty": p["difficulty"],
            "time_complexity": p["time_complexity"],
            "space_complexity": p["space_complexity"],
        }
        for p in list_problems()
        if p["status"] in SOLVED_STATUSES and not _has_complexity(p)
    ]


def revision_queue() -> list[dict[str, Any]]:
    """Solved problems that are shaky or stale — redo these."""
    current = date.today()
    out = []
    for problem in list_problems():
        if problem["status"] == "revisit":
            reason = "flagged for revisit"
        elif problem["status"] in SOLVED_STATUSES:
            confidence = problem.get("confidence")
            touched = _last_touched(problem)
            days = (current - touched).days if touched else None
            if confidence is not None and confidence <= LOW_CONFIDENCE:
                reason = f"low confidence ({confidence}/5)"
            elif days is not None and days >= REVISIT_AFTER_DAYS:
                reason = f"not revisited in {days} days"
            elif problem.get("used_hint") and not problem["revisits"]:
                reason = "solved with a hint, never redone"
            else:
                # A missing complexity analysis is deliberately NOT a reason to
                # be here. This queue means "re-solve this"; an unannotated
                # solve needs a one-line note, not another attempt. It is
                # counted in stats()["missing_complexity"] and listed by
                # missing_complexity() instead.
                continue
        else:
            continue

        touched = _last_touched(problem)
        out.append(
            {
                "id": problem["id"],
                "title": problem["title"],
                "platform": problem["platform"],
                "url": problem["url"],
                "difficulty": problem["difficulty"],
                "topics": problem["topics"],
                "phase": problem["phase"],
                "time_complexity": problem["time_complexity"],
                "space_complexity": problem["space_complexity"],
                "confidence": problem.get("confidence"),
                "days_since_touched": (current - touched).days if touched else None,
                "reason": reason,
                "issues": problem["issues"],
            }
        )
    out.sort(key=lambda p: (p["confidence"] or 0, -(p["days_since_touched"] or 0)))
    return out
