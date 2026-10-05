"""Find newly posted roles at the companies on the board.

**This does not scrape HTML.** Greenhouse, Lever and Ashby each publish a
documented, public, unauthenticated JSON endpoint that job aggregators are
meant to consume, and every company on the board that uses one is wired to it
by `ats_provider` + `ats_token`. Parsing JSON that a company publishes for this
exact purpose is stable; parsing their careers page is not — it breaks on the
next redesign, and it is rude besides. Companies with no supported board keep
`ats_provider: "none"`, and the assistant falls back to WebSearch for those
(see the discovery section of ai.py's system prompt).

Everything from `parse` down is a pure function over a payload, so the whole
normalise -> filter -> dedupe pipeline is testable without a network call —
which is what selftest.py exercises.

Results are deliberately **not persisted**. jobs.json is already the ledger of
what you're tracking; a second store of "roles I saw once" would need its own
expiry rules and would immediately disagree with it. A discovered role becomes
real when you promote it into a job record.
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

import httpx

import companies
import storage
from jsonstore import today

PROVIDERS = ["greenhouse", "lever", "ashby"]

_ENDPOINTS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}

# Be identifiable rather than anonymous — these are public APIs and we are a
# well-behaved, low-volume client.
_HEADERS = {"User-Agent": "job-tracker/1.0 (personal job search; single user)"}

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# Boards change a few times a day at most, so a short cache turns "re-run the
# search with different filters" into zero extra requests.
CACHE_TTL_SECONDS = 900
_MAX_CONCURRENCY = 6
DESCRIPTION_LIMIT = 6000

_cache: dict[tuple[str, str], tuple[float, Any]] = {}


def clear_cache() -> None:
    _cache.clear()


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_BLANKS = re.compile(r"\n{3,}")


def strip_html(raw: str | None) -> str:
    """Good-enough HTML -> text. Greenhouse returns escaped HTML; the others
    hand us plain text already, so this is not on the hot path."""
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|h[1-6]|tr)>", "\n\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = _TAG.sub("", text)
    text = html.unescape(text)
    return _BLANKS.sub("\n\n", text).strip()


def _iso_day(value: Any) -> str | None:
    """Normalise every provider's timestamp flavour down to YYYY-MM-DD."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):  # lever: epoch milliseconds
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value)[:10]
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None


# --------------------------------------------------------------------------
# seniority + location
# --------------------------------------------------------------------------

# Word-boundary anchored, not substring: an earlier version looked for "i " to
# catch "Engineer I" and duly classified "Principal AI Security Specialist" as
# entry level, because "ai " ends in "i ". Level words are whole words.
#
# Ordered, first hit wins. intern precedes senior so "Senior Data Science
# Intern" reads as intern; senior precedes entry so "Associate Director" reads
# as senior rather than being caught by "associate".
_SENIORITY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("intern", re.compile(r"\b(intern|internship|trainee|apprentice|co-?op)\b")),
    # "(?<!technical )staff" because the AI labs on this board — OpenAI,
    # Sarvam, Perplexity — title every IC level "Member of Technical Staff".
    # Reading that as senior would hide their entire board from a SWE2 search.
    ("senior", re.compile(
        r"\b(senior|sr\.?|(?<!technical )staff|principal|lead|architect|manager|director|"
        r"head|vp|president|distinguished|fellow|iii|iv)\b"
    )),
    ("entry", re.compile(
        r"\b(new\s+grad(uate)?|campus|entry[\s-]level|fresher|early\s+career|associate|"
        r"graduate\s+engineer|engineer\s+i|sde\s*-?\s*1|swe\s*-?\s*1)\b"
    )),
]


def guess_seniority(title: str) -> str:
    """Rough bucket from the title alone, so SWE2-level roles can be isolated.

    A guess, and labelled as one — titles are not a reliable level signal
    ("Member of Technical Staff" could be anything). It filters the obvious
    mismatches (internships, director roles) and nothing more.
    """
    haystack = title.lower()
    for level, pattern in _SENIORITY_RULES:
        if pattern.search(haystack):
            return level
    return "mid"


