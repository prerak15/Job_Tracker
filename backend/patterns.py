"""Pattern revision across DSA and system design — data/patterns.json.

dsa.py and design.py track individual problems. prep.py tracks the curriculum
phase above them. This module is a third axis: the *technique* a problem
exercises, which cuts across both other domains and across every phase — two
pointers shows up in phase 1 and phase 4, and "what do I still not have" is a
question neither of the other two can answer.

The catalogue is seeded from `pattern_seed.py` (Prerak's own sheet for the DSA
half) and then owned by the file, so problems can be added or removed.

**Everything about progress is joined in at read time and never stored.**
A pattern's `solved`, `coverage`, `state` and whether it is due come from
dsa.json and design.json on every read, matched by URL slug. That is the same
choice companies.py makes against jobs.json, for the same reason: a second
copy of "have I done this" would eventually disagree with the tab that owns
it, and the wrong one would be the one being read. What the file *does* store
is what nothing else knows — the catalogue, a self-rated confidence, notes,
revisits, and an explicit flag.

Two lists, and like dsa.py's pair they must stay disjoint:

* `revision_queue()` — patterns with real work in them that has since decayed.
  Re-derive these.
* `unstarted()` — patterns with nothing solved at all. You cannot revise what
  you never learned, and merging the two means the never-started list, which is
  always longer, buries the revision that is actually due.

There is deliberately **no second coach here**. `dsa.coach()` answers "which
problem now" and stays the only thing that does; this module answers "which
technique has gone stale", which is a different question at a different
altitude. Two competing "do this next" cards would eventually disagree, and
the user would learn to ignore both.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, parse_date, pct, read, today, write

FILE = "patterns.json"
KEY = "patterns"
_lock = lock_for(FILE)

# "dsa" problems live in dsa.json; "lld"/"hld" study topics live in design.json.
DOMAINS = ["dsa", "lld", "hld"]

# Where a pattern stops being something you are learning and becomes something
# you are maintaining. Deliberately not 100%: the sheet lists challenge
# problems most people never finish, and a bar nobody reaches is a bar nobody
# aims at.
PRACTICED_COVERAGE = 60

# Same thresholds dsa.py uses, so "stale" means one thing across the app.
LOW_CONFIDENCE = 3
REVISE_AFTER_DAYS = 21

_DEFAULTS: dict[str, Any] = {
    "key": "",
    "name": "",
    "domain": "dsa",
    "order": 0,
    # The invariant that makes the technique correct — not a template and not
    # a recognition cue. See the note at the top of pattern_seed.py.
    "idea": "",
    "problems": [],
    # 1-5, self-rated. The one progress signal the joins cannot supply: you can
    # have solved every problem in a pattern and still not trust it.
    "confidence": None,
    "notes": "",
    "revisits": [],
    # Set by hand when something goes wrong in a mock or an interview, before
    # the cadence would have caught it.
    "flagged": False,
}

_PROBLEM_DEFAULTS: dict[str, Any] = {
    "title": "",
    "url": None,
    "difficulty": None,
    # The sub-heading this problem sits under in the sheet ("Kth", "Traversal").
    "group": None,
    "challenge": False,
    # Non-problem links from the sheet: an article, a video walkthrough.
    "refs": [],
}


def _normalize(pattern: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(pattern, _DEFAULTS)
    if out["domain"] not in DOMAINS:
        out["domain"] = "dsa"
    out["problems"] = [apply_defaults(p, _PROBLEM_DEFAULTS) for p in out["problems"]]
    for problem in out["problems"]:
        # A catalogue row is not a record with its own life — it has no dates,
        # no status and no id of its own. apply_defaults hands out an id to
        # everything, so drop it rather than let it look like one.
        problem.pop("id", None)
    for revisit in out["revisits"]:
        revisit.setdefault("date", today())
        revisit.setdefault("outcome", "")
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = sorted(
        (_normalize(p) for p in data[KEY]), key=lambda p: (p["order"], p["name"])
    )
    return data


# --------------------------------------------------------------------------
# matching a catalogue row to a tracked record
# --------------------------------------------------------------------------
#
# The slug is the join key, and it is namespaced by host: LeetCode and GfG both
# publish /problems/<slug>, and an unnamespaced key would let one site's problem
# claim the other's. Titles are the fallback for a record entered by hand with
# no URL on it.

_SLUG = re.compile(r"/problems/([^/?#]+)")
_HOST = re.compile(r"https?://(?:www\.)?([^/]+)")

# His own titles carry the LeetCode number ("LC 207 - Course Schedule"); the
# sheet's do not. Strip it so the two can still meet.
_LC_PREFIX = re.compile(r"^\s*(?:lc|leetcode)\s*\d+\s*[-:.]\s*", re.I)


def slug_of(url: str | None) -> str | None:
    if not url:
        return None
    found = _SLUG.search(url)
    if not found:
        return None
    host = _HOST.match(url)
    site = (host.group(1).split(".")[0] if host else "web").lower()
    return f"{site}:{found.group(1).lower()}"


def norm_title(title: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", _LC_PREFIX.sub("", title or "").lower())


def platform_of(url: str | None) -> str:
    if not url:
        return "none"
    host = _HOST.match(url)
    if not host:
        return "other"
    name = host.group(1).lower()
    if "leetcode" in name:
        return "leetcode"
    if "geeksforgeeks" in name:
        return "gfg"
    return "other"


def _dsa_index() -> tuple[dict[str, Any], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Tracked DSA problems, keyed by slug, by normalised title, and by topic."""
    import dsa  # noqa: PLC0415 -- local, so the domain modules stay independent

    by_slug: dict[str, Any] = {}
    by_title: dict[str, Any] = {}
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for problem in dsa.list_problems():
        # `touched` rides along on the index so decorating 26 patterns doesn't
        # re-read dsa.json 26 times — this runs on every dashboard load.
        stamps = [parse_date(problem.get(f)) for f in ("date_completed", "date_started")]
        entry = {
            "problem_id": problem["id"],
            "status": problem["status"],
            "solved": problem["status"] in dsa.SOLVED_STATUSES,
            "confidence": problem.get("confidence"),
            "difficulty": problem.get("difficulty"),
            "touched": max([s for s in stamps if s], default=None),
        }
        slug = slug_of(problem.get("url"))
        if slug:
            by_slug.setdefault(slug, entry)
        title = norm_title(problem.get("title"))
        if title:
            by_title.setdefault(title, entry)
        for topic in problem["topics"]:
            by_topic.setdefault(norm_title(topic), []).append(entry)
    return by_slug, by_title, by_topic


