"""Skill gaps read out of the job descriptions — data/skills.json.

The other domains answer "what have I done". This one answers "what do the
roles I am actually applying to keep asking for that I cannot supply", and it
has to stay honest as the pipeline changes: a skill that three JDs wanted in
August and nothing has wanted since should sink on its own, without anyone
re-writing a list.

So **demand is joined in at read time from jobs.json and never stored** — the
same choice companies.py makes against jobs.json and patterns.py makes against
dsa.json, for the same reason. Add a job with a `job_description` and every
count and every rank on this board moves on the next read. There is no refresh
step and nothing to keep in sync, because there is no second copy.

A second join, against resumes.json, is what makes this more than a wishlist:
`claimed` is true when a stored resume already names the skill. Claimed with
nothing behind it is not a gap, it is a **live credibility risk** — the reader
has already been told you have it, and the question is coming. That state is
worth more than any of the counts, and neither jobs.json nor resumes.json can
see it alone.

What the file *does* store is what nothing else knows: the catalogue, the
aliases that do the matching, a self-rated level, the cost of closing it, the
plan, and the evidence log.

Two lists come out of this, and unlike dsa.py's and patterns.py's pairs they
are **allowed to overlap**:

* `gap_queue()` — ranked, "acquire this next".
* `exposed()` — "this claim on your resume is unbacked".

Those are not two answers to the same question. A skill that is both in demand
and falsely claimed genuinely needs both actions — go and learn it, and take it
off the resume until you have. Forcing them disjoint would mean dropping one of
two things that are both true.
"""

from __future__ import annotations

import math
import re
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, parse_date, pct, read, today, write

FILE = "skills.json"
KEY = "skills"
_lock = lock_for(FILE)

# Where the skill sits, for grouping the board. Not a difficulty ranking.
AREAS = ["language", "backend", "data", "ml", "cloud", "infra", "practice"]

# Where you are with it, as a decision — separate from `level`, which is where
# you are with it as a fact. "declined" is the important one: a skill that only
# one JD ever wanted is a real requirement and still the wrong thing to learn,
# and writing that down is what stops it nagging every time the board is read.
STATUSES = ["wanted", "learning", "declined", "done"]

# 0-4. The gap between "read about it" and "shipped it" is the whole subject of
# this module, so it does not collapse into a boolean.
LEVELS = ["none", "aware", "used", "built", "shipped"]

# The lowest level at which claiming the skill on a resume is defensible. Below
# this, `claimed` makes the skill `exposed` rather than covered.
USABLE_LEVEL = 2

# What "closed" means by default: built something non-trivial with it. Deliberately
# not `shipped` — a bar that only production work can clear is a bar no amount of
# personal work can reach, and every row would sit open forever.
DEFAULT_TARGET = 3

# How much one JD naming the skill counts for. A live application is a question
# that could be asked next week; a rejected one is market signal and still
# counts, because the next posting from that tier will ask the same thing.
MENTION_WEIGHT = {
    "interviewing": 4,
    "offer": 4,
    "applied": 3,
    "saved": 2,
    "rejected": 1,
    "ghosted": 1,
    "withdrawn": 1,
}
DEFAULT_MENTION_WEIGHT = 1

# Demand saturates rather than accumulating linearly. Going from one posting to
# four is a real change in what the market is saying; going from eight to nine
# is noise. Counted straight, a word every JD uses in passing ("code review")
# outranks a stated hard requirement ("Kubernetes") on frequency alone, which
# is how a ranked list stops being read.
DEMAND_SCALE = 10

# How far the skill is from usable, which is the other half of the question: a
# widely-wanted thing you nearly have is worth less work than a slightly less
# wanted thing you cannot do at all.
GAP_WEIGHT = 5

# Cheap things rank up. This board is a work queue, not a wishlist: a two-day
# skill three JDs asked for beats a three-month one that four asked for, because
# the first is closable this week and the second is a quarter of the year.
EFFORT_BONUS = {"days": 4, "weeks": 2, "months": 0}
EFFORTS = list(EFFORT_BONUS)

# A resume claim with nothing behind it outranks a plain gap: a missing skill
# costs you a role you were never going to get, an unbacked claim costs you one
# you already have an interview for.
EXPOSED_BONUS = 6