# Cities that carry most Indian engineering hiring, plus the spellings and
# abbreviations job boards actually use.
INDIA_TOKENS = (
    "india", "bengaluru", "bangalore", "blr", "hyderabad", "hyd", "pune",
    "chennai", "mumbai", "delhi", "gurgaon", "gurugram", "noida", "ncr",
    "kolkata", "ahmedabad", "jaipur", "kochi", "cochin", "trivandrum",
    "thiruvananthapuram", "coimbatore", "indore", "bhubaneswar", "chandigarh",
    "mysuru", "mysore", "vizag", "visakhapatnam", "nagpur",
)

_REMOTE_TOKENS = ("remote", "anywhere", "work from home", "distributed")


# --------------------------------------------------------------------------
# experience — "2 - 5 Years" in a board's field, "3+ years of experience" in a JD
# --------------------------------------------------------------------------

_YEARS = r"(?:years?|yrs?)\b"
_NUM = r"(\d{1,2}(?:\.\d)?)"
_EXP_RANGE = re.compile(rf"{_NUM}\s*(?:-|–|—|to)\s*{_NUM}\s*\+?\s*{_YEARS}", re.I)
_EXP_PLUS = re.compile(rf"{_NUM}\s*\+\s*{_YEARS}", re.I)
_EXP_AT_LEAST = re.compile(
    rf"(?:minimum|min\.?|at\s+least|over|more\s+than)\s+(?:of\s+)?{_NUM}\s*\+?\s*{_YEARS}", re.I
)
_EXP_SINGLE = re.compile(rf"{_NUM}\s*{_YEARS}", re.I)
_FRESHER = re.compile(r"\b(freshers?|new\s+grad(uate)?s?|0\s*years?)\b", re.I)
# A JD mentions years for plenty of reasons ("founded 12 years ago"); only a
# figure near the word experience is read as a requirement.
_EXP_WORD = re.compile(r"\bexp(erience|\.)?\b", re.I)
_EXP_WINDOW = 90
_EXP_CEILING = 30  # a bigger number is a company age or a typo, not a requirement


def _exp_in(text: str) -> tuple[float, float | None] | None:
    """The first years figure in a short string: a range, an "N+", or a single N."""
    for pattern, kind in ((_EXP_RANGE, "range"), (_EXP_AT_LEAST, "min"), (_EXP_PLUS, "min"),
                          (_EXP_SINGLE, "single")):
        match = pattern.search(text)
        if not match:
            continue
        lo = float(match.group(1))
        if kind == "range":
            hi: float | None = float(match.group(2))
            lo, hi = min(lo, hi), max(lo, hi)
        elif kind == "min":
            hi = None
        else:
            hi = lo
        if lo > _EXP_CEILING:
            continue
        return lo, hi
    if _FRESHER.search(text):
        return 0.0, 0.0
    return None


def parse_experience(text: str | None, *, structured: bool = False) -> tuple[float, float | None] | None:
    """Years of experience a posting asks for, as (min, max), max None when open-ended.

    `structured` is for a field that holds nothing but experience ("2 - 5 Years",
    Darwinbox's `experience`), where any figure counts. Free text (a title, a JD)
    is only read within a short window of the word "experience", so a company's
    age or a team's size isn't mistaken for a requirement. The first such
    figure wins: JDs open with the headline requirement and then list
    sub-skills ("3+ years overall; 1+ year with Kafka").
    """
    if not text:
        return None
    if structured:
        return _exp_in(text)
    for match in _EXP_WORD.finditer(text):
        start = max(0, match.start() - _EXP_WINDOW)
        window = text[start: match.end() + _EXP_WINDOW]
        found = _exp_in(window)
        if found:
            return found
    return None


def format_experience(exp: tuple[float, float | None] | None) -> str:
    if not exp:
        return ""
    lo, hi = (f"{v:g}" if v is not None else None for v in exp)
    if hi is None:
        return f"{lo}+ yrs"
    return f"{lo} yrs" if lo == hi else f"{lo}-{hi} yrs"


def experience_fits(
    role: dict[str, Any], want: tuple[float, float] | None, *, required: bool = False
) -> bool:
    """Does the posting's range overlap the range wanted?

    Overlap, not containment: "2-5 years" is open to someone with 2, and a
    3+-year bar is reachable from a 0-3 search. A posting that states no figure
    is kept unless `required` — most careers pages never say, and dropping
    them would empty the list.
    """
    if not want:
        return True
    lo, hi = role.get("exp_min"), role.get("exp_max")
    if lo is None:
        return not required
    want_lo, want_hi = want
    return lo <= want_hi and (hi is None or hi >= want_lo)