def _design_index() -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Design topics, bucketed by the pattern key they are tagged with.

    Tagging is what makes a design topic count, and `promote` sets the tag —
    so anything created from this tab joins back without a second step.
    """
    import design  # noqa: PLC0415

    by_pattern: dict[str, list[dict[str, Any]]] = {}
    by_title: dict[str, Any] = {}
    for topic in design.list_topics():
        stamps = [parse_date(topic.get(f)) for f in ("date_completed", "date_started")]
        entry = {
            "problem_id": topic["id"],
            "status": topic["status"],
            "solved": topic["status"] in design.DONE_STATUSES,
            "confidence": topic.get("confidence"),
            "difficulty": None,
            "touched": max([s for s in stamps if s], default=None),
        }
        for tag in [*topic["patterns"], *topic["concepts"]]:
            by_pattern.setdefault(norm_title(tag), []).append(entry)
        title = norm_title(topic.get("title"))
        if title:
            by_title.setdefault(title, entry)
    return by_pattern, by_title


_UNTRACKED = {
    "problem_id": None,
    "status": None,
    "solved": False,
    "confidence": None,
    "touched": None,
}


def _decorate(
    pattern: dict[str, Any],
    dsa_slugs: dict[str, Any],
    dsa_titles: dict[str, Any],
    dsa_topics: dict[str, list[dict[str, Any]]],
    design_tags: dict[str, list[dict[str, Any]]],
    design_titles: dict[str, Any],
    current: date,
) -> dict[str, Any]:
    """Attach live progress. Nothing computed here is ever written back."""
    is_dsa = pattern["domain"] == "dsa"
    by_title = dsa_titles if is_dsa else design_titles
    problems: list[dict[str, Any]] = []
    touched: list[date] = []
    for problem in pattern["problems"]:
        slug = slug_of(problem["url"])
        match = (dsa_slugs.get(slug) if is_dsa and slug else None) or by_title.get(
            norm_title(problem["title"])
        )
        if match and match["touched"]:
            touched.append(match["touched"])
        problems.append(
            {
                **problem,
                "slug": slug,
                "platform": platform_of(problem["url"]),
                **{k: v for k, v in (match or _UNTRACKED).items() if k != "touched"},
                "tracked": match is not None,
            }
        )

    # Work tagged with this pattern that is not in the catalogue at all — a
    # design topic, or a DSA problem carrying the pattern as a topic. It counts
    # as evidence that the technique is in use, but deliberately NOT toward
    # coverage: the catalogue is the curriculum, and a denominator that grows
    # every time something is tagged is a percentage that means nothing.
    tags = dsa_topics if is_dsa else design_tags
    aliases = {norm_title(pattern["key"]), norm_title(pattern["name"])}
    seen = {p["problem_id"] for p in problems if p["problem_id"]}
    extra = []
    for alias in aliases:
        for entry in tags.get(alias, []):
            if entry["problem_id"] not in seen:
                seen.add(entry["problem_id"])
                extra.append(entry)

    total = len(problems)
    solved = sum(1 for p in problems if p["solved"])
    tracked = sum(1 for p in problems if p["tracked"])
    extra_solved = sum(1 for e in extra if e["solved"])

    # When work last happened *in this pattern*, from whichever domain owns it.
    touched += [e["touched"] for e in extra if e["touched"]]
    revised = [d for d in (parse_date(r.get("date")) for r in pattern["revisits"]) if d]
    last_worked = max([*touched, *revised], default=None)
    last_revised = max(revised, default=None)

    coverage = pct(solved, total)
    if not solved and not extra_solved:
        state = "untouched"
    elif coverage >= PRACTICED_COVERAGE:
        state = "practiced"
    else:
        state = "learning"

    days_since_worked = (current - last_worked).days if last_worked else None
    confidence = pattern.get("confidence")

    # Progress and decay are kept as separate facts. Folding them into one word
    # ("rusty") loses which half is the problem — a pattern can be well covered
    # and stale, or fresh and barely started, and those need different actions.
    #
    # Nothing untouched is ever due, a hand-set flag included: you cannot revise
    # what you never learned. That is what keeps revision_queue() and
    # unstarted() disjoint by construction rather than by convention.
    due_reason = None
    if state != "untouched":
        if pattern["flagged"]:
            due_reason = "flagged for revision"
        elif confidence is not None and confidence <= LOW_CONFIDENCE:
            due_reason = f"low confidence ({confidence}/5)"
        elif days_since_worked is not None and days_since_worked >= REVISE_AFTER_DAYS:
            due_reason = f"nothing worked in {days_since_worked} days"
        elif confidence is None and last_revised is None and state == "practiced":
            due_reason = "covered but never rated or revisited"

    return {
        **pattern,
        "problems": problems,
        "total": total,
        "tracked": tracked,
        "solved": solved,
        "coverage": coverage,
        "untracked": total - tracked,
        "extra_tagged": len(extra),
        "extra_solved": extra_solved,
        "last_worked": last_worked.isoformat() if last_worked else None,
        "days_since_worked": days_since_worked,
        "last_revised": last_revised.isoformat() if last_revised else None,
        "state": state,
        "due": due_reason is not None,
        "due_reason": due_reason,
    }


# --------------------------------------------------------------------------
# queries
# --------------------------------------------------------------------------


def list_patterns(domain: str | None = None) -> list[dict[str, Any]]:
    """The board. dsa.json and design.json are read once and joined in."""
    dsa_slugs, dsa_titles, dsa_topics = _dsa_index()
    design_tags, design_titles = _design_index()
    current = date.today()
    out = [
        _decorate(p, dsa_slugs, dsa_titles, dsa_topics, design_tags, design_titles, current)
        for p in load()[KEY]
    ]
    if domain:
        out = [p for p in out if p["domain"] == domain]
    return out


def get_pattern(key: str) -> dict[str, Any] | None:
    return next((p for p in list_patterns() if p["key"] == key), None)


def find_patterns(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        p
        for p in list_patterns()
        if needle in p["name"].lower()
        or needle in p["key"].lower()
        or any(needle in q["title"].lower() for q in p["problems"])
    ]


def for_problem(url: str | None, title: str | None = None) -> list[dict[str, Any]]:
    """Which patterns a problem belongs to — a problem can be in several.

    Derived rather than stored as a field on the DSA record: the catalogue is
    the thing that knows, and a copy on the problem would go stale the moment
    the catalogue changed.
    """
    slug = slug_of(url)
    needle = norm_title(title)
    out = []
    for pattern in load()[KEY]:
        for problem in pattern["problems"]:
            if (slug and slug_of(problem["url"]) == slug) or (
                needle and norm_title(problem["title"]) == needle
            ):
                out.append({"key": pattern["key"], "name": pattern["name"], "domain": pattern["domain"]})
                break
    return out


# --------------------------------------------------------------------------
# mutations
# --------------------------------------------------------------------------


def update_pattern(key: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, pattern in enumerate(data[KEY]):
            if pattern["key"] != key:
                continue
            data[KEY][idx] = _normalize(
                {**pattern, **{k: v for k, v in patch.items() if k != "key"}}
            )
            write(FILE, data)
            return get_pattern(key)
        return None


def log_revisit(
    key: str, outcome: str, confidence: int | None = None, on: str | None = None
) -> dict[str, Any] | None:
    """Record that the technique was re-derived, and clear the flag.

    Revisiting is the act that answers whatever put the pattern in the queue,
    so it is also what takes it back out — otherwise the flag outlives the
    problem it recorded and the queue stops meaning anything.
    """
    with _lock:
        data = load()
        for idx, pattern in enumerate(data[KEY]):
            if pattern["key"] != key:
                continue
            pattern["revisits"].append({"date": on or today(), "outcome": outcome})
            if confidence is not None:
                pattern["confidence"] = confidence
            pattern["flagged"] = False
            data[KEY][idx] = _normalize(pattern)
            write(FILE, data)
            return get_pattern(key)
        return None


def add_problem(key: str, problem: dict[str, Any]) -> dict[str, Any] | None:
    """Add a problem to a pattern's catalogue."""
    with _lock:
        data = load()
        for idx, pattern in enumerate(data[KEY]):
            if pattern["key"] != key:
                continue
            entry = apply_defaults(problem, _PROBLEM_DEFAULTS)
            entry.pop("id", None)
            if not entry["title"].strip():
                raise ValueError("A catalogue problem needs a title.")
            slug = slug_of(entry["url"])
            for existing in pattern["problems"]:
                same = slug and slug_of(existing["url"]) == slug
                if same or norm_title(existing["title"]) == norm_title(entry["title"]):
                    raise ValueError(f"{entry['title']} is already under {pattern['name']}.")
            pattern["problems"].append(entry)
            data[KEY][idx] = _normalize(pattern)
            write(FILE, data)
            return get_pattern(key)
        return None


