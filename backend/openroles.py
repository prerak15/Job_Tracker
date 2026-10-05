"""Open roles — one list over both ways the tracker finds jobs.

`discover.py` reads the public ATS boards live (Greenhouse, Lever, Ashby);
`scrape.py` reads careers pages in a browser and leaves the last roles it read
per company in `data/scraped-roles.json`. The dashboard's Open roles tab wants
one list, filtered once, by the same rules the scraper's workbook uses — so the
filters live in one file (`data/role-filters.json`) and both halves go through
`discover.filter_roles` with them.

Also here, because the tab is where it is used: running the scraper in the
background, and suggesting companies to add (the curated catalogue, minus what
is already on the board).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import companies
import company_seed
import discover
import jsonstore
import scrape
import storage

LEVELS = ("intern", "entry", "mid", "senior")
# The keys the tab may change. locations / exclude_keywords stay file-only: their
# defaults are long lists that a form would only get wrong.
EDITABLE = ("keywords", "experience", "exclude_seniority", "include_remote", "max_age_days")


# --------------------------------------------------------------------------
# filters — data/role-filters.json, shared with the scraper's workbook
# --------------------------------------------------------------------------


def get_filters() -> dict[str, Any]:
    f = scrape.load_filters()
    return {
        "keywords": f["keywords"],
        "experience": f["experience"],
        "exclude_seniority": f["exclude_seniority"],
        "include_remote": f["include_remote"],
        "max_age_days": f["max_age_days"],
        "levels": list(LEVELS),
        "default_keywords": list(scrape.ROLE_KEYWORDS),
    }


def save_filters(patch: dict[str, Any]) -> dict[str, Any]:
    """Update the editable keys in the file, validating before anything is written."""
    unknown = set(patch) - set(EDITABLE)
    if unknown:
        raise ValueError(f"not editable here: {', '.join(sorted(unknown))}")
    clean: dict[str, Any] = {}
    if "keywords" in patch:
        words = [str(k).strip() for k in patch["keywords"] or [] if str(k).strip()]
        if not words:
            raise ValueError("keep at least one keyword, or every role on every board matches")
        clean["keywords"] = words
    if "experience" in patch:
        # Off is stored as false, not null: load_filters treats null as "use the
        # default", which would quietly switch the 0-3 filter back on.
        clean["experience"] = scrape.experience_range(patch["experience"]) or False
    if "exclude_seniority" in patch:
        levels = [str(s) for s in patch["exclude_seniority"] or []]
        bad = [s for s in levels if s not in LEVELS]
        if bad:
            raise ValueError(f"unknown level: {', '.join(bad)}")
        clean["exclude_seniority"] = levels
    if "include_remote" in patch:
        clean["include_remote"] = bool(patch["include_remote"])
    if "max_age_days" in patch:
        age = patch["max_age_days"]
        clean["max_age_days"] = int(age) if age not in (None, "") else None

    scrape.load_filters()  # creates the file with defaults if it isn't there yet
    path = jsonstore.DATA_DIR / scrape.FILTERS_FILE
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored.update(clean)
    jsonstore.write(scrape.FILTERS_FILE, stored)
    return get_filters()


# --------------------------------------------------------------------------
# the list
# --------------------------------------------------------------------------


def scraped_roles(board: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Roles from the last careers-page reads, for companies still on the board.

    Tier and category are re-read from the board, so re-tiering a company shows
    up without a re-scrape.
    """
    roles: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for company_id, entry in scrape.load_scraped().items():
        company = board.get(company_id)
        if not company:
            continue
        for role in entry.get("roles") or []:
            roles.append({**role, "tier": company.get("tier"), "category": company.get("category"),
                          "read_on": entry.get("read_on")})
        sources.append({"company": company["name"], "read_on": entry.get("read_on"),
                        "problem": entry.get("problem"), "roles": len(entry.get("roles") or [])})
    return roles, sources


