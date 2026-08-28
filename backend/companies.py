"""Company board — data/companies.json.

The shortlist you work *from*: who to target in India, MNC and startup, with
enough wiring on each record that role discovery can go and check their board
(see discover.py).

Two joins happen at read time and are never stored:

* `applications` / `board_column` come from jobs.json, so the board can't
  disagree with the application list. Matching is by name, the same
  case-insensitive convention prep.readiness() uses for company tags.
* `category` reuses storage.COMPANY_TYPES rather than inventing a parallel
  vocabulary, so promoting a company into an application carries its type
  straight through.
"""

from __future__ import annotations

import re
from typing import Any

import storage
from jsonstore import apply_defaults, lock_for, new_id, pct, read, today, write

FILE = "companies.json"
KEY = "companies"
_lock = lock_for(FILE)

# Where you are with the company, as a decision — not as an outcome.
# "applied" is deliberately absent: that is derived from jobs.json by
# board_column(), so the board can never claim you applied when you didn't.
STATUSES = ["researching", "target", "on_hold", "not_interested"]

# The interview bar you'd be preparing for, which is the thing that actually
# changes how you study. Not a prestige ranking.
TIERS = ["faang", "tier1", "tier2", "growth", "early"]

# Role families, for filtering the board down to what you'd actually apply to.
FOCUS_AREAS = [
    "swe", "ai_ml", "data", "backend", "frontend", "fullstack", "infra", "mobile", "quant",
]

CATEGORIES = storage.COMPANY_TYPES

_DEFAULTS: dict[str, Any] = {
    "name": "",
    # Other names the same employer appears under — "Eternal" for Zomato,
    # the legal entity on a job posting. Used by the jobs join.
    "aliases": [],
    "category": "product",
    "tier": None,
    "hq": None,
    "locations": [],
    "website": None,
    "careers_url": None,
    # Discovery wiring. provider "none" means we have no machine-readable
    # board and the assistant has to fall back to WebSearch.
    "ats_provider": "none",
    "ats_token": None,
    "focus": [],
    "tech_stack": [],
    "org_summary": None,
    # 1-5, how much you actually want it. Drives the default board sort.
    "interest": None,
    "status": "researching",
    "notes": "",
    # A record of the last fetch, not a derived number: when we last looked,
    # how many roles came back, and why it failed if it did.
    "discovery": {"last_checked": None, "last_count": None, "last_error": None},
}