def _is_remote(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _REMOTE_TOKENS)


def location_matches(role_locations: Iterable[str], wanted: Iterable[str]) -> bool:
    haystack = " | ".join(role_locations).lower()
    return any(token.lower() in haystack for token in wanted)


# --------------------------------------------------------------------------
# provider parsers — pure functions over a decoded payload
# --------------------------------------------------------------------------


def _role(
    company: dict[str, Any],
    provider: str,
    *,
    title: str,
    url: str,
    locations: list[str],
    posted: str | None,
    department: str = "",
    employment_type: str = "",
    description: str = "",
    experience: tuple[float, float | None] | None = None,
) -> dict[str, Any]:
    locations = [loc for loc in (l.strip() for l in locations) if loc]
    # A board's own field wins, then the title ("SDE (2-4 yrs)"), then the JD —
    # read in full, before it is truncated for storage.
    exp = (
        experience
        or parse_experience(title)
        or parse_experience(description)
    )
    return {
        "company": company.get("name", ""),
        "company_id": company.get("id"),
        "category": company.get("category"),
        "tier": company.get("tier"),
        "provider": provider,
        "title": (title or "").strip(),
        "url": url,
        "location": ", ".join(locations) if locations else "",
        "locations": locations,
        "remote": any(_is_remote(loc) for loc in locations),
        "posted": posted,
        "department": (department or "").strip(),
        "employment_type": (employment_type or "").strip(),
        "seniority": guess_seniority(title or ""),
        "exp_min": exp[0] if exp else None,
        "exp_max": exp[1] if exp else None,
        "experience": format_experience(exp),
        "description": description[:DESCRIPTION_LIMIT],
    }