async def open_roles(*, refresh: bool = False) -> dict[str, Any]:
    """Every role that passes the saved filters and isn't tracked yet, both sources."""
    f = scrape.load_filters()
    board = {c["id"]: c for c in companies.list_companies()}
    exp = scrape.experience_args(f)

    ats = await discover.search(
        keywords=f["keywords"],
        exclude_keywords=f["exclude_keywords"],
        locations=f["locations"],
        include_remote=f["include_remote"],
        max_age_days=f["max_age_days"],
        exclude_seniority=f["exclude_seniority"],
        limit=2000,
        force=refresh,
        **exp,
    )
    raw, sources = scraped_roles(board)
    filtered = scrape.filter_scraped(raw, f)
    from_pages, already = scrape.dedupe_scraped(filtered, storage.list_jobs())

    roles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in ats["roles"] + from_pages:
        key = scrape.link_key(role["url"])
        if key in seen:
            continue
        seen.add(key)
        roles.append({**role, "source": "careers page" if role.get("provider") == "careers_page" else "job board"})
    # Tier first, newest first within a tier, undated last. Two stable sorts.
    roles.sort(key=lambda r: (r.get("posted") or "", r["company"].lower()), reverse=True)
    roles.sort(key=lambda r: scrape.TIER_ORDER.get(r.get("tier") or "", 9))

    read_dates = sorted({s["read_on"] for s in sources if s["read_on"]})
    return {
        "roles": roles,
        "filters": get_filters(),
        "totals": {
            "roles": len(roles),
            "from_boards": sum(1 for r in roles if r["source"] == "job board"),
            "from_pages": sum(1 for r in roles if r["source"] == "careers page"),
            "already_tracked": ats["totals"]["already_tracked"] + already,
            "boards_checked": ats["totals"]["companies_checked"],
            "pages_read": len(sources),
            "pages_failing": sum(1 for s in sources if s["problem"]),
            "companies": len(Counter(r["company_id"] for r in roles)),
        },
        "pages_read_on": read_dates[-1] if read_dates else None,
        "oldest_page_read": read_dates[0] if read_dates else None,
        "board_errors": [c for c in ats["checked"] if c["error"]],
        "scrape": scrape_status(),
    }


# --------------------------------------------------------------------------
# running the scraper from the dashboard
# --------------------------------------------------------------------------
#
# A subprocess, not a thread: a full run is minutes of Playwright, and the API
# must stay responsive. The command is exactly what a person would type, so a
# run started here and one started in a terminal behave the same, and its
# output goes to a log the tab tails.

SCOPES = {
    "startups": ["--tier", "growth,early"],
    "targets": ["--status", "target"],
    "top": ["--tier", "faang,tier1"],
    "mid": ["--tier", "tier2"],
    "all": [],
}
_lock = threading.Lock()
_run: dict[str, Any] = {"proc": None, "scope": None, "started_at": None}


def _log_path() -> Path:
    return jsonstore.DATA_DIR / "scrape-run.log"


def start_scrape(scope: str = "startups", names: list[str] | None = None) -> dict[str, Any]:
    if scope not in SCOPES and not names:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    with _lock:
        proc = _run["proc"]
        if proc is not None and proc.poll() is None:
            raise RuntimeError("a scrape is already running")
        args = ["--only", ",".join(names)] if names else SCOPES[scope]
        cmd = [sys.executable, str(Path(scrape.__file__).resolve()), *args]
        log = _log_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        handle = log.open("w", encoding="utf-8")
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _run["proc"] = subprocess.Popen(
            cmd, stdout=handle, stderr=subprocess.STDOUT, cwd=str(Path(scrape.__file__).resolve().parent.parent),
            env=env, creationflags=flags,
        )
        handle.close()  # the child holds its own handle
        _run["scope"] = ", ".join(names) if names else scope
        _run["started_at"] = jsonstore.today()
    return scrape_status()


def scrape_status() -> dict[str, Any]:
    proc = _run["proc"]
    running = proc is not None and proc.poll() is None
    tail: list[str] = []
    log = _log_path()
    if log.exists():
        try:
            tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-12:]
        except OSError:
            tail = []
    return {
        "running": running,
        "scope": _run["scope"],
        "started_at": _run["started_at"],
        "exit_code": None if proc is None or running else proc.returncode,
        "log_tail": tail,
        "scopes": list(SCOPES),
    }


# --------------------------------------------------------------------------
# finding companies
# --------------------------------------------------------------------------


def suggestions() -> list[dict[str, Any]]:
    """Curated companies that aren't on the board: the catalogue, plus seed entries removed."""
    board = companies.list_companies()
    out = []
    for entry in company_seed.CATALOGUE + company_seed.SEED:
        if any(companies.matches(c, entry["name"]) for c in board):
            continue
        out.append({**entry, "from": "catalogue" if entry in company_seed.CATALOGUE else "curated list"})
    return out


def add_suggestions(names: list[str]) -> dict[str, Any]:
    wanted = {companies.norm_name(n) for n in names}
    picked = [e for e in company_seed.CATALOGUE + company_seed.SEED if companies.norm_name(e["name"]) in wanted]
    if not picked:
        raise ValueError("none of those names is in the catalogue")
    return companies.seed(picked)