def _normalize(company: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(company, _DEFAULTS)
    discovery = out["discovery"]
    discovery.setdefault("last_checked", None)
    discovery.setdefault("last_count", None)
    discovery.setdefault("last_error", None)
    if out["ats_provider"] not in ("greenhouse", "lever", "ashby", "none"):
        out["ats_provider"] = "none"
    # A provider without a token can't be fetched, so don't pretend it can.
    if not out["ats_token"]:
        out["ats_provider"] = "none"
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = [_normalize(c) for c in data[KEY]]
    return data


def save(data: dict[str, Any]) -> None:
    write(FILE, data)


# --------------------------------------------------------------------------
# name matching
# --------------------------------------------------------------------------


def norm_name(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


# Below this length a prefix match is too loose to trust — "ola" would claim
# every job at Olam, so short names must match exactly.
_PREFIX_SAFE_LENGTH = 5


def matches(company: dict[str, Any], organisation: str | None) -> bool:
    """Does `organisation` (as written on a job record) refer to this company?

    Exact match on the name or any alias, or a prefix match when the name is
    long enough to be distinctive — job postings routinely carry the legal
    entity ("Razorpay Software Private Limited") rather than the brand.
    """
    target = norm_name(organisation)
    if not target:
        return False
    for candidate in [company["name"], *company.get("aliases", [])]:
        known = norm_name(candidate)
        if not known:
            continue
        if target == known:
            return True
        if len(known) >= _PREFIX_SAFE_LENGTH and target.startswith(known):
            return True
    return False


# --------------------------------------------------------------------------
# queries
# --------------------------------------------------------------------------


def _decorate(company: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    mine = [j for j in jobs if matches(company, j.get("organisation"))]
    live = [j for j in mine if j["status"] != "saved"]
    company["applications"] = len(live)
    company["leads"] = len(mine) - len(live)
    company["application_statuses"] = sorted({j["status"] for j in mine})
    # An application is a fact; the manual status is an intention. The fact wins.
    company["board_column"] = "applied" if live else company["status"]
    return company


def list_companies(
    status: str | None = None,
    category: str | None = None,
    tier: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """The board. jobs.json is read once and joined in, not re-read per row."""
    jobs = storage.list_jobs()
    out = [_decorate(c, jobs) for c in load()[KEY]]
    if status:
        out = [c for c in out if c["board_column"] == status]
    if category:
        out = [c for c in out if c["category"] == category]
    if tier:
        out = [c for c in out if c["tier"] == tier]
    if query:
        needle = query.strip().lower()
        out = [
            c
            for c in out
            if needle in c["name"].lower()
            or any(needle in a.lower() for a in c["aliases"])
            or any(needle in t.lower() for t in c["tech_stack"])
            or any(needle in f.lower() for f in c["focus"])
        ]
    # Most-wanted first, then alphabetical so the order is stable.
    out.sort(key=lambda c: (-(c["interest"] or 0), c["name"].lower()))
    return out


def get_company(company_id: str) -> dict[str, Any] | None:
    jobs = storage.list_jobs()
    company = next((c for c in load()[KEY] if c["id"] == company_id), None)
    return _decorate(company, jobs) if company else None


def find_company(name: str) -> dict[str, Any] | None:
    """Locate by name or alias — how the AI resolves a company the user names."""
    jobs = storage.list_jobs()
    for company in load()[KEY]:
        if matches(company, name):
            return _decorate(company, jobs)
    return None


def fetchable() -> list[dict[str, Any]]:
    """Companies with a machine-readable board — what discovery can search."""
    return [c for c in load()[KEY] if c["ats_provider"] != "none"]


# --------------------------------------------------------------------------
# mutations
# --------------------------------------------------------------------------


def create_company(payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        company = _normalize({**payload, "id": new_id()})
        if not company["name"].strip():
            raise ValueError("A company needs a name.")
        if any(matches(c, company["name"]) for c in data[KEY]):
            raise ValueError(f"{company['name']} is already on the board.")
        data[KEY].append(company)
        save(data)
        return _decorate(company, storage.list_jobs())


def update_company(company_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, company in enumerate(data[KEY]):
            if company["id"] != company_id:
                continue
            data[KEY][idx] = _normalize(
                {**company, **{k: v for k, v in patch.items() if k != "id"}}
            )
            save(data)
            return _decorate(data[KEY][idx], storage.list_jobs())
        return None


def delete_company(company_id: str) -> bool:
    with _lock:
        data = load()
        remaining = [c for c in data[KEY] if c["id"] != company_id]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        save(data)
        return True


def record_discovery_many(stamps: dict[str, tuple[int | None, str | None]]) -> int:
    """Stamp the outcome of a discovery run onto every company it checked.

    Takes the whole run at once because a search fans out over the entire
    board: stamping one company at a time would rewrite the file once per
    company, which is a hundred writes for one click.
    """
    if not stamps:
        return 0
    with _lock:
        data = load()
        when = today()
        touched = 0
        for idx, company in enumerate(data[KEY]):
            if company["id"] not in stamps:
                continue
            count, error = stamps[company["id"]]
            company["discovery"] = {
                "last_checked": when,
                "last_count": count,
                "last_error": error,
            }
            data[KEY][idx] = _normalize(company)
            touched += 1
        if touched:
            save(data)
        return touched


def record_discovery(
    company_id: str, count: int | None, error: str | None = None
) -> dict[str, Any] | None:
    """Stamp a single company's fetch outcome."""
    if not record_discovery_many({company_id: (count, error)}):
        return None
    return get_company(company_id)


def seed(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Add curated companies, skipping any already on the board.

    Idempotent on purpose: re-seeding after the list grows should add only
    what's new and never clobber a status, interest or note you've set.
    """
    with _lock:
        data = load()
        added, skipped = [], []
        for entry in entries:
            if any(matches(c, entry["name"]) for c in data[KEY]):
                skipped.append(entry["name"])
                continue
            company = _normalize({**entry, "id": new_id()})
            data[KEY].append(company)
            added.append(company["name"])
        if added:
            save(data)
        return {"added": len(added), "skipped": len(skipped), "names": added}


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------


def stats() -> dict[str, Any]:
    board = list_companies()
    total = len(board)

    def tally(field: str, values: list[str]) -> dict[str, int]:
        counts = {v: 0 for v in values}
        for company in board:
            key = company.get(field)
            if key:
                counts[key] = counts.get(key, 0) + 1
        return counts

    targets = [c for c in board if c["status"] == "target"]
    # The gap the board exists to close: wanted, but nothing sent yet.
    untouched = [c for c in targets if not c["applications"]]
    with_ats = [c for c in board if c["ats_provider"] != "none"]

    locations: dict[str, int] = {}
    for company in board:
        for city in company["locations"]:
            locations[city] = locations.get(city, 0) + 1

    return {
        "total": total,
        "targets": len(targets),
        "untouched_targets": len(untouched),
        "applied_to": sum(1 for c in board if c["applications"]),
        "leads_open": sum(c["leads"] for c in board),
        "with_ats": len(with_ats),
        "ats_coverage": pct(len(with_ats), total),
        "by_status": tally("status", STATUSES),
        "by_category": tally("category", CATEGORIES),
        "by_tier": tally("tier", TIERS),
        "by_location": dict(sorted(locations.items(), key=lambda kv: -kv[1])),
        "never_checked": sum(1 for c in with_ats if not c["discovery"]["last_checked"]),
    }


def target_gaps() -> list[dict[str, Any]]:
    """Companies you called targets and then never applied to."""
    out = [
        {
            "id": c["id"],
            "name": c["name"],
            "tier": c["tier"],
            "category": c["category"],
            "careers_url": c["careers_url"],
            "ats_provider": c["ats_provider"],
            "interest": c["interest"],
            "last_checked": c["discovery"]["last_checked"],
        }
        for c in list_companies()
        if c["status"] == "target" and not c["applications"] and not c["leads"]
    ]
    out.sort(key=lambda c: -(c["interest"] or 0))
    return out