def _parse_greenhouse(payload: Any, company: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    out = []
    for job in jobs:
        location = (job.get("location") or {}).get("name", "")
        out.append(
            _role(
                company,
                "greenhouse",
                title=job.get("title", ""),
                url=job.get("absolute_url", ""),
                locations=[location] if location else [],
                # first_published is when it went up; updated_at moves on every
                # edit, so it would make an old posting look new.
                posted=_iso_day(job.get("first_published") or job.get("updated_at")),
                department=", ".join(
                    d.get("name", "") for d in job.get("departments", []) if d.get("name")
                ),
                description=strip_html(job.get("content")),
            )
        )
    return out


def _parse_lever(payload: Any, company: dict[str, Any]) -> list[dict[str, Any]]:
    postings = payload if isinstance(payload, list) else []
    out = []
    for job in postings:
        categories = job.get("categories") or {}
        locations = job.get("allLocations") or []
        if not locations and categories.get("location"):
            locations = [categories["location"]]
        out.append(
            _role(
                company,
                "lever",
                title=job.get("text", ""),
                url=job.get("hostedUrl") or job.get("applyUrl", ""),
                locations=list(locations),
                posted=_iso_day(job.get("createdAt")),
                department=categories.get("department") or categories.get("team") or "",
                employment_type=categories.get("commitment") or "",
                description=job.get("descriptionPlain") or strip_html(job.get("description")),
            )
        )
    return out


def _parse_ashby(payload: Any, company: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    out = []
    for job in jobs:
        # isListed false means it's on the board but deliberately unpublished.
        if job.get("isListed") is False:
            continue
        locations = [job.get("location") or ""]
        locations += [
            (sec or {}).get("location", "") for sec in job.get("secondaryLocations") or []
        ]
        if job.get("isRemote"):
            locations.append("Remote")
        out.append(
            _role(
                company,
                "ashby",
                title=job.get("title", ""),
                url=job.get("jobUrl") or job.get("applyUrl", ""),
                locations=locations,
                posted=_iso_day(job.get("publishedAt")),
                department=job.get("department") or job.get("team") or "",
                employment_type=job.get("employmentType") or "",
                description=job.get("descriptionPlain") or strip_html(job.get("descriptionHtml")),
            )
        )
    return out


_PARSERS = {
    "greenhouse": _parse_greenhouse,
    "lever": _parse_lever,
    "ashby": _parse_ashby,
}


def parse(provider: str, payload: Any, company: dict[str, Any]) -> list[dict[str, Any]]:
    parser = _PARSERS.get(provider)
    if not parser:
        return []
    return [r for r in parser(payload, company) if r["title"] and r["url"]]


# --------------------------------------------------------------------------
# filtering + dedupe — also pure
# --------------------------------------------------------------------------


def matches_keywords(role: dict[str, Any], keywords: Iterable[str]) -> bool:
    """Keyword hit on the title or department.

    Anchored at the start of a word but not the end, which is the useful
    middle ground for job titles: "engineer" still matches "Engineering", while
    "ai" no longer matches "Retail" and "ml" no longer matches "HTML".
    """
    needles = [k.strip().lower() for k in keywords if k.strip()]
    if not needles:
        return True
    haystack = f"{role['title']} {role['department']}".lower()
    return any(re.search(rf"\b{re.escape(needle)}", haystack) for needle in needles)


# Titles that match an engineering keyword while being nothing of the sort —
# "Sales Engineer", "Enterprise Sales - AI Services". Applied by default
# because every real search wants them gone; pass exclude_keywords explicitly
# to override.
NOISE_KEYWORDS = (
    "sales", "account executive", "business development", "marketing",
    "recruiter", "talent acquisition", "customer success", "collections",
)


def filter_roles(
    roles: list[dict[str, Any]],
    *,
    keywords: Iterable[str] = (),
    exclude_keywords: Iterable[str] = NOISE_KEYWORDS,
    locations: Iterable[str] = INDIA_TOKENS,
    include_remote: bool = False,
    max_age_days: int | None = None,
    exclude_seniority: Iterable[str] = (),
    experience: tuple[float, float] | None = None,
    experience_required: bool = False,
    as_of: date | None = None,
) -> list[dict[str, Any]]:
    excluded = {s.lower() for s in exclude_seniority}
    banned = [k for k in exclude_keywords if k.strip()]
    wanted = list(locations)
    cutoff = None
    if max_age_days is not None:
        cutoff = ((as_of or date.today()) - timedelta(days=max_age_days)).isoformat()

    out = []
    for role in roles:
        if not matches_keywords(role, keywords):
            continue
        if banned and matches_keywords(role, banned):
            continue
        if wanted:
            here = location_matches(role["locations"], wanted)
            # Remote is opt-in: "Remote - US" is not an Indian role.
            if not here and not (include_remote and role["remote"]):
                continue
        if role["seniority"] in excluded:
            continue
        if not experience_fits(role, experience, required=experience_required):
            continue
        # A posting with no date is kept — missing metadata shouldn't hide a
        # real role. Only a date we can read and that is too old excludes one.
        if cutoff and role["posted"] and role["posted"] < cutoff:
            continue
        out.append(role)
    return out


def _url_key(url: str) -> str:
    return re.sub(r"[?#].*$", "", (url or "").strip().rstrip("/").lower())


def dedupe(
    roles: list[dict[str, Any]], jobs: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Drop roles already in jobs.json, and collapse duplicates within a board.

    Matched on URL first, then on (organisation, title) — the same role often
    appears once per city, and a record you saved by hand won't share a URL.
    """
    tracked_urls = {_url_key(j.get("url") or "") for j in jobs if j.get("url")}
    tracked_urls.discard("")
    tracked_titles = {
        (companies.norm_name(j.get("organisation")), companies.norm_name(j.get("job_title")))
        for j in jobs
    }

    kept: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_titles: set[tuple[str, str]] = set()
    already = 0

    for role in roles:
        url_key = _url_key(role["url"])
        title_key = (companies.norm_name(role["company"]), companies.norm_name(role["title"]))
        if url_key in tracked_urls or title_key in tracked_titles:
            already += 1
            continue
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        kept.append(role)
    return kept, already


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------


async def fetch_board(
    client: httpx.AsyncClient, provider: str, token: str, *, force: bool = False
) -> Any:
    key = (provider, token)
    hit = _cache.get(key)
    if hit and not force and (time.monotonic() - hit[0]) < CACHE_TTL_SECONDS:
        return hit[1]

    url = _ENDPOINTS[provider].format(token=token)
    params = {"content": "true"} if provider == "greenhouse" else None
    response = await client.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    if response.status_code == 404:
        raise LookupError(f"no {provider} board called '{token}'")
    response.raise_for_status()
    payload = response.json()
    _cache[key] = (time.monotonic(), payload)
    return payload


async def _check_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    company: dict[str, Any],
    force: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    async with semaphore:
        try:
            payload = await fetch_board(
                client, company["ats_provider"], company["ats_token"], force=force
            )
            return company, parse(company["ats_provider"], payload, company), None
        except LookupError as exc:
            # A dead token is a data problem worth surfacing, not a crash.
            return company, [], str(exc)
        except httpx.HTTPStatusError as exc:
            return company, [], f"HTTP {exc.response.status_code}"
        except httpx.HTTPError as exc:
            return company, [], f"{type(exc).__name__}: {exc}"
        except ValueError as exc:  # malformed JSON
            return company, [], f"bad response: {exc}"


async def search(
    *,
    company_ids: list[str] | None = None,
    keywords: Iterable[str] = (),
    exclude_keywords: Iterable[str] = NOISE_KEYWORDS,
    locations: Iterable[str] = INDIA_TOKENS,
    include_remote: bool = False,
    max_age_days: int | None = None,
    exclude_seniority: Iterable[str] = (),
    experience: tuple[float, float] | None = None,
    experience_required: bool = False,
    limit: int = 100,
    include_description: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Check every wired board and return roles that are new to you."""
    targets = companies.fetchable()
    if company_ids:
        wanted = set(company_ids)
        targets = [c for c in targets if c["id"] in wanted]

    if not targets:
        return {
            "roles": [],
            "checked": [],
            "totals": {
                "companies_checked": 0,
                "roles_seen": 0,
                "after_filters": 0,
                "already_tracked": 0,
                "errors": 0,
            },
            "ran_at": today(),
            "note": (
                "No company on the board has a supported job board wired up. Add "
                "ats_provider and ats_token to a company, or ask the assistant to "
                "search the web instead."
            ),
        }

    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            *(_check_one(client, semaphore, c, force) for c in targets)
        )

    raw: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    stamps: dict[str, tuple[int | None, str | None]] = {}
    for company, roles, error in results:
        raw.extend(roles)
        checked.append(
            {
                "company": company["name"],
                "company_id": company["id"],
                "provider": company["ats_provider"],
                "found": len(roles),
                "error": error,
            }
        )
        stamps[company["id"]] = (None if error else len(roles), error)

    # One write for the whole run, not one per company.
    companies.record_discovery_many(stamps)

    filtered = filter_roles(
        raw,
        keywords=keywords,
        exclude_keywords=exclude_keywords,
        locations=locations,
        include_remote=include_remote,
        max_age_days=max_age_days,
        exclude_seniority=exclude_seniority,
        experience=experience,
        experience_required=experience_required,
    )
    fresh, already = dedupe(filtered, storage.list_jobs())
    # Newest first; undated postings sort last rather than jumping the queue.
    fresh.sort(key=lambda r: (r["posted"] or "", r["company"]), reverse=True)

    trimmed = fresh[:limit]
    if not include_description:
        trimmed = [{**r, "description": ""} for r in trimmed]

    return {
        "roles": trimmed,
        "checked": sorted(checked, key=lambda c: -c["found"]),
        "totals": {
            "companies_checked": len(targets),
            "roles_seen": len(raw),
            "after_filters": len(filtered),
            "already_tracked": already,
            "new": len(fresh),
            "errors": sum(1 for c in checked if c["error"]),
        },
        "ran_at": today(),
    }


# --------------------------------------------------------------------------
# promotion
# --------------------------------------------------------------------------


def to_job(role: dict[str, Any], status: str = "saved") -> dict[str, Any]:
    """Turn a discovered role into a job record.

    Defaults to "saved" — discovery finds leads, and a lead is not an
    application. storage.stats() keeps saved records out of every rate
    denominator, so auto-discovery can't quietly wreck your response rate.
    """
    provider = role.get("provider", "board")
    where = "careers page" if provider == "careers_page" else f"{provider} board"
    return {
        "job_title": role.get("title", ""),
        "organisation": role.get("company", ""),
        "status": status,
        "url": role.get("url"),
        "location": role.get("location") or None,
        "date_job_posted": role.get("posted"),
        "company_type": role.get("category"),
        "source": "careers_page",
        "found_via": f"tracker discovery — {where}",
        "job_description": role.get("description", "") or "",
        "latest_update": f"Found on {role.get('company', 'their')} {where}",
    }