def remove_problem(key: str, index: int) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, pattern in enumerate(data[KEY]):
            if pattern["key"] != key:
                continue
            if not 0 <= index < len(pattern["problems"]):
                raise ValueError("No problem at that position.")
            pattern["problems"].pop(index)
            data[KEY][idx] = _normalize(pattern)
            write(FILE, data)
            return get_pattern(key)
        return None


def delete_pattern(key: str) -> bool:
    with _lock:
        data = load()
        remaining = [p for p in data[KEY] if p["key"] != key]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        write(FILE, data)
        return True


def seed(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Load the curated curriculum, skipping patterns already present.

    Idempotent, the same way companies.seed is: re-seeding after the list grows
    adds only what is new and never clobbers a confidence, note or revisit.
    A pattern that is already there keeps its catalogue too — a problem removed
    on purpose must not come back on the next seed.
    """
    with _lock:
        data = load()
        known = {p["key"] for p in data[KEY]}
        added, skipped = [], []
        for entry in entries:
            if entry["key"] in known:
                skipped.append(entry["key"])
                continue
            data[KEY].append(_normalize({**entry, "id": new_id()}))
            added.append(entry["key"])
        if added:
            write(FILE, data)
        return {"added": len(added), "skipped": len(skipped), "keys": added}


def promote(
    key: str, index: int, title: str | None = None, phase: str | None = None
) -> dict[str, Any]:
    """Turn a catalogue row into a tracked record in the domain that owns it.

    A DSA row becomes a `todo` problem in dsa.json; a design row becomes a
    `todo` topic in design.json tagged with this pattern, which is what makes
    it join back here without a second step. Neither carries an approach, a
    hint or a note — promoting queues the work, it does not start it.
    """
    import design  # noqa: PLC0415
    import dsa  # noqa: PLC0415

    pattern = get_pattern(key)
    if pattern is None:
        raise ValueError(f"No pattern with key {key}.")
    if not 0 <= index < len(pattern["problems"]):
        raise ValueError("No problem at that position.")
    problem = pattern["problems"][index]
    if problem["tracked"]:
        raise ValueError(f"{problem['title']} is already tracked.")

    # Topics use the hyphenated form his existing records use ("two-pointers",
    # "topological-sort"), so the pattern tag sorts in with the rest.
    tag = key.replace("_", "-")
    if pattern["domain"] == "dsa":
        payload = {
            "title": title or problem["title"],
            "url": problem["url"],
            "platform": problem["platform"] if problem["platform"] != "none" else "other",
            "topics": [tag],
            "status": "todo",
            "phase": phase,
        }
        # Difficulty is left to dsa's own default when the sheet doesn't say —
        # guessing it would put a made-up number into the difficulty stats.
        if problem["difficulty"]:
            payload["difficulty"] = problem["difficulty"]
        return {"domain": "dsa", "record": dsa.create_problem(payload)}

    return {
        "domain": pattern["domain"],
        "record": design.create_topic(
            {
                "title": title or problem["title"],
                "kind": pattern["domain"],
                "url": problem["url"],
                "status": "todo",
                "patterns": [tag],
                "concepts": [tag],
            }
        ),
    }


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------


def revision_queue() -> list[dict[str, Any]]:
    """Patterns with real work behind them that has since decayed.

    Kept disjoint from `unstarted()` — see the module docstring. Ordered by how
    little you trust it, then by how long it has been left.
    """
    out = [
        {
            "key": p["key"],
            "name": p["name"],
            "domain": p["domain"],
            "state": p["state"],
            "solved": p["solved"],
            "total": p["total"],
            "coverage": p["coverage"],
            "confidence": p["confidence"],
            "days_since_worked": p["days_since_worked"],
            "last_revised": p["last_revised"],
            "reason": p["due_reason"],
            # The obvious rep to take: something in this pattern not yet solved.
            "next_problem": next(
                (
                    {"title": q["title"], "url": q["url"], "tracked": q["tracked"]}
                    for q in p["problems"]
                    if not q["solved"]
                ),
                None,
            ),
        }
        for p in list_patterns()
        if p["due"]
    ]
    out.sort(key=lambda p: (p["confidence"] or 0, -(p["days_since_worked"] or 0)))
    return out


def unstarted() -> list[dict[str, Any]]:
    """Patterns with nothing solved in them yet. Not revision — new ground."""
    return [
        {
            "key": p["key"],
            "name": p["name"],
            "domain": p["domain"],
            "total": p["total"],
            "tracked": p["tracked"],
            "first_problem": next(
                (
                    {"title": q["title"], "url": q["url"], "tracked": q["tracked"]}
                    for q in p["problems"]
                ),
                None,
            ),
        }
        for p in list_patterns()
        if p["state"] == "untouched"
    ]


def stats() -> dict[str, Any]:
    board = list_patterns()
    total = len(board)
    problems = sum(p["total"] for p in board)
    solved = sum(p["solved"] for p in board)

    by_state = {state: 0 for state in ("untouched", "learning", "practiced")}
    for pattern in board:
        by_state[pattern["state"]] += 1

    by_domain = {}
    for domain in DOMAINS:
        of_domain = [p for p in board if p["domain"] == domain]
        domain_problems = sum(p["total"] for p in of_domain)
        domain_solved = sum(p["solved"] for p in of_domain)
        by_domain[domain] = {
            "patterns": len(of_domain),
            "practiced": sum(1 for p in of_domain if p["state"] == "practiced"),
            "problems": domain_problems,
            "solved": domain_solved,
            "coverage": pct(domain_solved, domain_problems),
        }

    rated = [p["confidence"] for p in board if p["confidence"]]
    return {
        "total": total,
        "problems": problems,
        "solved": solved,
        "coverage": pct(solved, problems),
        # Catalogue rows with no record in dsa.json or design.json at all. Not
        # a failure — it is the size of the curriculum still ahead.
        "untracked": sum(p["untracked"] for p in board),
        # Solved work tagged with a pattern but not listed under it. Counted
        # here rather than in `solved`, so `coverage` stays a statement about
        # the curriculum instead of drifting every time something is tagged.
        "solved_off_catalogue": sum(p["extra_solved"] for p in board),
        "by_state": by_state,
        "by_domain": by_domain,
        "due": len(revision_queue()),
        "unstarted": len(unstarted()),
        "flagged": sum(1 for p in board if p["flagged"]),
        "rated": len(rated),
        "avg_confidence": round(sum(rated) / len(rated), 1) if rated else 0,
        # Started, and least covered — where the next rep buys the most.
        "thinnest": [
            {
                "key": p["key"],
                "name": p["name"],
                "domain": p["domain"],
                "solved": p["solved"],
                "total": p["total"],
                "coverage": p["coverage"],
            }
            for p in sorted(
                (p for p in board if p["state"] == "learning"),
                key=lambda p: (p["coverage"], -p["total"]),
            )[:5]
        ],
    }
