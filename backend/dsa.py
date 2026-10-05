"""DSA problem practice tracking — data/dsa.json.

Tracks when a problem was started and finished, how much effort it took, and
— the point of the whole thing — what went wrong, so weak topics surface and
low-confidence problems come back around in the revision queue.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, parse_date, pct, read, today, write

FILE = "dsa.json"
KEY = "problems"
_lock = lock_for(FILE)

PLATFORMS = ["leetcode", "codeforces", "gfg", "hackerrank", "codechef", "other"]
DIFFICULTIES = ["easy", "medium", "hard"]
DSA_STATUSES = ["todo", "in_progress", "solved", "revisit", "stuck", "deferred"]

SOLVED_STATUSES = {"solved", "revisit"}

# A solved problem is due for revision below this confidence, or after this gap.
LOW_CONFIDENCE = 3
REVISIT_AFTER_DAYS = 21

# Statuses that mean "not attempted, or attempted and unfinished", ranked in the
# order they should be picked up: finish what is already open before starting
# something new, and a stuck problem outranks a fresh one because the rep that
# is currently blocked is the one teaching something.
NEXT_UP_RANK = {"in_progress": 0, "stuck": 1, "todo": 2}

# A ranked list of twenty things to do next is a backlog, not a decision.
NEXT_UP_LIMIT = 5

# A habit that has resurfaced this many times across unrelated problems is not a
# slip any more, it is how the code gets written under pressure. Stacking new
# material on top of it just manufactures more instances of the same mistake.
DRILL_AFTER_RECURRENCES = 3

# New solves allowed between revisits. Without a cadence the revision queue only
# grows: everything is eventually "stale enough", and new work always feels
# better than old work, so the redo never happens.
REVISE_EVERY = 3

# One continuous stopwatch segment longer than this is a timer someone forgot,
# not a four-hour sitting. It is banked at the cap instead of its real length,
# because a single overnight timer would wreck avg_time_minutes — and that
# average is the only reason the stopwatch exists.
STALE_SEGMENT_HOURS = 4

# One attempt gets this long on the clock. Past it, more grinding stops teaching:
# the solution is shown, the attempt is written down, and the problem comes back
# cold REVISIT_AFTER_CAP_DAYS later to be re-derived rather than recalled. The
# cap is per attempt, so ending one zeroes the clock -- a return visit that
# started already over the line would hand the solution straight back.
ATTEMPT_CAP_MINUTES = 40
REVISIT_AFTER_CAP_DAYS = 14

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
    # Set aside deliberately, with the condition for bringing it back. A `stuck`
    # problem you keep staring at stalls the phase and quietly becomes a wall;
    # a deferred one is off the queue with a stated, checkable way back in.
    # {"reason", "until_solved": [problem_id], "review_on": date | None}
    "defer": None,
    # The stopwatch. `started_at` is the current running segment (None when
    # paused), `accumulated_seconds` is every segment already banked. Server
    # side rather than in the browser, because a refresh, a second tab and the
    # chat agent must all see the same clock.
    "timer": {"started_at": None, "accumulated_seconds": 0, "capped": False},
}


def _normalize(problem: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(problem, _DEFAULTS)
    for issue in out["issues"]:
        issue.setdefault("date", out.get("date_started") or today())
        issue.setdefault("issue", "")
    for revisit in out["revisits"]:
        revisit.setdefault("date", today())
        revisit.setdefault("outcome", "")
    timer = dict(out.get("timer") or {})
    timer.setdefault("started_at", None)
    timer.setdefault("accumulated_seconds", 0)
    timer.setdefault("capped", False)
    out["timer"] = timer
    if out["status"] == "deferred":
        gate = dict(out.get("defer") or {})
        gate.setdefault("reason", "")
        gate.setdefault("until_solved", [])
        gate.setdefault("review_on", None)
        out["defer"] = gate
    else:
        # The gate is meaningless off a deferred problem, and leaving one behind
        # would make a resurfaced problem still look like it is on hold.
        out["defer"] = None
    return out


# --------------------------------------------------------------------------
# the stopwatch
# --------------------------------------------------------------------------
#
# Timer stamps carry a time of day, unlike every other date in this file — a
# stopwatch cannot work at day resolution. ISO 8601 to the second.


def _now_stamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_stamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def elapsed_seconds(problem: dict[str, Any]) -> int:
    """Banked time plus whatever the running segment has added so far."""
    timer = problem.get("timer") or {}
    total = int(timer.get("accumulated_seconds") or 0)
    started = _parse_stamp(timer.get("started_at"))
    if started:
        total += max(0, int((datetime.now() - started).total_seconds()))
    return total


def _bank(problem: dict[str, Any]) -> None:
    """Roll the running segment into the total and stop the clock.

    A segment over STALE_SEGMENT_HOURS is banked at the cap rather than its
    real length, with `capped` set so the number stays auditable instead of
    quietly wrong.
    """
    timer = problem["timer"]
    started = _parse_stamp(timer.get("started_at"))
    if not started:
        return
    seconds = max(0, int((datetime.now() - started).total_seconds()))
    if seconds > STALE_SEGMENT_HOURS * 3600:
        seconds = STALE_SEGMENT_HOURS * 3600
        timer["capped"] = True
    timer["accumulated_seconds"] = int(timer.get("accumulated_seconds") or 0) + seconds
    timer["started_at"] = None


def _over_attempt_cap(problem: dict[str, Any]) -> bool:
    """An open attempt whose clock has reached ATTEMPT_CAP_MINUTES.

    Running or paused both count: a clock paused for review at 45 minutes
    crossed the line before the solution arrived.
    """
    return (
        problem.get("status") == "in_progress"
        and elapsed_seconds(problem) >= ATTEMPT_CAP_MINUTES * 60
    )


def _public(problem: dict[str, Any]) -> dict[str, Any]:
    """A copy with the live stopwatch reading attached.

    Deliberately not done in `_normalize`, which also runs on the write path —
    a derived number that gets persisted is one that will eventually disagree
    with what derives it.
    """
    return {
        **problem,
        "elapsed_seconds": elapsed_seconds(problem),
        "over_attempt_cap": _over_attempt_cap(problem),
    }


def over_attempt_cap() -> list[dict[str, Any]]:
    """Open attempts past the cap -- each one is owed its solution now."""
    return [_public(p) for p in load()[KEY] if _over_attempt_cap(p)]


def cap_attempt(problem_id: str, on: str | None = None) -> dict[str, Any] | None:
    """End an attempt that ran past ATTEMPT_CAP_MINUTES.

    The solution is being shown, so this is where the attempt gets written
    down: its length goes into `issues[]` (the clock is about to be zeroed, so
    this is the only record of it), `attempts` counts it, and `used_hint` is
    set because an eventual solve will not have been unaided. Then the problem
    is deferred with a review date, which is what brings it back.
    """
    stamp = on or today()
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            _bank(problem)
            minutes = round(int(problem["timer"]["accumulated_seconds"] or 0) / 60)
            problem["issues"].append(
                {
                    "date": stamp,
                    "issue": f"Hit the {ATTEMPT_CAP_MINUTES}-minute attempt cap "
                    f"after {minutes} min; solution shown.",
                }
            )
            problem["attempts"] = int(problem.get("attempts") or 0) + 1
            problem["used_hint"] = True
            problem["timer"] = {"started_at": None, "accumulated_seconds": 0, "capped": False}
            problem["status"] = "deferred"
            problem["defer"] = {
                "reason": f"Attempt capped at {ATTEMPT_CAP_MINUTES} min on {stamp}; "
                "solution shown. Re-derive from scratch -- derivation, not recall.",
                "until_solved": [],
                "review_on": (
                    date.fromisoformat(stamp) + timedelta(days=REVISIT_AFTER_CAP_DAYS)
                ).isoformat(),
            }
            data[KEY][idx] = _normalize(problem)
            write(FILE, data)
            return _public(data[KEY][idx])
        return None


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = [_normalize(p) for p in data[KEY]]
    return data


def list_problems() -> list[dict[str, Any]]:
    return [_public(p) for p in load()[KEY]]


def get_problem(problem_id: str) -> dict[str, Any] | None:
    return next((p for p in list_problems() if p["id"] == problem_id), None)


def find_problems(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        p
        for p in list_problems()
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
        return _public(problem)


def update_problem(problem_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            updated = _normalize({**problem, **{k: v for k, v in patch.items() if k != "id"}})
            status = updated.get("status")
            if status in ("in_progress", *SOLVED_STATUSES) and not updated.get("date_started"):
                updated["date_started"] = today()
            if status in SOLVED_STATUSES and not updated.get("date_completed"):
                updated["date_completed"] = today()
            if status in ("todo", "stuck", "deferred"):
                # Moving back out of solved clears the completion stamp.
                updated["date_completed"] = None
            if status in SOLVED_STATUSES:
                _bank(updated)
                banked = int(updated["timer"]["accumulated_seconds"] or 0)
                # The stopwatch only fills the field in when it actually ran,
                # and never over a figure already there: a hand-entered time
                # for a problem solved away from the app is an explicit act.
                if banked and not updated.get("time_spent_minutes"):
                    updated["time_spent_minutes"] = max(1, round(banked / 60))
            data[KEY][idx] = _normalize(updated)
            write(FILE, data)
            return _public(data[KEY][idx])
        return None


def set_timer(problem_id: str, action: str) -> dict[str, Any] | None:
    """Drive the stopwatch: `start` (or resume), `pause`, `reset`.

    Starting also moves the problem into `in_progress` and stamps its start
    date — pressing start *is* beginning the problem, and making that two
    separate clicks is how a timer ends up never being used.
    """
    if action not in ("start", "pause", "reset"):
        raise ValueError("action must be start, pause or reset")
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            if action == "start":
                if not problem["timer"]["started_at"]:
                    problem["timer"]["started_at"] = _now_stamp()
                if problem["status"] in ("todo", "stuck", "deferred"):
                    problem["status"] = "in_progress"
                if not problem["date_started"]:
                    problem["date_started"] = today()
            elif action == "pause":
                _bank(problem)
            else:
                problem["timer"] = {
                    "started_at": None,
                    "accumulated_seconds": 0,
                    "capped": False,
                }
            data[KEY][idx] = _normalize(problem)
            write(FILE, data)
            return _public(data[KEY][idx])
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


def defer_problem(
    problem_id: str,
    reason: str,
    until_solved: list[str] | None = None,
    review_on: str | None = None,
) -> dict[str, Any] | None:
    """Take a problem off the queue with a stated condition for its return.

    The condition is the whole point. "Come back to it later" is a note to
    nobody; `until_solved` is checkable, so the problem resurfaces on its own
    the moment its prerequisites land, without anyone remembering to look.
    """
    return update_problem(
        problem_id,
        {
            "status": "deferred",
            "defer": {
                "reason": reason,
                "until_solved": until_solved or [],
                "review_on": review_on,
            },
        },
    )


def log_issue(problem_id: str, issue: str, on: str | None = None) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, problem in enumerate(data[KEY]):
            if problem["id"] != problem_id:
                continue
            problem["issues"].append({"date": on or today(), "issue": issue})
            data[KEY][idx] = _normalize(problem)
            write(FILE, data)
            return _public(data[KEY][idx])
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
            return _public(data[KEY][idx])
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
        # How much of the average is actually measured rather than guessed at.
        "timed": len(times),
        # A stopwatch nobody can see from the other tabs is a stopwatch left
        # running, so the running one is surfaced rather than left to be found.
        "timer_running": next(
            (
                {
                    "id": p["id"],
                    "title": p["title"],
                    "elapsed_seconds": elapsed_seconds(p),
                    # The raw block too, so a chip elsewhere in the UI can keep
                    # counting between polls instead of freezing for 30s.
                    "timer": p["timer"],
                }
                for p in problems
                if (p.get("timer") or {}).get("started_at")
            ),
            None,
        ),
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


def next_up(limit: int = NEXT_UP_LIMIT) -> list[dict[str, Any]]:
    """What to open next — work that has never been finished, ranked.

    Deliberately disjoint from `revision_queue()`. That queue means "re-solve
    something you already solved"; this one means "attempt something you have
    not". Merged into one list, "redo LC 102" and "start LC 733" compete for
    the same slot and the redo always loses, so both signals get weaker.

    The current curriculum phase is the primary sort after status, because the
    phase *is* the plan — a queue that ignores it is just the backlog re-sorted
    by difficulty. Problems outside the current phase still appear, below
    everything in it, so the list never goes empty while work remains.

    Each entry carries the number, title and topics and nothing else: no
    solution notes, no approach, no complexity. The assistant's interview mode
    gives a LeetCode number and a title and stops, and the dashboard must not
    be the leak that undoes that restraint.
    """
    import prep  # noqa: PLC0415 -- local, so the domain modules stay independent

    profile = prep.load()
    current_key = profile["profile"].get("current_phase")
    phase_names = {p["key"]: p["name"] for p in profile[prep.KEY]}
    current_name = phase_names.get(current_key) or "the current phase"

    difficulty_rank = {level: n for n, level in enumerate(DIFFICULTIES)}
    current = date.today()
    ranked: list[tuple[tuple[int, int, int, int], dict[str, Any]]] = []

    # File order is the curriculum order the problems were added in, so it is
    # the honest tie-breaker — better than inventing a secondary heuristic.
    for order, problem in enumerate(list_problems()):
        status = problem["status"]
        if status not in NEXT_UP_RANK:
            continue
        in_phase = bool(current_key) and problem["phase"] == current_key
        started = parse_date(problem.get("date_started"))

        if status == "in_progress":
            reason = "already in progress — finish this first"
        elif status == "stuck":
            reason = "stuck — unblock this before starting anything new"
        elif in_phase:
            reason = f"next in {current_name}"
        else:
            reason = "backlog — outside the current phase"

        ranked.append(
            (
                (
                    NEXT_UP_RANK[status],
                    0 if in_phase else 1,
                    difficulty_rank.get(problem["difficulty"], len(DIFFICULTIES)),
                    order,
                ),
                {
                    "id": problem["id"],
                    "title": problem["title"],
                    "platform": problem["platform"],
                    "url": problem["url"],
                    "difficulty": problem["difficulty"],
                    "topics": problem["topics"],
                    "phase": problem["phase"],
                    "status": status,
                    "in_current_phase": in_phase,
                    "days_open": (current - started).days if started else None,
                    "reason": reason,
                },
            )
        )

    ranked.sort(key=lambda entry: entry[0])
    return [entry for _, entry in ranked[:limit]]


# --------------------------------------------------------------------------
# the coach — one recommendation, and the evidence behind it
# --------------------------------------------------------------------------


def _blockers(
    problem: dict[str, Any], by_id: dict[str, Any], solved: set[str], current: date
) -> list[str]:
    """Why a deferred problem is still on hold. Empty means it is ready."""
    gate = problem.get("defer") or {}
    out = [
        by_id[pid]["title"] if pid in by_id else pid
        for pid in gate.get("until_solved") or []
        if pid not in solved
    ]
    review_on = parse_date(gate.get("review_on"))
    if review_on and current < review_on:
        out.append(f"not before {gate['review_on']}")
    return out


def _recommendation(problem: dict[str, Any], action: str) -> dict[str, Any]:
    """The shape every pick takes.

    Carries the number, title and topics and nothing else — same restraint as
    next_up(). A recommendation points at a problem; it is not a head start.
    """
    return {
        "id": problem["id"],
        "title": problem["title"],
        "action": action,  # "solve" | "redo"
        "platform": problem["platform"],
        "url": problem["url"],
        "difficulty": problem["difficulty"],
        "topics": problem["topics"],
        "phase": problem["phase"],
        "status": problem["status"],
        # So the card can drive the stopwatch without a second lookup.
        "timer": problem["timer"],
        "elapsed_seconds": elapsed_seconds(problem),
    }


def coach() -> dict[str, Any]:
    """One recommendation: the single thing to do next, with its evidence.

    `next_up()` and `revision_queue()` stay separate lists on purpose — merged,
    the redo always loses. This picks *between* them, which is a different job:
    a queue answers "what is outstanding", this answers "what now".

    The order is weakness-first, not curriculum-first. A habit that has recurred
    three times across unrelated problems is a concept that has not landed, and
    new material stacked on top of it only manufactures more instances of the
    same mistake. Where a drill is called for, a *different* problem exercising
    the same concept beats re-solving the original: reproducing an answer you
    have already seen tests recall, and recall is not the goal — being able to
    derive it on an unfamiliar problem is.

    Every branch appends to `because`. A recommendation you cannot audit is one
    you will start ignoring the first time it looks wrong.
    """
    import prep  # noqa: PLC0415 -- local, so the domain modules stay independent

    problems = list_problems()
    by_id = {p["id"]: p for p in problems}
    solved = {p["id"] for p in problems if p["status"] in SOLVED_STATUSES}
    current = date.today()

    on_hold: list[dict[str, Any]] = []
    unlocked: list[dict[str, Any]] = []
    for problem in problems:
        if problem["status"] != "deferred":
            continue
        blockers = _blockers(problem, by_id, solved, current)
        entry = {
            "id": problem["id"],
            "title": problem["title"],
            "difficulty": problem["difficulty"],
            "phase": problem["phase"],
            "reason": (problem["defer"] or {}).get("reason", ""),
            "blockers": blockers,
        }
        (on_hold if blockers else unlocked).append(entry)

    # Revision cadence, measured in solves rather than days: days punish a slow
    # week, solves track the thing that actually creates revision debt.
    revisit_dates = [
        parse_date(r["date"]) for p in problems for r in p["revisits"] if parse_date(r["date"])
    ]
    last_revisit = max(revisit_dates, default=None)
    solved_since = sum(
        1
        for p in problems
        if p["status"] in SOLVED_STATUSES
        and (last_revisit is None or (parse_date(p["date_completed"]) or current) >= last_revisit)
    )

    habits = prep.list_standing_issues(active_only=True)  # most-recurrent first
    entrenched = next((h for h in habits if len(h["seen_on"]) >= DRILL_AFTER_RECURRENCES), None)

    because: list[str] = []
    kind, pick, reason = "idle", None, "Nothing queued. Add problems, or advance the phase."

    open_now = next((p for p in problems if p["status"] == "in_progress"), None)

    if unlocked:
        # The whole reason for deferring rather than leaving something stuck:
        # it comes back on a condition, not on somebody remembering.
        target = by_id[unlocked[0]["id"]]
        kind = "unlocked"
        pick = _recommendation(target, "solve")
        reason = "Everything this was waiting on is now solved."
        because.append(f"set aside because: {unlocked[0]['reason']}")

    elif open_now:
        kind = "finish"
        pick = _recommendation(open_now, "solve")
        reason = "Already open. Finish it before starting anything new."

    elif entrenched:
        seen = sorted(
            (s for s in entrenched["seen_on"] if s.get("problem_id") in by_id),
            key=lambda s: s.get("date") or "",
        )
        origin = by_id[seen[-1]["problem_id"]] if seen else None
        times = len(entrenched["seen_on"])
        because.append(f"\"{entrenched['issue']}\" has recurred {times}x")

        # A different problem on the same concept, if one is waiting. Same idea,
        # unfamiliar surface — that is what tells you the concept transferred
        # rather than the solution being remembered.
        fresh = next(
            (
                p
                for p in problems
                if p["status"] in NEXT_UP_RANK
                and origin is not None
                and p["id"] != origin["id"]
                and set(p["topics"]) & set(origin["topics"])
            ),
            None,
        )
        if fresh is not None:
            kind = "drill"
            pick = _recommendation(fresh, "solve")
            reason = "Same concept as where that habit keeps appearing, different problem."
            because.append(f"last seen on {origin['title']}")
            because.append(f"shares {', '.join(sorted(set(fresh['topics']) & set(origin['topics'])))}")
        elif origin is not None and origin["status"] in SOLVED_STATUSES:
            kind = "drill"
            pick = _recommendation(origin, "redo")
            reason = "Redo this one unaided — it is where the habit last showed up."
            because.append("no unsolved problem shares its topics, so the rep is a redo")

    if pick is None and revision_queue() and solved_since >= REVISE_EVERY:
        due = revision_queue()[0]
        kind = "revise"
        pick = _recommendation(by_id[due["id"]], "redo")
        reason = due["reason"]
        because.append(
            f"{solved_since} solved since the last revisit"
            if last_revisit
            else f"{solved_since} solved and no revisit ever logged"
        )

    if pick is None:
        ahead = next_up(limit=1)
        if ahead:
            kind = "advance"
            pick = _recommendation(by_id[ahead[0]["id"]], "solve")
            reason = ahead[0]["reason"]

    # Deliberately not folded into `because`: on_hold is a first-class field, so
    # repeating it as prose only makes the evidence list longer to read.
    return {
        "kind": kind,
        "pick": pick,
        "reason": reason,
        "because": because,
        "unlocked": unlocked,
        "on_hold": on_hold,
        "solved_since_last_revisit": solved_since,
        "revision_due": len(revision_queue()),
    }