_DEFAULTS: dict[str, Any] = {
    "key": "",
    "name": "",
    "area": "practice",
    "order": 0,
    # The strings matched against JD and resume text. This is the join wiring —
    # the same load-bearing role ats_token plays on a company record, and it
    # fails the same silently-wrong way when it is careless. See `_matcher`.
    "aliases": [],
    # 0-4, self-rated, and the one signal neither join can supply: nothing in
    # jobs.json or resumes.json knows whether you can actually do this.
    "level": 0,
    "target_level": DEFAULT_TARGET,
    "effort": "weeks",
    "status": "wanted",
    # What you would point a screener at today. Empty is the honest default.
    "evidence": "",
    # The concrete closing move, not a topic. "Deploy the tracker to a local
    # kind cluster" is a plan; "learn Kubernetes" is a restatement of the row.
    "plan": "",
    "notes": "",
    # {date, note, level} — what actually moved the level, so a 3 can be
    # defended later. Self-ratings drift upward without a record behind them.
    "log": [],
}


def _normalize(skill: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(skill, _DEFAULTS)
    if out["area"] not in AREAS:
        out["area"] = "practice"
    if out["status"] not in STATUSES:
        out["status"] = "wanted"
    if out["effort"] not in EFFORT_BONUS:
        out["effort"] = "weeks"
    out["level"] = _clamp_level(out["level"])
    out["target_level"] = _clamp_level(out["target_level"], DEFAULT_TARGET)
    out["aliases"] = [a for a in (str(a).strip() for a in out["aliases"]) if a]
    # A skill with no aliases would silently match nothing, so the name stands
    # in. Only when the list is empty, though: the Go row lists a guarded
    # pattern precisely to keep "Go ahead, apply anyway" out, and quietly
    # appending the bare name behind it put the false positive straight back.
    # If the author supplied aliases, the author is in charge.
    if out["name"] and not out["aliases"]:
        out["aliases"] = [out["name"]]
    for entry in out["log"]:
        entry.setdefault("date", today())
        entry.setdefault("note", "")
        entry.setdefault("level", None)
    return out


def _clamp_level(value: Any, fallback: int = 0) -> int:
    try:
        return max(0, min(len(LEVELS) - 1, int(value)))
    except (TypeError, ValueError):
        return fallback


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = sorted(
        (_normalize(s) for s in data[KEY]), key=lambda s: (s["order"], s["name"])
    )
    return data


# --------------------------------------------------------------------------
# matching a skill to prose
# --------------------------------------------------------------------------
#
# discover.py learned this the expensive way and the lesson transfers exactly:
# a substring search over job postings is wrong in ways that look right. The
# false positives that actually occurred while building this catalogue, all of
# them from the JDs in data/jobs.json:
#
#   "ai"     matched Ret*ai*l and cert*ai*n
#   "eks"    matched "features live within we*eks*"        (EKS, Barclays)
#   "scala"  matched "*scala*ble solutions"                (Scala, Expedia)
#   "Go"     matched "Go ahead, apply anyway"              (Golang, UiPath)
#
# The first three are fixed by anchoring on boundaries. The fourth is not — it
# is a real word-boundary match on a real English word, so it needs a guard,
# the same way discover.guess_seniority needs `(?<!technical )staff`.
#
# So an alias is a plain word by default and matched on boundaries. An alias
# prefixed `re:` is a raw pattern the catalogue author wrote deliberately, and
# every one of those in skill_seed.py carries a comment saying which false
# positive it exists to kill.

_RAW = "re:"

# \b is wrong at either end of "C++", ".NET" or "CI/CD" — the boundary falls in
# the middle of the token. These lookarounds treat the alias as a run of
# identifier-ish characters instead, so "C++" will not match inside "C++11" but
# will match "C++." at the end of a sentence.
_LEFT = r"(?<![A-Za-z0-9+#])"
_RIGHT = r"(?![A-Za-z0-9+#])"

# Job postings pluralise constantly — "design documents", "voice pipelines",
# "vector databases", "training pipelines" — and an alias written in the
# singular missed every one of them. Allowing an optional plural suffix is
# safe here because the right-hand boundary still has to hold afterwards:
# "Scala" matches "Scalas" and still refuses "Scalable".
_PLURAL = r"(?:es|s)?"

_cache: dict[str, re.Pattern[str]] = {}


def _matcher(alias: str) -> re.Pattern[str]:
    if alias not in _cache:
        if alias.startswith(_RAW):
            # Author-written, case-sensitive: the guards that need it are
            # distinguishing "Go" the language from "go" the verb.
            _cache[alias] = re.compile(alias[len(_RAW) :])
        else:
            _cache[alias] = re.compile(
                _LEFT + re.escape(alias) + _PLURAL + _RIGHT, re.IGNORECASE
            )
    return _cache[alias]


def mentions(text: str | None, aliases: list[str]) -> str | None:
    """The text that matched, or None. Pure — no I/O.

    Returns what the posting actually said rather than the alias that caught
    it: "voice pipelines" is a more useful thing to show than the regex which
    found it, and for a raw alias the pattern itself would be unreadable.
    """
    if not text:
        return None
    for alias in aliases:
        found = _matcher(alias).search(text)
        if found:
            return found.group(0)
    return None


# --------------------------------------------------------------------------
# the joins
# --------------------------------------------------------------------------


def _jd_index() -> list[dict[str, Any]]:
    """Every stored job description, with what it takes to weigh a mention."""
    import storage  # noqa: PLC0415 -- local, so the domain modules stay independent

    out = []
    for job in storage.list_jobs():
        text = (job.get("job_description") or "").strip()
        if not text:
            continue
        status = job.get("status") or "saved"
        out.append(
            {
                "job_id": job["id"],
                "organisation": job.get("organisation") or "?",
                "job_title": job.get("job_title"),
                "status": status,
                "live": status not in ("rejected", "ghosted", "withdrawn"),
                "weight": MENTION_WEIGHT.get(status, DEFAULT_MENTION_WEIGHT),
                "date": job.get("date_job_posted") or job.get("date_created"),
                "text": text,
            }
        )
    return out


# The resume's own skills block. Everything above it is prose: a bullet saying
# "raised outreach throughput from 30 to 200 emails/hour" contains the word
# "throughput" and claims nothing about performance engineering, and matching
# it flagged half the catalogue as exposed on the first run. A skills row is
# where a claim is actually *made* — prose is evidence, and evidence is fine.
#
# resumes._normalize derives `content` from LaTeX when only LaTeX is stored, so
# reading the plain text alone covers every version.
# An ALL-CAPS line on its own is a section heading in the layout docx_export
# parses; body lines always carry lower case, so they cannot be mistaken for one.
_HEADING = re.compile(r"^[A-Z][A-Z0-9 &/,'.-]{2,}$", re.MULTILINE)


def claim_text(content: str | None) -> str:
    """The part of a resume that asserts a capability, rather than evidencing one.

    Falls back to the whole document when there is no skills block to find: a
    resume written in some other shape should still be checked, and a silent
    empty string would report every claim on it as absent.
    """
    if not content:
        return ""
    headings = list(_HEADING.finditer(content))
    for idx, heading in enumerate(headings):
        if "SKILL" not in heading.group(0):
            continue
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(content)
        return content[heading.end() : end]
    return content


def _resume_index() -> list[dict[str, Any]]:
    """Every stored resume's skills block, so a claim can be found where it is made.

    All versions, not only the master: a tailored version that claims something
    the master doesn't is the one that actually went out, so it is the one that
    carries the risk.
    """
    import resumes  # noqa: PLC0415

    out = []
    for resume in resumes.list_resumes():
        text = claim_text(resume.get("content"))
        if text.strip():
            out.append(
                {
                    "resume_id": resume["id"],
                    "name": resume.get("name") or "untitled",
                    "master": bool(resume.get("is_latex_template")),
                    "text": text,
                }
            )
    return out


def _decorate(
    skill: dict[str, Any], jds: list[dict[str, Any]], cvs: list[dict[str, Any]]
) -> dict[str, Any]:
    """Attach live demand and resume claims. None of this is ever written back."""
    aliases = skill["aliases"]

    found = []
    for jd in jds:
        hit = mentions(jd["text"], aliases)
        if hit:
            found.append(
                {
                    "job_id": jd["job_id"],
                    "organisation": jd["organisation"],
                    "job_title": jd["job_title"],
                    "status": jd["status"],
                    "live": jd["live"],
                    "date": jd["date"],
                    "matched": hit,
                }
            )

    claimed_on = [
        {"resume_id": cv["resume_id"], "name": cv["name"], "master": cv["master"]}
        for cv in cvs
        if mentions(cv["text"], aliases)
    ]

    demand = len(found)
    demand_live = sum(1 for m in found if m["live"])
    weighted = sum(MENTION_WEIGHT.get(m["status"], DEFAULT_MENTION_WEIGHT) for m in found)
    dates = [d for d in (parse_date(m["date"]) for m in found) if d]

    level = skill["level"]
    target = skill["target_level"]
    gap = max(0, target - level)
    claimed = bool(claimed_on)

    # Order matters. A declined skill is a decision and outranks every fact
    # about it; past that, having it beats every warning about not having it.
    if skill["status"] == "declined":
        state = "declined"
    elif skill["status"] == "done" or level >= target:
        state = "have"
    elif claimed and level < USABLE_LEVEL:
        state = "exposed"
    elif level >= 1 or skill["status"] == "learning":
        state = "learning"
    else:
        state = "missing"

    score, because = _rank(skill, state, weighted, demand, demand_live, gap, claimed)

    return {
        **skill,
        "level_name": LEVELS[level],
        "target_name": LEVELS[target],
        "gap": gap,
        "demand": demand,
        "demand_live": demand_live,
        "demand_weighted": weighted,
        "mentions": sorted(found, key=lambda m: (not m["live"], m["organisation"])),
        "organisations": sorted({m["organisation"] for m in found}),
        "first_seen": min(dates).isoformat() if dates else None,
        "last_seen": max(dates).isoformat() if dates else None,
        "claimed": claimed,
        "claimed_on": claimed_on,
        "on_master": any(c["master"] for c in claimed_on),
        "state": state,
        "score": score,
        "because": because,
    }


def _rank(
    skill: dict[str, Any],
    state: str,
    weighted: int,
    demand: int,
    demand_live: int,
    gap: int,
    claimed: bool,
) -> tuple[int, list[str]]:
    """Score a skill, and say why.

    Every contribution appends to `because`. A ranking nobody can audit is one
    that gets ignored the first time it looks wrong — and this one reorders
    itself whenever a job is added, so it will look wrong eventually and has to
    be able to defend itself when it does. Same reasoning as dsa.coach().
    """
    if state in ("have", "declined"):
        return 0, []

    because: list[str] = []
    score = round(DEMAND_SCALE * math.log2(1 + weighted))
    if demand:
        live = f", {demand_live} live" if demand_live and demand_live != demand else ""
        because.append(f"named in {demand} JD{'s' if demand != 1 else ''}{live}")
    if gap:
        because.append(
            f"{LEVELS[skill['level']]} against a target of {LEVELS[skill['target_level']]}"
        )
    score += gap * GAP_WEIGHT

    bonus = EFFORT_BONUS[skill["effort"]]
    score += bonus
    if bonus >= 4:
        because.append("closable in days")

    if claimed and skill["level"] < USABLE_LEVEL:
        score += EXPOSED_BONUS
        because.append("already claimed on a resume with nothing behind it")

    return score, because


# --------------------------------------------------------------------------
# queries
# --------------------------------------------------------------------------


def list_skills(area: str | None = None, state: str | None = None) -> list[dict[str, Any]]:
    """The board. jobs.json and resumes.json are read once and joined in."""
    jds = _jd_index()
    cvs = _resume_index()
    out = [_decorate(s, jds, cvs) for s in load()[KEY]]
    if area:
        out = [s for s in out if s["area"] == area]
    if state:
        out = [s for s in out if s["state"] == state]
    return out


def get_skill(key: str) -> dict[str, Any] | None:
    return next((s for s in list_skills() if s["key"] == key), None)


def find_skills(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        s
        for s in list_skills()
        if needle in s["name"].lower()
        or needle in s["key"].lower()
        or any(needle in a.lower() for a in s["aliases"])
    ]


def gap_queue(limit: int | None = None) -> list[dict[str, Any]]:
    """What to acquire next, ranked by what the JDs on file actually ask for.

    Only skills with live demand: this board is driven by the pipeline, and a
    catalogue row nothing has asked for is not a priority, it is a row waiting
    for a posting to justify it. `no_demand` in stats() counts those.
    """
    out = [
        _summary(s)
        for s in list_skills()
        if s["demand"] > 0 and s["state"] not in ("have", "declined")
    ]
    out.sort(key=lambda s: (-s["score"], -s["demand_weighted"], s["name"]))
    for rank, row in enumerate(out, start=1):
        row["rank"] = rank
    return out[:limit] if limit else out


def exposed() -> list[dict[str, Any]]:
    """Claims already on a resume with nothing behind them.

    Deliberately allowed to overlap gap_queue() — see the module docstring.
    Ordered by where the claim is made: the master version is on every send.
    """
    out = [_summary(s) for s in list_skills() if s["state"] == "exposed"]
    out.sort(key=lambda s: (not s["on_master"], -s["demand_weighted"], s["name"]))
    return out


def declined() -> list[dict[str, Any]]:
    """Skills consciously not being chased, with their demand still shown.

    The demand keeps updating, which is the point: a decision made when one
    posting wanted it should be revisited if four more arrive, and nothing
    re-opens that question unless the number stays visible.
    """
    out = [_summary(s) for s in list_skills() if s["state"] == "declined"]
    out.sort(key=lambda s: (-s["demand_weighted"], s["name"]))
    return out


def for_job(job_id: str) -> dict[str, Any]:
    """What one posting asks for, split into covered and missing.

    The view worth reading before applying: it names the gaps this particular
    JD will screen on, rather than the gaps the pipeline has on average.
    """
    import storage  # noqa: PLC0415

    job = storage.get_job(job_id)
    if job is None:
        raise ValueError("No job with that id.")
    text = job.get("job_description") or ""
    covered, missing, declined_here = [], [], []
    for skill in list_skills():
        if not mentions(text, skill["aliases"]):
            continue
        row = _summary(skill)
        if skill["state"] == "have":
            covered.append(row)
        elif skill["state"] == "declined":
            declined_here.append(row)
        else:
            missing.append(row)
    missing.sort(key=lambda s: -s["score"])
    return {
        "job_id": job_id,
        "organisation": job.get("organisation"),
        "job_title": job.get("job_title"),
        "has_description": bool(text.strip()),
        "covered": covered,
        "missing": missing,
        "declined": declined_here,
    }


def _summary(skill: dict[str, Any]) -> dict[str, Any]:
    """The fields a queue row needs. Full records stay behind get_skill."""
    return {
        "key": skill["key"],
        "name": skill["name"],
        "area": skill["area"],
        "state": skill["state"],
        "status": skill["status"],
        "level": skill["level"],
        "level_name": skill["level_name"],
        "target_level": skill["target_level"],
        "gap": skill["gap"],
        "effort": skill["effort"],
        "demand": skill["demand"],
        "demand_live": skill["demand_live"],
        "demand_weighted": skill["demand_weighted"],
        "organisations": skill["organisations"],
        "first_seen": skill["first_seen"],
        "claimed": skill["claimed"],
        "on_master": skill["on_master"],
        "claimed_on": [c["name"] for c in skill["claimed_on"]],
        "plan": skill["plan"],
        "evidence": skill["evidence"],
        "score": skill["score"],
        "because": skill["because"],
    }


# --------------------------------------------------------------------------
# mutations
# --------------------------------------------------------------------------


def create_skill(payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        skill = _normalize({**payload, "id": new_id()})
        if not skill["key"].strip():
            raise ValueError("A skill needs a key.")
        if not skill["name"].strip():
            raise ValueError("A skill needs a name.")
        if any(s["key"] == skill["key"] for s in data[KEY]):
            raise ValueError(f"{skill['key']} is already on the board.")
        data[KEY].append(skill)
        write(FILE, data)
        return get_skill(skill["key"])


def update_skill(key: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, skill in enumerate(data[KEY]):
            if skill["key"] != key:
                continue
            data[KEY][idx] = _normalize(
                {**skill, **{k: v for k, v in patch.items() if k != "key"}}
            )
            write(FILE, data)
            return get_skill(key)
        return None


def log_evidence(
    key: str, note: str, level: int | None = None, on: str | None = None
) -> dict[str, Any] | None:
    """Record something you actually did with the skill, and raise the level.

    The level is a self-rating, and self-ratings drift up quietly. Tying every
    change to a dated note is what makes a 3 defensible six months later, when
    the question is "you list this — where?" and the answer has to be a thing,
    not a feeling. The note also becomes the `evidence` line, which is exactly
    what a resume bullet or an interview answer needs.
    """
    if not note.strip():
        raise ValueError("Evidence needs a note — what did you actually do?")
    with _lock:
        data = load()
        for idx, skill in enumerate(data[KEY]):
            if skill["key"] != key:
                continue
            entry = {"date": on or today(), "note": note.strip(), "level": None}
            if level is not None:
                entry["level"] = _clamp_level(level)
                skill["level"] = entry["level"]
            skill["log"].append(entry)
            skill["evidence"] = note.strip()
            # Evidence is the act of starting, so it also ends "wanted" — a
            # skill with work behind it that still reads as untouched is how
            # the board stops matching reality.
            if skill["status"] == "wanted":
                skill["status"] = "learning"
            if skill["level"] >= skill["target_level"]:
                skill["status"] = "done"
            data[KEY][idx] = _normalize(skill)
            write(FILE, data)
            return get_skill(key)
        return None


def decline(key: str, reason: str) -> dict[str, Any] | None:
    """Consciously stop chasing a skill, with the reason recorded.

    A reason is required. "Not doing this" with no why is indistinguishable
    from having forgotten about it, and it is the note that lets the decision
    be re-read later against a demand count that has since moved.
    """
    if not reason.strip():
        raise ValueError("Declining a skill needs a reason.")
    return update_skill(key, {"status": "declined", "notes": reason.strip()})


def delete_skill(key: str) -> bool:
    with _lock:
        data = load()
        remaining = [s for s in data[KEY] if s["key"] != key]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        write(FILE, data)
        return True


def seed(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Load the curated catalogue, skipping keys already present.

    Idempotent, like companies.seed and patterns.seed: re-seeding after the
    catalogue grows adds only what is new and never clobbers a level, a plan,
    an evidence log or a decision to decline.
    """
    with _lock:
        data = load()
        known = {s["key"] for s in data[KEY]}
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


# --------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------


def stats() -> dict[str, Any]:
    board = list_skills()
    jds = _jd_index()
    wanted = [s for s in board if s["state"] not in ("have", "declined")]
    in_demand = [s for s in board if s["demand"] > 0]

    by_state = {state: 0 for state in ("missing", "learning", "exposed", "have", "declined")}
    for skill in board:
        by_state[skill["state"]] += 1

    by_area = {}
    for area in AREAS:
        of_area = [s for s in board if s["area"] == area]
        if not of_area:
            continue
        by_area[area] = {
            "total": len(of_area),
            "have": sum(1 for s in of_area if s["state"] == "have"),
            "demand": sum(s["demand"] for s in of_area),
        }

    return {
        "total": len(board),
        "jds_read": len(jds),
        "in_demand": len(in_demand),
        # The headline: of everything the JDs on file ask for, how much can you
        # actually supply. Coverage over demanded skills, not over the whole
        # catalogue — a catalogue can be padded, a JD cannot.
        "coverage": pct(sum(1 for s in in_demand if s["state"] == "have"), len(in_demand)),
        "open": len(wanted),
        "by_state": by_state,
        "by_area": by_area,
        "exposed": len(exposed()),
        "declined": by_state["declined"],
        # Catalogue rows nothing on file has asked for. Not a failure — either
        # the pipeline moved on, or the row was speculative to begin with.
        "no_demand": sum(1 for s in board if s["demand"] == 0),
        "quick_wins": sum(
            1 for s in wanted if s["demand"] > 0 and s["effort"] == "days"
        ),
        # The bars on the tab: what the postings ask for most, whether or not
        # it is a gap, so "everything at the top is red" is visibly not the
        # same claim as "everything is a gap".
        "top_demand": [
            {
                "key": s["key"],
                "name": s["name"],
                "demand": s["demand"],
                "demand_live": s["demand_live"],
                "state": s["state"],
            }
            for s in sorted(board, key=lambda s: (-s["demand"], s["name"]))[:8]
            if s["demand"] > 0
        ],
        "next": gap_queue(limit=3),
    }
