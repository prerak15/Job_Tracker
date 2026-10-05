"""Open roles from careers pages that publish no JSON board — Playwright, script-first.

`discover.py` reads the Greenhouse / Lever / Ashby JSON endpoints and nothing
else. That leaves the companies with `ats_provider: "none"`, almost all of which
run their own careers site. This module visits those pages in a headless
browser, applies your filters, extracts the matching roles and their links, and
writes them to an Excel workbook (`roles_xlsx.py`).

**The point is to spend no tokens.** A run is one command with no model in the
loop, and it speaks to the terminal only when something is wrong — one summary
line on success, one `FAIL` line per company it could not read, each pointing at
a snapshot directory. Fixing a failure means reading that small directory and
patching one entry in `data/career-sites.json`, then re-running with `--only`.

    python backend/scrape.py --tier faang,tier1 --status target
    python backend/scrape.py --only "Nvidia" --probe
    python backend/scrape.py --keywords "backend,python" --max-age-days 14

Extraction strategies, cheapest and most robust first. The first that returns
roles wins, and the winner is saved so the next run replays it directly:

1. **xhr** — the page's own JSON. Careers sites load their listings from an API
   call; listening for that response survives a redesign in a way a CSS selector
   does not. The field mapping is guessed once and stored.
2. **dom** — per-site selectors from `career-sites.json` (hand-written or fixed
   from a snapshot), with an optional "next" control.
3. **links** — every anchor whose href looks like a job path. Blunt, and the
   fallback of last resort.

Rules this module keeps, and why:

* **One visit per company per run, a few at a time.** This is a personal tool,
  not a crawler.
* **No login walls, no CAPTCHA bypass.** A 403/429, a challenge page or a login
  wall is classified `blocked` and reported. LinkedIn is skipped outright.
* **A company with no readable roles is a finding, not an empty result.** The
  filtered search link is still written to the workbook so the run always hands
  you something clickable.
* The pure functions (URL templating, JSON mapping, link heuristics, filtering,
  assembly) never import Playwright; selftest.py exercises them with no browser
  and no network.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, parse_qsl, quote_plus, urlencode, urljoin, urlsplit, urlunsplit

import companies
import discover
import jsonstore
import roles_xlsx
import storage
from jsonstore import today

SITES_FILE = "career-sites.json"
# The last roles read from each careers page, unfiltered, for the dashboard's Open
# roles tab. A snapshot per company that each successful read replaces, not a
# ledger: jobs.json is the ledger, and a role becomes real only when tracked.
SCRAPED_FILE = "scraped-roles.json"
FILTERS_FILE = "role-filters.json"

SITE_TIMEOUT_S = 60
DEFAULT_WORKERS = 3
SCROLLS = 4
MAX_PAGES = 8  # "load more" clicks / "next" pages per site; career-sites.json can raise it
# A site that reports a total and yields fewer than this share of it is under-covered.
PARTIAL_BELOW = 0.5
# Problems that still carry usable rows: they are warnings with a snapshot, not dead ends.
KEEP_ROWS = ("layout_changed", "partial", "timeout")
STRATEGIES = ("xhr", "dom", "links")
TIER_ORDER = {"faang": 0, "tier1": 1, "tier2": 2, "growth": 3, "early": 4}

# Hosts that are skipped outright, with the reason shown in the workbook.
SKIP_HOSTS = {"linkedin.com": "login wall and terms of service"}

# Software engineer / developer, ML engineer and AI engineer roles.
# "software" rather than "software engineer": Amazon's title is "Software Development
# Engineer", which a two-word needle never matches. Bare "engineer" is too broad (it
# admits hardware and mechanical roles), and bare "ai" admitted "AI Success Manager"
# and "AI Data Analyst", so the AI/ML titles are spelled out instead.
ROLE_KEYWORDS = (
    "software", "sde", "swe", "developer", "backend", "back end", "full stack", "fullstack",
    "frontend", "front end", "machine learning", "ml engineer", "mlops", "ai engineer",
    "ai/ml", "ml/ai", "applied ai", "genai", "gen ai", "llm", "data engineer",
    "platform engineer", "member of technical staff",
)

DEFAULT_FILTERS: dict[str, Any] = {
    "_note": (
        "keywords match a title or department by word prefix; locations null means the "
        "India city list from discover.py. primary_query is one search term baked into a "
        "site's own URL when that site has a keyword parameter; leave it empty to read "
        "the whole (location-filtered) list and let the keywords filter client-side, "
        "which keeps 'Machine Learning Engineer' from being lost to a 'software engineer' search."
    ),
    "primary_query": "",
    "keywords": list(ROLE_KEYWORDS),
    "locations": None,
    "exclude_keywords": None,
    "include_remote": False,
    "max_age_days": None,
    # Early-to-mid career. The range is matched by overlap ("2-5 years" stays, "6-9"
    # goes), and a posting that states no figure is kept unless required is true.
    "experience": {"min": 0, "max": 3, "required": False},
    "exclude_seniority": ["senior", "intern"],
}


def snapshot_root() -> Path:
    return jsonstore.DATA_DIR / "scrape-snapshots"


def export_dir() -> Path:
    return jsonstore.DATA_DIR.parent / "exports"


# --------------------------------------------------------------------------
# filters
# --------------------------------------------------------------------------


def load_filters(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """data/role-filters.json, created with defaults on first use, plus CLI overrides."""
    path = jsonstore.DATA_DIR / FILTERS_FILE
    stored: dict[str, Any] = {}
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON ({exc}).") from exc
    else:
        jsonstore.write(FILTERS_FILE, dict(DEFAULT_FILTERS))

    merged = {**DEFAULT_FILTERS, **{k: v for k, v in stored.items() if v is not None}}
    for key, value in (overrides or {}).items():
        if value is not None:
            merged[key] = value
    if merged.get("locations") is None:
        merged["locations"] = list(discover.INDIA_TOKENS)
    if merged.get("exclude_keywords") is None:
        merged["exclude_keywords"] = list(discover.NOISE_KEYWORDS)
    merged["experience"] = experience_range(merged.get("experience"))
    merged["exclude_seniority"] = list(merged.get("exclude_seniority") or [])
    return merged


def experience_range(value: Any) -> dict[str, Any] | None:
    """{"min", "max", "required"} from the file, a CLI "0-3", or None for no filter."""
    if value in (None, "", False):
        return None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*", value)
        if not match:
            raise ValueError(f"experience should look like 0-3, not {value!r}")
        value = {"min": float(match.group(1)), "max": float(match.group(2))}
    lo = float(value.get("min") or 0)
    hi = float(value["max"]) if value.get("max") is not None else 99.0
    return {"min": min(lo, hi), "max": max(lo, hi), "required": bool(value.get("required"))}


def _experience_label(exp: dict[str, Any] | None) -> str:
    if not exp:
        return "any"
    span = f"{exp['min']:g}-{exp['max']:g}"
    return span + (" (postings must state it)" if exp["required"] else " (unstated postings kept)")


def experience_args(filters: dict[str, Any]) -> dict[str, Any]:
    """The experience part of `discover.filter_roles`' arguments."""
    exp = filters.get("experience")
    if not exp:
        return {"experience": None, "experience_required": False}
    return {"experience": (exp["min"], exp["max"]), "experience_required": exp["required"]}


# --------------------------------------------------------------------------
# per-site config — data/career-sites.json, written by the scraper itself
# --------------------------------------------------------------------------


def load_sites() -> dict[str, dict[str, Any]]:
    return {s["company_id"]: s for s in jsonstore.read(SITES_FILE, "sites")["sites"]}


def save_sites(sites: dict[str, dict[str, Any]]) -> None:
    ordered = sorted(sites.values(), key=lambda s: s.get("name", "").lower())
    jsonstore.write(SITES_FILE, {"sites": ordered})


def skip_reason(company: dict[str, Any], site: dict[str, Any] | None) -> str | None:
    if site and site.get("strategy") == "skip":
        return site.get("skip_reason") or "marked skip"
    host = urlsplit(company.get("careers_url") or "").netloc.lower()
    for fragment, reason in SKIP_HOSTS.items():
        if host == fragment or host.endswith("." + fragment):
            return reason
    return None


# --------------------------------------------------------------------------
# URLs — the filters that can be set in the address bar are set there
# --------------------------------------------------------------------------

_QUERY_KEYS = {"q", "query", "keyword", "keywords", "search", "searchtext", "k", "text", "term"}


def keyword_template(careers_url: str) -> str:
    """Swap the value of the site's own keyword parameter for `{q}`.

    Most careers URLs already carry a location filter (`?location=India`); some
    carry a keyword parameter too. A URL with no keyword parameter is returned
    unchanged — the client-side filter does that site's keyword work.
    """
    parts = urlsplit(careers_url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    hit = False
    out = []
    for key, value in pairs:
        if key.lower() in _QUERY_KEYS:
            out.append((key, "{q}"))
            hit = True
        else:
            out.append((key, value))
    if not hit:
        return careers_url
    return urlunsplit(parts._replace(query=urlencode(out, safe="{}")))


def fill_url(template: str, query: str) -> str:
    return template.replace("{q}", quote_plus(query))


def default_url_base(careers_url: str) -> str | None:
    """Workday returns paths relative to the *site*, not the host."""
    parts = urlsplit(careers_url)
    if parts.netloc.lower().endswith("myworkdayjobs.com"):
        return urlunsplit(parts._replace(query="", fragment="")).rstrip("/")
    return None


def build_url(raw: Any, *, page_url: str, url_base: str | None) -> str | None:
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    if raw.lower().startswith(("http://", "https://")):
        return raw
    if url_base:
        return url_base.rstrip("/") + "/" + raw.lstrip("/")
    return urljoin(page_url, raw)


# --------------------------------------------------------------------------
# JSON mapping (strategy: xhr) — pure functions over decoded payloads
# --------------------------------------------------------------------------

_TITLE_KEYS = (
    "title", "jobTitle", "job_title", "jobtitle", "postingTitle", "positionTitle", "reqTitle",
    "positionName", "jobName", "job_name", "designation", "name", "text", "displayName",
)
_URL_KEYS = (
    "absolute_url", "hostedUrl", "applyUrl", "applyURL", "apply_url", "jobUrl", "job_url",
    "jobLink", "job_link", "job_path", "jobPath", "jobPostingUrl", "postingUrl",
    "canonicalPositionUrl", "detailsUrl", "detailUrl", "detail_url", "externalPath",
    "externalUrl", "permalink", "uri", "url", "link", "href", "path",
)
_LOC_KEYS = (
    "locationsText", "location", "locations", "primaryLocation", "city", "office",
    "offices", "locationName", "jobLocation", "location_name", "work_location", "cityState",
)
_DATE_KEYS = (
    "postedOn", "posted_on", "postedDate", "posted_date", "datePosted", "date_posted",
    "publishedAt", "publish_date", "created_at", "createdAt", "updated_at", "posted",
)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def find_job_lists(payload: Any, *, max_depth: int = 5) -> list[tuple[str, list[Any]]]:
    """Every list of 3+ objects in the payload, with the dotted path that reaches it."""
    found: list[tuple[str, list[Any]]] = []

    def walk(node: Any, path: str, depth: int) -> None:
        if depth > max_depth:
            return
        if isinstance(node, list):
            if len(node) >= 3 and all(isinstance(i, dict) for i in node[:5]):
                found.append((path, node))
            return
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, f"{path}.{key}" if path else str(key), depth + 1)

    walk(payload, "", 0)
    return found


def guess_field_map(items: list[Any], path: str) -> dict[str, Any] | None:
    """Which keys hold the title, link, location and date — or None if this isn't jobs.

    A job list has a title *and* a link on most rows, and titles that read like
    titles. That last test is what stops a facet list ("India", "Bengaluru") from
    being mistaken for roles.
    """
    sample = [i for i in items if isinstance(i, dict)]
    if len(sample) < 3:
        return None

    def pick(keys: tuple[str, ...], want=_is_text) -> str | None:
        best: tuple[str, int] | None = None
        for key in keys:
            hits = sum(1 for row in sample if want(row.get(key)))
            if hits >= max(3, len(sample) * 0.6) and (best is None or hits > best[1]):
                best = (key, hits)
        return best[0] if best else None

    title = pick(_TITLE_KEYS)
    link = pick(_URL_KEYS)
    if not title or not link:
        return None
    titles = [row[title] for row in sample if _is_text(row.get(title))]
    if sum(len(t) for t in titles) / len(titles) < 10:
        return None
    return {
        "path": path,
        "title": title,
        "url": link,
        "location": pick(_LOC_KEYS, want=lambda v: bool(v)),
        "posted": pick(_DATE_KEYS, want=lambda v: v not in (None, "")),
        **guess_experience_keys(sample),
    }


_EXP_PAIRS = (
    ("minExperience", "maxExperience"), ("min_experience", "max_experience"),
    ("expMin", "expMax"), ("experience_from", "experience_to"), ("minExp", "maxExp"),
    ("experienceFrom", "experienceTo"), ("min_exp", "max_exp"),
)
_EXP_TEXT_KEYS = ("experience", "experienceRange", "experience_range", "yearsOfExperience", "workExperience")


def guess_experience_keys(sample: list[dict[str, Any]]) -> dict[str, str]:
    """Which keys carry years of experience, if most rows have them."""
    for lo, hi in _EXP_PAIRS:
        if sum(1 for row in sample if _years(row.get(lo)) is not None) >= len(sample) * 0.5:
            return {"exp_min": lo, "exp_max": hi}
    for key in _EXP_TEXT_KEYS:
        readable = sum(
            1 for row in sample
            if isinstance(row.get(key), str) and discover.parse_experience(row[key], structured=True)
        )
        if readable >= len(sample) * 0.5:
            return {"experience": key}
    return {}


def dig(payload: Any, path: str) -> Any:
    node = payload
    for part in path.split(".") if path else []:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def flat_location(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        # "location" before "name": an office record's name is the street address.
        for key in ("location", "name", "text", "label", "display", "city"):
            if _is_text(value.get(key)):
                return value[key].strip()
        return ""
    if isinstance(value, list):
        return ", ".join(p for p in (flat_location(v) for v in value) if p)
    return str(value)


def endpoint_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc}{parts.path}"


def rows_from_source(
    captured: list[tuple[str, Any]],
    endpoint: str,
    field_map: dict[str, Any],
    *,
    page_url: str,
    url_base: str | None,
) -> list[dict[str, Any]]:
    """Every response from one endpoint, merged — scrolling fires several pages of it."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url, payload in captured:
        if endpoint not in url:
            continue
        items = dig(payload, field_map["path"])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not _is_text(item.get(field_map["title"])):
                continue
            if field_map.get("url_template") and item.get(field_map.get("id")) not in (None, ""):
                # Some APIs expose only an id; a person supplies the URL pattern once.
                link = field_map["url_template"].replace(
                    "{id}", encode_id(item[field_map["id"]], field_map.get("id_encoding"))
                )
            else:
                link = build_url(
                    item.get(field_map.get("url")), page_url=page_url, url_base=url_base
                )
            if not link or link in seen:
                continue
            seen.add(link)
            rows.append(
                {
                    "title": item[field_map["title"]].strip(),
                    "url": link,
                    # Dotted paths reach nested fields (Kula's `ats_job.offices`).
                    "location": flat_location(dig(item, field_map["location"]))
                    if field_map.get("location")
                    else "",
                    "posted": dig(item, field_map["posted"]) if field_map.get("posted") else None,
                    "experience": row_experience(item, field_map),
                }
            )
    return rows


def encode_id(value: Any, encoding: str | None) -> str:
    """The id as the job URL wants it. MyNextHire hides it in base64 JSON (`p=`)."""
    if encoding == "mynexthire":
        payload = {
            "pageType": "jd", "cvSource": "careers", "reqId": value,
            "requester": {"id": "", "code": "", "name": ""},
            "page": "careers", "bufilter": -1, "customFields": {},
        }
        return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return str(value)


def known_field_map(url: str, path: str) -> dict[str, Any] | None:
    """Boards whose job list carries no link at all — the link is a fixed pattern on the id.

    `guess_field_map` needs a link field on most rows, so these are invisible to it,
    and their page anchors say "View and Apply" rather than the title, so `links`
    cannot read them either. Darwinbox is common enough among Indian startups
    (Locus, Ninjacart, Perfios, Pixxel) to recognise by its endpoint instead of
    hand-writing the same field_map per company. Kula (Acko, Plum, slice) is the
    same story; its id-only path redirects to the canonical `<id>-<slug>` posting.
    PyjamaHR (Kuku FM) renders cards that open on click, with no anchors at all.
    MyNextHire (Amagi) links a posting by a base64 JSON blob, see `encode_id`.
    Workable (Tiger Analytics, Apna) lists `shortcode`s.
    """
    parts = urlsplit(url)
    host = parts.netloc.lower()
    workable = re.fullmatch(r"/api/v3/accounts/([^/]+)/jobs/?", parts.path)
    if host == "apply.workable.com" and workable and path == "results":
        return {
            "path": "results",
            "title": "title",
            "id": "shortcode",
            "url_template": f"https://apply.workable.com/{workable.group(1)}/j/{{id}}/",
            "location": "location",
            "posted": "published",
        }
    if (
        host.endswith(".mynexthire.com")
        and parts.path.endswith("/employer/careers/reqlist/get")
        and path == "reqDetailsBOList"
    ):
        return {
            "path": "reqDetailsBOList",
            "title": "reqTitle",
            "id": "reqId",
            "id_encoding": "mynexthire",
            "url_template": f"https://{host}/employer/jobs/careers#?src=careers&p={{id}}&page=careers",
            "location": "location",
            "posted": "approvedOn",
            "exp_min": "expMin",
            "exp_max": "expMax",
        }
    if (
        parts.netloc.lower() == "api.pyjamahr.com"
        and parts.path.rstrip("/").endswith("/api/career/jobs")
        and path == "results"
    ):
        query = parse_qs(parts.query)
        uuid = (query.get("company_uuid") or [""])[0]
        slug = (query.get("company_slug") or [""])[0]
        if uuid or slug:
            # The jobs.pyjamahr.com board asks by company_slug and links postings by
            # their own slug; the embedded app.pyjamahr.com widget asks by uuid and
            # links by job_id.
            return {
                "path": "results",
                "title": "title",
                "id": "slug" if slug else "id",
                "url_template": f"https://jobs.pyjamahr.com/{slug}/{{id}}" if slug
                else f"https://app.pyjamahr.com/careers?company_uuid={uuid}&job_id={{id}}",
                "location": "location",
                "posted": None,
                "exp_min": "min_experience",
                "exp_max": "max_experience",
            }
    if (
        parts.netloc.lower() == "careers.kula.ai"
        and parts.path.endswith("/api/internal/ats_job_posts")
        and path == "data"
    ):
        account = (parse_qs(parts.query).get("accountName") or [""])[0]
        if account:
            return {
                "path": "data",
                "title": "title",
                "id": "id",
                "url_template": f"https://careers.kula.ai/{account}/{{id}}",
                "location": "ats_job.offices",
                "posted": "launch_at",
            }
    if (
        parts.netloc.lower().endswith(".darwinbox.in")
        and parts.path.endswith("/candidateapi/job/alljobs")
        and path == "data"
    ):
        tenant = (parse_qs(parts.query).get("companyId") or ["main"])[0]
        return {
            "path": "data",
            "title": "title",
            "id": "id",
            "url_template": f"https://{parts.netloc}/ms/candidatev2/{tenant}/careers/jobDetails/{{id}}",
            "location": "locations",
            "posted": "posted_on",
            "exp_min": "experience_from",
            "exp_max": "experience_to",
        }
    return None


def _years(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    try:
        years = float(value)
    except (TypeError, ValueError):
        return None
    return years if 0 <= years <= 40 else None


def row_experience(item: dict[str, Any], field_map: dict[str, Any]) -> tuple[float, float | None] | None:
    """Experience from a board's own fields: a min/max pair, or one text field."""
    if field_map.get("exp_min"):
        lo = _years(dig(item, field_map["exp_min"]))
        hi = _years(dig(item, field_map["exp_max"])) if field_map.get("exp_max") else None
        if lo is None:
            return None
        # A max of 0 under a min of 3 means "not set", not a backwards range.
        return (lo, hi if hi is not None and hi >= lo else None)
    if field_map.get("experience"):
        text = dig(item, field_map["experience"])
        return discover.parse_experience(str(text), structured=True) if text else None
    return None


def find_source(
    captured: list[tuple[str, Any]],
    endpoint: str | None,
    field_map: dict[str, Any] | None,
    *,
    page_url: str,
    url_base: str | None,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]] | None:
    """Replay the saved mapping if there is one; otherwise guess from what loaded."""
    if endpoint and field_map:
        rows = rows_from_source(captured, endpoint, field_map, page_url=page_url, url_base=url_base)
        if rows:
            return endpoint, field_map, rows

    best: tuple[int, str, dict[str, Any]] | None = None
    for url, payload in captured:
        for path, items in find_job_lists(payload):
            mapping = guess_field_map(items, path) or known_field_map(url, path)
            if mapping and (best is None or len(items) > best[0]):
                best = (len(items), endpoint_of(url), mapping)
    if not best:
        return None
    _, found_endpoint, mapping = best
    rows = rows_from_source(captured, found_endpoint, mapping, page_url=page_url, url_base=url_base)
    return (found_endpoint, mapping, rows) if rows else None


_TOTAL_KEYS = (
    "total", "totalCount", "total_count", "totalResults", "numFound", "count", "hits",
    "totalHits", "total_hits", "totalJobs", "total_jobs", "job_counts",
)


def source_total(captured: list[tuple[str, Any]], endpoint: str, field_map: dict[str, Any]) -> int | None:
    """How many roles the site says it has, if its response says so.

    Read from the object that holds the list, or the root. The latest non-zero
    figure wins: Workday reports it on the first page only (later pages say 0),
    and Workable loads the whole board before narrowing it to the visitor's
    country, so its *first* total (161) describes a list nobody asked for and the
    refined one (4) is the list on screen. Taking the largest read that as
    "partial" on every run.
    """
    latest = 0
    path = field_map["path"]
    for url, payload in captured:
        if endpoint not in url:
            continue
        holder = dig(payload, path.rsplit(".", 1)[0]) if "." in path else payload
        meta = payload.get("meta") if isinstance(payload, dict) else None
        here = 0
        for node in (holder, payload, meta):
            if isinstance(node, dict):
                for key in _TOTAL_KEYS:
                    value = node.get(key)
                    if isinstance(value, int) and not isinstance(value, bool):
                        here = max(here, value)
        latest = here or latest
    return latest or None


def merge_rows(have: list[dict[str, Any]], more: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = {r["url"] for r in have}
    return have + [r for r in more if r["url"] not in seen]


# --------------------------------------------------------------------------
# anchor heuristic (strategy: links)
# --------------------------------------------------------------------------

_JOB_HREF = re.compile(
    r"/(jobs?|job-?details?|positions?|openings?|requisitions?|vacanc(?:y|ies)|"
    r"opportunit(?:y|ies)|roles?)/[^/?#]+|[?&](jobid|job_id|gh_jid|req(?:uisition)?id)=",
    re.I,
)
_NAV_TEXT = {
    "jobs", "careers", "search jobs", "apply", "apply now", "view all jobs", "all jobs",
    "see all jobs", "learn more", "join us", "home", "sign in", "log in", "privacy",
    "terms", "view job", "view jobs", "view details", "read more",
}


def _shape(href: str) -> str:
    """The URL with ids and slugs wildcarded: /en-in/details/200-0836/swe → en-in/details/*/*."""
    parts = urlsplit(href)
    segs = [s for s in parts.path.split("/") if s]
    kept = [
        s if i < 2 and not re.search(r"\d", s) and len(s) <= 20 else "*"
        for i, s in enumerate(segs)
    ]
    return f"{parts.netloc}/{'/'.join(kept)}"


def cluster_links(anchors: Iterable[dict[str, str]], page_url: str) -> list[dict[str, Any]]:
    """The biggest group of anchors that share one URL shape and carry ids — a listing.

    A job board repeats one link shape per posting. This catches the sites whose
    paths the keyword heuristic has never heard of (`/details/<id>/<slug>`), and
    it demands an id-bearing segment so a block of marketing or team links
    ("/teams/software-engineering") is not mistaken for roles.
    """
    groups: dict[str, list[tuple[str, list[str]]]] = {}
    for anchor in anchors:
        href = (anchor.get("href") or "").split("#")[0]
        lines = [ln.strip() for ln in (anchor.get("text") or "").splitlines() if ln.strip()]
        if not href.startswith("http") or not lines:
            continue
        title = " ".join(lines[0].split())
        if not (8 <= len(title) <= 120) or title.lower() in _NAV_TEXT:
            continue
        shape = _shape(href)
        if shape.count("/") < 2:  # a bare host or one-segment path is navigation
            continue
        groups.setdefault(shape, []).append((href, lines))

    best: list[tuple[str, list[str]]] = []
    for members in groups.values():
        unique = {href: lines for href, lines in members}
        with_id = sum(1 for href in unique if re.search(r"\d", urlsplit(href).path))
        if len(unique) >= 4 and with_id >= 0.7 * len(unique) and len(unique) > len(best):
            best = list(unique.items())
    return [
        {
            "title": " ".join(lines[0].split()),
            "url": href,
            "location": ", ".join(lines[1:3]),
            "posted": None,
            "experience": card_experience(lines[1:]),
        }
        for href, lines in best
    ]


def card_experience(lines: list[str]) -> tuple[float, float | None] | None:
    """A job card's own "2 - 5 Years" line. Only short lines: a card's blurb is prose."""
    for line in lines:
        if len(line) <= 40:
            found = discover.parse_experience(line, structured=True)
            if found:
                return found
    return None


def job_links(anchors: Iterable[dict[str, str]], page_url: str) -> list[dict[str, Any]]:
    """Job anchors by href keyword, or by repeated-shape cluster — whichever finds more."""
    anchors = list(anchors)
    by_keyword = _keyword_links(anchors, page_url)
    by_shape = cluster_links(anchors, page_url)
    return by_shape if len(by_shape) > len(by_keyword) else by_keyword


def _keyword_links(anchors: Iterable[dict[str, str]], page_url: str) -> list[dict[str, Any]]:
    """Anchors that look like a specific job: a job-shaped href and a title-shaped text."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in anchors:
        href = (anchor.get("href") or "").split("#")[0]
        lines = [ln.strip() for ln in (anchor.get("text") or "").splitlines() if ln.strip()]
        if not href or not lines:
            continue
        title = " ".join(lines[0].split())
        if not (6 <= len(title) <= 140) or title.lower() in _NAV_TEXT:
            continue
        if not _JOB_HREF.search(href):
            continue
        link = build_url(href, page_url=page_url, url_base=None)
        if not link or link in seen:
            continue
        seen.add(link)
        rows.append(
            {"title": title, "url": link, "location": ", ".join(lines[1:3]), "posted": None,
             "experience": card_experience(lines[1:])}
        )
    return rows


# --------------------------------------------------------------------------
# entry links — a careers page is often a brochure one click away from the list
# --------------------------------------------------------------------------

# Hosts that are job boards in their own right: a link or an iframe pointing at one
# is the listing, whatever its text says.
_ATS_HOSTS = (
    "myworkdayjobs.com", "greenhouse.io", "lever.co", "ashbyhq.com", "darwinbox.in",
    "darwinbox.com", "keka.com", "kekahire.com", "smartrecruiters.com", "icims.com",
    "taleo.net", "successfactors.com", "successfactors.eu", "oraclecloud.com",
    "turbohire.co", "freshteam.com", "zohorecruit.com", "zohorecruit.in", "workable.com",
    "recruitee.com", "eightfold.ai", "jobvite.com", "bamboohr.com", "breezy.hr",
    "mynexthire.com", "phenompeople.com", "avature.net", "skillate.com",
    "pyjamahr.com", "kula.ai",
)
_SOCIAL_HOSTS = (
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com",
    "glassdoor.", "naukri.com", "indeed.", "wa.me", "t.me",
)
_ENTRY_TEXT = re.compile(
    r"(open (roles|positions|jobs|opportunities|requisitions)"
    r"|view (all )?(open |current )?(job )?(jobs|roles|openings|positions|opportunities|vacancies)"
    r"|(current|job) openings|search (all )?(jobs|roles|openings|positions)"
    r"|(browse|see|explore) (all )?(open |current )?(job )?(jobs|roles|openings|positions|opportunities)"
    r"|find (your|a|the right) (job|role)|all jobs|join (us|our team)|we.?re hiring"
    r"|^\s*(careers?|jobs|work with us)\s*$)",
    re.I,
)


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def pick_entry_link(
    anchors: Iterable[dict[str, str]], frame_urls: Iterable[str], page_url: str
) -> str | None:
    """The link (or embedded board) most likely to lead from this page to the job list.

    An iframe on a job-board host wins outright — it *is* the list. Otherwise links
    score on their text ("View open roles"), on pointing at a job-board host, and on
    a jobs-shaped path; social links never qualify, whatever they say ("Join us on
    LinkedIn" is not a listing).
    """
    for url in frame_urls:
        if url.startswith("http") and any(h in _host(url) for h in _ATS_HOSTS):
            return url
    here = discover._url_key(page_url)
    best: tuple[int, str | None] = (0, None)
    for anchor in anchors:
        href = (anchor.get("href") or "").split("#")[0]
        if not href.startswith("http") or discover._url_key(href) == here:
            continue
        host = _host(href)
        if any(s in host for s in _SOCIAL_HOSTS):
            continue
        text = " ".join(((anchor.get("text") or "").splitlines() or [""])[0].split())
        score = 2 if _ENTRY_TEXT.search(text) else 0
        if any(h in host for h in _ATS_HOSTS):
            score += 4  # outranks any wording: a job-board host is the list itself
        if re.search(r"/(jobs?|openings|positions|job-search|search-jobs|opportunities)(/|$|\?)", urlsplit(href).path + "/"):
            score += 1
        if score >= 2 and score > best[0]:
            best = (score, href)
    return best[1]


def site_root(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}/"


def listing_url_for(url: str) -> str:
    """Map a job-board page that is *near* the list (a login, a home, one job) to the list.

    Following links lands on whatever the careers page linked to: Darwinbox's
    candidate login or careers home, a single Workable posting. Each board keeps
    its full list at one predictable address.
    """
    parts = urlsplit(url)
    host, path = parts.netloc.lower(), parts.path
    if host.endswith(("darwinbox.in", "darwinbox.com")) and "allJobs" not in path:
        return f"{parts.scheme}://{parts.netloc}/ms/candidatev2/main/careers/allJobs"
    if host == "apply.workable.com":
        account = path.strip("/").split("/")[0]
        if account:
            return f"https://apply.workable.com/{account}/"
    return url


# Words that nearly every real job title carries. A "list" whose titles mostly lack
# them is something else that repeats: customer case studies ("Hapi Cloud hit an 85%
# utilization rate…"), a nav item ("Application") served as JSON.
_ROLE_WORDS = re.compile(
    r"\b(engineer|engineering|developer|development|manager|management|lead|head|director|"
    r"analyst|scientist|architect|designer|design|specialist|associate|intern|consultant|"
    r"executive|officer|administrator|admin|recruiter|representative|coordinator|technician|"
    r"operator|programmer|sde|swe|sre|devops|qa|tester|researcher|staff|principal|partner|"
    r"advisor|counsel|accountant|writer|editor|strategist|owner|agent|expert|trainee|"
    r"apprentice|fellow|member|chief|vp|president|supervisor|planner|buyer|auditor)s?\b",
    re.I,
)


def looks_like_jobs(rows: list[dict[str, Any]]) -> bool:
    """Most titles must read like job titles, and they cannot all be the same string."""
    if not rows:
        return False
    titles = [r["title"] for r in rows]
    if len(titles) >= 3 and len(set(t.lower() for t in titles)) == 1:
        return False
    hits = sum(1 for t in titles if _ROLE_WORDS.search(t))
    return hits >= max(1, 0.5 * len(titles))


# --------------------------------------------------------------------------
# failure classification
# --------------------------------------------------------------------------

_BLOCK_MARKERS = (
    "captcha", "verify you are human", "are you a robot", "access denied",
    "unusual traffic", "just a moment", "attention required", "request blocked",
    "pardon our interruption",
)
_LOGIN_MARKERS = ("sign in to continue", "log in to continue", "join linkedin", "sign in to view")


def classify_page(status: int | None, text: str) -> str | None:
    """A reason string if this is a wall rather than a careers page. Reported, never bypassed."""
    if status in (401, 403, 429):
        return f"HTTP {status}"
    if status == 202 and not (text or "").strip():
        return "HTTP 202 with an empty page (a bot-protection challenge)"
    lowered = (text or "")[:4000].lower()
    for marker in _BLOCK_MARKERS + _LOGIN_MARKERS:
        if marker in lowered:
            return f"page says '{marker}'"
    return None


_NO_OPENINGS = re.compile(
    r"(there are no|no) (current |open |job |available )*(openings|positions|postings|vacancies|jobs|roles)"
    r"( currently| at the moment| right now| available)?"
    r"|currently (have )?no (open|job|available)|no (open )?(jobs|roles) (found|match)"
    r"|(?<![\d,.])0\s+(open\s+|current\s+)?(jobs|roles|openings|positions)\s+(available|found)",
    re.I,
)


def says_no_openings(text: str) -> bool:
    """The page itself reports an empty list — a real zero, not a failure to read."""
    return bool(_NO_OPENINGS.search(text or ""))


def classify_exception(exc: BaseException) -> str:
    name, message = type(exc).__name__, str(exc)
    if "Timeout" in name:
        return "timeout"
    if "net::ERR_" in message or "NS_ERROR" in message:
        return "navigation"
    return "error"


def short(exc: BaseException) -> str:
    first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    return f"{type(exc).__name__}: {first}"[:200]


# --------------------------------------------------------------------------
# role normalisation, filtering, assembly — pure
# --------------------------------------------------------------------------


def normalize_posted(value: Any, as_of: date | None = None) -> str | None:
    """ISO day from an ISO date or epoch, or from "Posted 3 Days Ago" style text."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 1e11:
        # Epoch *seconds* (Darwinbox). discover._iso_day reads numbers as Lever's
        # milliseconds, which would put every one of these in January 1970.
        value = value * 1000
    iso = discover._iso_day(value)
    if iso or not isinstance(value, str):
        return iso
    now = as_of or date.today()
    lowered = value.lower()
    if "today" in lowered or "just posted" in lowered or "hour" in lowered:
        return now.isoformat()
    if "yesterday" in lowered:
        return (now - timedelta(days=1)).isoformat()
    match = re.search(r"(\d+)\+?\s*(day|week|month)", lowered)
    if match:
        days = int(match.group(1)) * {"day": 1, "week": 7, "month": 30}[match.group(2)]
        return (now - timedelta(days=days)).isoformat()
    return None


def to_role(company: dict[str, Any], strategy: str, row: dict[str, Any]) -> dict[str, Any]:
    location = (row.get("location") or "").strip()
    role = discover._role(
        company,
        "careers_page",
        title=row["title"],
        url=row["url"],
        locations=[location] if location else [],
        posted=normalize_posted(row.get("posted")),
        experience=row.get("experience"),
    )
    role["strategy"] = strategy
    return role


def filter_scraped(roles: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    """`discover.filter_roles`, except a role with no location is trusted to the URL filter.

    A careers page opened with `?location=India` has already narrowed to India;
    a link-only extraction often cannot read the location at all. discover's
    filter would drop every one of those rows, which is the wrong default here.
    """
    common = dict(
        keywords=filters["keywords"],
        exclude_keywords=filters["exclude_keywords"],
        include_remote=filters["include_remote"],
        max_age_days=filters["max_age_days"],
        exclude_seniority=filters.get("exclude_seniority") or (),
        **experience_args(filters),
    )
    located = [r for r in roles if r["locations"]]
    unlocated = [r for r in roles if not r["locations"]]
    return discover.filter_roles(
        located, locations=filters["locations"], **common
    ) + discover.filter_roles(unlocated, locations=(), **common)


_TRACKING_PARAM = re.compile(r"^(utm_\w+|gh_src|src|source|ref|referrer|trk|refid|trackingid)$", re.I)


def link_key(url: str) -> str:
    """A posting's identity, keeping the query and fragment that carry it.

    `discover._url_key` cuts at `?`/`#`, right for an ATS board's clean paths and
    wrong here: PyjamaHR names a posting by `?job_id=`, MyNextHire by a `#…p=` blob,
    so cutting there collapsed a whole board into one row. Only tracking
    parameters are dropped, so a `utm_` variant still matches its original.
    """
    parts = urlsplit((url or "").strip())
    query = urlencode(sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _TRACKING_PARAM.match(k)
    ))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/"), query, parts.fragment)
    ).lower()


def dedupe_scraped(
    roles: list[dict[str, Any]], jobs: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    """Drop roles you already track and collapse repeats — by *link*, not by title.

    `discover.dedupe` also collapses on (company, title), which is right for an ATS
    board and wrong here: Amazon posts hundreds of "Software Development Engineer"
    roles, each its own link in its own city, and a title match would show you one.
    A tracked record only matches by title when it has no URL of its own (a hand-added
    one), since then the title is all there is to match on.
    """
    tracked_urls = {link_key(j["url"]) for j in jobs if j.get("url")}
    tracked_titles = {
        (companies.norm_name(j.get("organisation")), companies.norm_name(j.get("job_title")))
        for j in jobs
        if not j.get("url")
    }
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    already = 0
    for role in roles:
        key = link_key(role["url"])
        title_key = (companies.norm_name(role["company"]), companies.norm_name(role["title"]))
        if key in tracked_urls or title_key in tracked_titles:
            already += 1
        elif key not in seen:
            seen.add(key)
            kept.append(role)
    return kept, already


def merge_scraped(
    store: dict[str, Any], results: list[dict[str, Any]], *, as_of: str
) -> dict[str, Any]:
    """Fold a run into the per-company snapshot. Pure.

    A read that worked (rows, or a page that says it has no openings) replaces
    that company's roles. A failure keeps the previous roles and records the
    problem, so one bad night doesn't blank a company that was readable
    yesterday — the date shows how old they are.
    """
    out = {k: dict(v) for k, v in (store or {}).items()}
    for result in results:
        company, problem = result["company"], result["problem"]
        if problem == "skipped":
            continue
        entry = out.get(company["id"], {"roles": [], "read_on": None})
        entry.update(company_id=company["id"], name=company["name"], problem=f"{problem}: {result['detail']}"[:200] if problem else None)
        keeps = not problem or (problem in KEEP_ROWS and result["rows"])
        if keeps:
            entry["roles"] = [
                {k: v for k, v in to_role(company, result["strategy"], row).items() if k != "description"}
                for row in result["rows"]
            ]
            entry["read_on"] = as_of
        out[company["id"]] = entry
    return out


def load_scraped() -> dict[str, dict[str, Any]]:
    return {c["company_id"]: c for c in jsonstore.read(SCRAPED_FILE, "companies")["companies"]}


def save_scraped(store: dict[str, dict[str, Any]]) -> None:
    ordered = sorted(store.values(), key=lambda c: c.get("name", "").lower())
    jsonstore.write(SCRAPED_FILE, {"companies": ordered})


def assemble(
    results: list[dict[str, Any]],
    filters: dict[str, Any],
    jobs: list[dict[str, Any]],
    previous_urls: set[str],
    sites: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Everything the workbook needs, from the per-company results. No I/O."""
    raw: list[dict[str, Any]] = []
    for result in results:
        company = result["company"]
        raw.extend(to_role(company, result["strategy"], row) for row in result["rows"])

    filtered = filter_scraped(raw, filters)
    fresh, already = dedupe_scraped(filtered, jobs)
    previous = {link_key(u) for u in previous_urls}
    for role in fresh:
        role["is_new"] = link_key(role["url"]) not in previous
    fresh.sort(
        key=lambda r: (TIER_ORDER.get(r.get("tier") or "", 9), r["company"].lower(), r["title"].lower())
    )

    per_company = Counter(r["company_id"] for r in fresh)
    links: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    attention: list[dict[str, Any]] = []
    for result in sorted(
        results,
        key=lambda r: (TIER_ORDER.get(r["company"].get("tier") or "", 9), r["company"]["name"].lower()),
    ):
        company, problem = result["company"], result["problem"]
        if problem == "skipped":
            status = f"skipped - {result['detail']}"
        elif problem:
            status = f"{problem}: {result['detail']}"[:140]
        else:
            status = f"ok - {result['detail']}" if result["detail"] else "ok"
        links.append(
            {
                "company": company["name"],
                "tier": company.get("tier"),
                "url": result["search_url"],
                "found": per_company.get(company["id"], 0),
                "status": status,
                "reviewed": review_label((sites or {}).get(company["id"])),
            }
        )
        if problem:
            entry = {
                "company": company["name"],
                "problem": problem,
                "detail": result["detail"],
                "snapshot": result.get("snapshot") or "",
            }
            attention.append(entry)
            if problem != "skipped":
                failures.append(entry)

    return {
        "roles": fresh,
        "links": links,
        # `failures` is what the terminal prints. `attention` is the workbook's sheet and
        # also lists the skips: a company parked with a reason is still unread, and the
        # one place that names every unread company should not leave any out.
        "failures": failures,
        "attention": attention,
        "totals": {
            "companies": len(results),
            "ok": sum(1 for r in results if not r["problem"]),
            "skipped": sum(1 for r in results if r["problem"] == "skipped"),
            "failed": len(failures),
            "roles_seen": len(raw),
            "after_filters": len(filtered),
            "already_tracked": already,
            "roles": len(fresh),
            "new": sum(1 for r in fresh if r["is_new"]),
        },
    }


def merge_site(
    site: dict[str, Any] | None, company: dict[str, Any], result: dict[str, Any], url_template: str
) -> dict[str, Any]:
    """Fold one run's outcome into the company's saved config."""
    merged = {
        "company_id": company["id"],
        "name": company["name"],
        "careers_url": company.get("careers_url"),
        "strategy": None,
        "search_url": url_template,
        "endpoint": None,
        "field_map": None,
        "url_base": None,
        "selectors": None,
        "ui_steps": [],
        **(site or {}),
    }
    if result["problem"] == "skipped":
        return merged
    keeps_rows = result["problem"] in KEEP_ROWS and bool(result["rows"])
    if result["problem"] and not keeps_rows:
        merged["last_error"] = f"{result['problem']}: {result['detail']}"[:200]
        return merged
    learned = result.get("learned") or {}
    merged.update(learned)
    merged["strategy"] = result["strategy"]
    # A followed entry link is the better address from now on.
    merged["search_url"] = learned.get("search_url") or url_template
    if result["problem"] == "layout_changed":
        # Keep last_count so the warning repeats until someone fixes the config.
        merged["last_error"] = f"layout_changed: {result['detail']}"[:200]
        return merged
    merged["verified_on"] = today()
    merged["last_count"] = len(result["rows"])
    merged["last_error"] = (
        f"{result['problem']}: {result['detail']}"[:200] if result["problem"] else None
    )
    return merged


# --------------------------------------------------------------------------
# manual review + "needs your help" — pure bookkeeping on career-sites.json
# --------------------------------------------------------------------------
#
# Every company is verified by hand, a couple a day: `--review` opens the site in a
# visible browser on the filtered page next to what the scraper read, and the verdict
# is recorded per company in `reviews[]` (a history, latest wins). Separately, a site
# that would cost more effort than it is worth goes on the "needs your help" list
# (`help`) with the reason, instead of being fought with indefinitely.

REVIEW_VERDICTS = ("verified", "needs_fix")


def _site_for(site: dict[str, Any] | None, company: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_id": company["id"],
        "name": company["name"],
        "careers_url": company.get("careers_url"),
        **(site or {}),
    }


def latest_review(site: dict[str, Any] | None) -> dict[str, Any] | None:
    reviews = (site or {}).get("reviews") or []
    return reviews[-1] if reviews else None


def review_label(site: dict[str, Any] | None) -> str:
    last = latest_review(site)
    return f"{last['verdict']} {last['date']}" if last else ""


def record_review(
    site: dict[str, Any] | None, company: dict[str, Any], verdict: str, note: str = "",
    on: str | None = None,
) -> dict[str, Any]:
    if verdict not in REVIEW_VERDICTS:
        raise ValueError(f"verdict must be one of {', '.join(REVIEW_VERDICTS)}")
    merged = _site_for(site, company)
    merged["reviews"] = [
        *(merged.get("reviews") or []),
        {"date": on or today(), "verdict": verdict, "note": note or ""},
    ]
    return merged


def review_queue(
    pool: list[dict[str, Any]], sites: dict[str, dict[str, Any]], limit: int = 2
) -> list[dict[str, Any]]:
    """Never-reviewed companies, readable ones first, then by tier — the next to look at."""
    pending = [c for c in pool if not latest_review(sites.get(c["id"]))]
    pending.sort(
        key=lambda c: (
            bool(skip_reason(c, sites.get(c["id"]))),
            TIER_ORDER.get(c.get("tier") or "", 9),
            c["name"].lower(),
        )
    )
    return pending[:limit]


def flag_help(
    site: dict[str, Any] | None, company: dict[str, Any], why: str, on: str | None = None
) -> dict[str, Any]:
    if not (why or "").strip():
        raise ValueError("say why the site needs help — a bare flag is a note to nobody")
    merged = _site_for(site, company)
    merged["help"] = {"why": why.strip(), "since": on or today()}
    return merged


def help_rows(pool: list[dict[str, Any]], sites: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for company in pool:
        flag = (sites.get(company["id"]) or {}).get("help")
        if flag:
            rows.append(
                {
                    "company": company["name"],
                    "tier": company.get("tier"),
                    "url": company.get("careers_url"),
                    "why": flag.get("why", ""),
                    "since": flag.get("since", ""),
                }
            )
    rows.sort(key=lambda r: (TIER_ORDER.get(r["tier"] or "", 9), r["company"].lower()))
    return rows


def selection_slug(tiers: list[str], statuses: list[str], names: list[str]) -> str:
    """Workbook suffix for a partial run, so it never overwrites the full daily export."""
    parts = sorted(tiers) + sorted(statuses) + [_slug(n) for n in names]
    return "-".join(parts)[:60].strip("-")


# --------------------------------------------------------------------------
# Playwright layer — everything below needs a browser
# --------------------------------------------------------------------------

_ASSET = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|woff2?|ttf|otf|mp4|webm)(\?|$)", re.I)
_MORE_BUTTON = re.compile(r"^\s*(load|show|view|see)\s+more", re.I)
# For a "Load More Jobs" that is a styled div rather than a button (Darwinbox):
# the whole text must be the phrase, so a "Show more" inside a description is not it.
_MORE_TEXT = re.compile(r"^\s*(load|show|view|see)\s+more(\s+\w+){0,2}\s*$", re.I)

_LINKS_JS = (
    "els => els.map(e => ({href: e.href, "
    "text: (e.innerText || e.getAttribute('aria-label') || '').trim()}))"
)
_DOM_JS = """(els, sel) => els.map(el => {
  const find = s => !s ? null : (el.matches(s) ? el : el.querySelector(s));
  const text = s => { const n = find(s); return n ? (n.innerText || '').trim() : ''; };
  const link = sel.link ? find(sel.link) : (el.closest('a') || el.querySelector('a[href]'));
  return {title: text(sel.title), href: link ? link.href : '',
          location: text(sel.location), posted: text(sel.posted)};
})"""


async def _block_assets(route) -> None:
    await route.abort()


class Capture:
    """JSON responses, console errors and the main document's status for one page."""

    def __init__(self) -> None:
        self.json: list[tuple[str, Any]] = []
        self.console: list[str] = []
        self.status: int | None = None
        self._tasks: set[asyncio.Future] = set()

    def attach(self, page) -> None:
        page.on("response", self._on_response)
        page.on(
            "console",
            lambda m: self.console.append(f"{m.type}: {m.text}"[:300])
            if m.type in ("error", "warning")
            else None,
        )

    def _on_response(self, response) -> None:
        # GraphQL endpoints are often served as text/plain or text/javascript.
        is_json = "json" in response.headers.get("content-type", "") or "graphql" in response.url.lower()
        if response.status != 200 or not is_json:
            return
        task = asyncio.ensure_future(self._grab(response))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _grab(self, response) -> None:
        try:
            body = await response.body()
            if len(body) <= 3_000_000:
                self.json.append((response.url, json.loads(body)))
        except Exception:  # a body that vanished on navigation is not an error
            pass

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


async def _settle(page, ms: int) -> None:
    from playwright.async_api import TimeoutError as PWTimeout

    try:
        await page.wait_for_load_state("networkidle", timeout=ms)
    except PWTimeout:
        pass


async def _ui_steps(page, steps: list[dict[str, Any]], filters: dict[str, Any]) -> None:
    """Per-site hand-written steps for filters that cannot be set in the URL."""
    values = {"{q}": filters["primary_query"], "{location}": (filters["locations"] or [""])[0]}

    def sub(text: str | None) -> str:
        out = text or ""
        for key, value in values.items():
            out = out.replace(key, value)
        return out

    for step in steps:
        action, selector = step.get("action"), step.get("selector")
        if action == "fill":
            await page.locator(selector).first.fill(sub(step.get("value")), timeout=8000)
        elif action == "click":
            await page.locator(selector).first.click(timeout=8000)
        elif action == "press":
            await page.locator(selector).first.press(step.get("value", "Enter"), timeout=8000)
        elif action == "select":
            await page.locator(selector).first.select_option(sub(step.get("value")), timeout=8000)
        elif action == "wait":
            await page.wait_for_timeout(int(step.get("value", 1000)))
        await _settle(page, 4000)


async def _expand(page, max_pages: int | None = None) -> None:
    """Scroll for lazy lists, and press "Load more" while there is one."""
    for _ in range(SCROLLS):
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(600)
    for _ in range(int(max_pages or MAX_PAGES)):
        button = None
        for candidate in (
            page.get_by_role("button", name=_MORE_BUTTON).first,
            page.get_by_role("link", name=_MORE_BUTTON).first,
            page.get_by_text(_MORE_TEXT).last,
        ):
            try:
                if await candidate.count() and await candidate.is_visible():
                    button = candidate
                    break
            except Exception:
                continue
        if button is None:
            break
        try:
            await button.click(timeout=3000)
            await page.wait_for_timeout(900)
        except Exception:
            break


# Exact-name matches only: a "Next steps" link or a "Next-gen" footer must not be clicked.
_NEXT_SELECTORS = (
    '[data-uxi-element-id="next"]',
    'button[aria-label="next" i]',
    'button[aria-label*="next page" i]',
    'a[rel="next"]',
    'a[aria-label*="next page" i]',
)
_NEXT_NAME = re.compile(r"^\s*(next|next page|›|»)\s*$", re.I)


async def _next_page(page, selector: str | None) -> bool:
    """Click the site's "next page" control if there is a live one."""
    if selector:
        candidates = [page.locator(selector).first]
    else:
        candidates = [page.locator(s).first for s in _NEXT_SELECTORS] + [
            page.get_by_role("button", name=_NEXT_NAME).first,
            page.get_by_role("link", name=_NEXT_NAME).first,
        ]
    for locator in candidates:
        try:
            if await locator.count() == 0 or not await locator.is_visible():
                continue
            if not await locator.is_enabled() or await locator.get_attribute("aria-disabled") == "true":
                continue
            await locator.click(timeout=4000)
            return True
        except Exception:
            continue
    return False


async def _paginate(
    page, capture: Capture, cfg: dict[str, Any], url_base: str | None,
    strategy: str, rows: list[dict[str, Any]], learned: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Walk "next page" until it runs out, stops adding roles, or hits max_pages.

    xhr accumulates across pages for free — every click fires another response
    from the same endpoint. links only sees the current page, so each page is
    read and merged. `result["rows"]` is kept current after every page, so a
    site that runs out of time still hands back what it had read.
    """
    def from_endpoint() -> int:
        # Count the jobs endpoint's own responses: an analytics ping landing first
        # must not be mistaken for the next page of results.
        return sum(1 for url, _ in capture.json if learned.get("endpoint", "\0") in url)

    for turn in range(int(cfg.get("max_pages") or MAX_PAGES) - 1):
        seen_before = from_endpoint()
        clicked = await _next_page(page, cfg.get("next"))
        if not clicked and turn == 0:
            # Under load the pager can render a moment after the first results do.
            await page.wait_for_timeout(2000)
            clicked = await _next_page(page, cfg.get("next"))
        if not clicked:
            break
        # networkidle can resolve before the click's own request has even started
        # (the page fires it a tick later), so wait for the response itself.
        for _ in range(20):
            await page.wait_for_timeout(300)
            await capture.drain()
            if strategy != "xhr" or from_endpoint() > seen_before:
                break
        await _settle(page, 3000)
        await capture.drain()
        if strategy == "xhr":
            found = find_source(
                capture.json, learned["endpoint"], learned["field_map"],
                page_url=page.url, url_base=url_base,
            )
            grown = found[2] if found else rows
        else:
            anchors = await page.eval_on_selector_all("a[href]", _LINKS_JS)
            grown = merge_rows(rows, job_links(anchors, page.url))
        added = len(grown) - len(rows)
        rows = grown
        result["rows"] = rows
        if added <= 0:
            break
    return rows


async def _extract_dom(
    page, selectors: dict[str, Any], url_base: str | None
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _ in range(int(selectors.get("max_pages") or MAX_PAGES)):
        items = await page.eval_on_selector_all(selectors["item"], _DOM_JS, selectors)
        before = len(seen)
        for item in items:
            link = build_url(item.get("href"), page_url=page.url, url_base=url_base)
            title = " ".join((item.get("title") or "").split())
            if not title or not link or link in seen:
                continue
            seen.add(link)
            rows.append(
                {"title": title, "url": link, "location": item.get("location", ""),
                 "posted": item.get("posted") or None}
            )
        nxt = selectors.get("next")
        if not nxt:
            break
        button = page.locator(nxt).first
        if await button.count() == 0 or not await button.is_enabled():
            break
        await button.click(timeout=5000)
        await _settle(page, 4000)
        if len(seen) == before and before:  # a page that adds nothing ends the walk
            break
    return rows


async def _run_strategy(
    strategy: str, page, capture: Capture, cfg: dict[str, Any], url_base: str | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if strategy == "xhr":
        found = find_source(
            capture.json, cfg.get("endpoint"), cfg.get("field_map"),
            page_url=page.url, url_base=url_base,
        )
        if not found:
            return [], {}
        endpoint, field_map, rows = found
        return rows, {"endpoint": endpoint, "field_map": field_map}
    if strategy == "dom":
        return await _extract_dom(page, cfg["selectors"], url_base), {}
    return job_links(await _all_anchors(page), page.url), {}


async def _all_anchors(page) -> list[dict[str, str]]:
    """Anchors from the page and every frame — an embedded job board lives in an iframe."""
    anchors: list[dict[str, str]] = []
    for frame in page.frames:
        try:
            anchors += await frame.eval_on_selector_all("a[href]", _LINKS_JS)
        except Exception:  # a cross-origin frame mid-navigation, a detached one
            continue
    return anchors


async def _open(
    page, capture: Capture, url: str, timeout_ms: int, max_pages: int | None = None
) -> str:
    """Navigate, let the list load, and return the body text."""
    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    capture.status = response.status if response else None
    await _settle(page, 8000)
    await _expand(page, max_pages)
    await _settle(page, 3000)
    await capture.drain()
    try:
        return await page.inner_text("body", timeout=5000)
    except Exception:
        return ""


async def _extract(page, capture: Capture, cfg: dict[str, Any], url_base: str | None):
    """Run the strategies in their fixed order; the first with rows wins."""
    # Fixed preference, not "whatever worked last time": a saved weak strategy that
    # returns *something* (links finding one page of cards) would otherwise shadow a
    # better one for good. The saved endpoint/field_map still make xhr a straight
    # replay, and a site that moved its API falls through to links rather than failing.
    # Selectors are hand-written, so a site that has them goes first.
    order = ["dom", "xhr", "links"] if cfg.get("selectors") else ["xhr", "links"]
    base = default_url_base(page.url) or url_base
    for strategy in order:
        rows, learned = await _run_strategy(strategy, page, capture, cfg, base)
        # Hand-written selectors are trusted; a guessed list has to look like jobs.
        if rows and (strategy == "dom" or looks_like_jobs(rows)):
            return rows, strategy, learned
    return [], None, {}


MAX_HOPS = 3  # root -> careers page -> listing, at most


async def _work(
    page, capture: Capture, company, cfg, url, url_base, filters, result, timeout_ms
) -> None:
    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    capture.status = response.status if response else None
    await _settle(page, 8000)
    await _ui_steps(page, cfg.get("ui_steps") or [], filters)
    await _expand(page, cfg.get("max_pages"))
    await _settle(page, 3000)
    await capture.drain()

    try:
        body = await page.inner_text("body", timeout=5000)
    except Exception:
        body = ""
    wall = classify_page(capture.status, body)
    if wall:
        result.update(problem="blocked", detail=wall)
        return

    rows, used, learned = await _extract(page, capture, cfg, url_base)

    # Nothing here: follow the page's own way to its list ("View open roles", an
    # embedded board) — or, from a 404, start again at the site's front door. A hop
    # that works is saved as search_url, so the next run goes straight there.
    hops = 0
    while not rows and hops < MAX_HOPS and not says_no_openings(body) and not cfg.get("no_hop"):
        target = pick_entry_link(
            await _all_anchors(page), [f.url for f in page.frames[1:]], page.url
        )
        from_root = False
        if not target and capture.status == 404 and hops == 0:
            target, from_root = site_root(page.url), True
        if not target:
            break
        hops += 1
        target = listing_url_for(target)
        body = await _open(page, capture, target, timeout_ms, cfg.get("max_pages"))
        wall = classify_page(capture.status, body)
        if wall:
            result.update(problem="blocked", detail=f"{wall} (after following {target})")
            return
        if from_root:
            continue  # a home page is only a way to the careers link, never the list
        rows, used, learned = await _extract(page, capture, cfg, url_base)
        if rows:
            learned = {**learned, "search_url": page.url}
            result["search_url"] = page.url

    if not rows and says_no_openings(body):
        result.update(detail="the page says there are no openings")
        return
    if not rows:
        followed = f", after following {hops} link(s) to {page.url}" if hops else ""
        result.update(
            problem="zero_extracted",
            detail=f"page loaded (HTTP {capture.status}) but no roles could be read{followed}",
        )
        return
    result.update(strategy=used, rows=rows, learned=learned)
    url_base = default_url_base(page.url) or url_base
    if used in ("xhr", "links"):
        rows = await _paginate(page, capture, cfg, url_base, used, rows, learned, result)
    result["rows"] = rows

    prior = cfg.get("last_count")
    if prior and prior >= 5 and len(rows) < prior * 0.3:
        result.update(
            problem="layout_changed", detail=f"{len(rows)} roles now against {prior} last time"
        )
        return
    if used == "xhr":
        total = source_total(capture.json, learned["endpoint"], learned["field_map"])
        if total and len(rows) < total * PARTIAL_BELOW:
            result.update(
                problem="partial",
                detail=(
                    f"read {len(rows)} of {total} roles - put the location in search_url "
                    f"or raise max_pages"
                ),
            )


async def write_snapshot(page, capture: Capture, directory: Path, meta: dict[str, Any]) -> Path:
    """What a person (or I) needs to diagnose a failure — text first, picture second."""
    directory.mkdir(parents=True, exist_ok=True)
    try:
        aria = await page.locator("body").aria_snapshot(timeout=5000)
        lines = aria.splitlines()
        text = "\n".join(lines[:200]) + (f"\n... {len(lines) - 200} more lines" if len(lines) > 200 else "")
    except Exception as exc:
        text = f"(aria snapshot unavailable: {short(exc)})"
    (directory / "aria.txt").write_text(text, encoding="utf-8")
    try:
        await page.screenshot(path=str(directory / "page.png"), timeout=8000)
    except Exception:
        pass
    network = [
        f"{len(json.dumps(payload)):>8}B  {url}  keys={sorted(payload)[:8] if isinstance(payload, dict) else 'list'}"
        for url, payload in capture.json
    ]
    (directory / "network.txt").write_text("\n".join(network) or "(no JSON responses)", encoding="utf-8")
    (directory / "console.txt").write_text("\n".join(capture.console) or "(none)", encoding="utf-8")
    try:
        final_url = page.url
    except Exception:
        final_url = None
    (directory / "meta.json").write_text(
        json.dumps({**meta, "final_url": final_url, "http_status": capture.status}, indent=2),
        encoding="utf-8",
    )
    return directory


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "company"


async def scrape_site(
    browser, company, site, filters, *, force_detect: bool, timeout_s: float, user_agent: str,
    hold=None,
) -> dict[str, Any]:
    """One company: open, filter, extract. Never raises — failures come back as data.

    `hold(result, page)` runs before the page is closed; review mode uses it to
    leave the visible browser on the filtered page until the person closes it.
    """
    started = time.monotonic()
    result: dict[str, Any] = {
        "company": company, "strategy": None, "rows": [], "learned": {},
        "search_url": company.get("careers_url"), "problem": None, "detail": "",
        "snapshot": None, "template": None,
    }
    reason = skip_reason(company, site)
    if reason:
        result.update(problem="skipped", detail=reason)
        if hold:
            # A parked site is still reviewed by eye: open it, read nothing from it.
            context = await browser.new_context(viewport={"width": 1366, "height": 900}, locale="en-IN")
            page = await context.new_page()
            try:
                await page.goto(company["careers_url"], wait_until="domcontentloaded", timeout=45000)
            except Exception as exc:
                result["detail"] += f" (could not open: {short(exc)})"
            await hold(result, page)
            await context.close()
        return result

    cfg = dict(site or {})
    if force_detect:
        # Re-detect the extraction, but keep what a person wrote: search_url, selectors, steps.
        for key in ("strategy", "endpoint", "field_map", "last_count"):
            cfg.pop(key, None)
    template = cfg.get("search_url") or keyword_template(company["careers_url"])
    # A site with thousands of roles needs a server-side keyword to be readable at all;
    # "query" in its config overrides the global primary_query for that site only.
    url = fill_url(template, cfg.get("query", filters["primary_query"]))
    url_base = cfg.get("url_base") or default_url_base(url) or default_url_base(company["careers_url"])
    result.update(search_url=url, template=template)
    timeout_s = float(cfg.get("timeout") or timeout_s)  # a long list can be given longer

    context = await browser.new_context(
        viewport={"width": 1366, "height": 900}, locale="en-IN", user_agent=user_agent
    )
    await context.route(_ASSET, _block_assets)
    page = await context.new_page()
    capture = Capture()
    capture.attach(page)
    try:
        await asyncio.wait_for(
            _work(page, capture, company, cfg, url, url_base, filters, result, int(timeout_s * 1000)),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        have = len(result["rows"])
        result.update(
            problem="timeout",
            detail=(
                f"read {have} roles, then hit the {timeout_s:.0f}s limit - raise it or lower max_pages"
                if have else f"no result within {timeout_s:.0f}s"
            ),
        )
    except Exception as exc:
        result.update(problem=classify_exception(exc), detail=short(exc))

    if result["problem"] and result["problem"] != "skipped":
        directory = snapshot_root() / today() / _slug(company["name"])
        meta = {
            "company": company["name"], "problem": result["problem"], "detail": result["detail"],
            "url": url, "seconds": round(time.monotonic() - started, 1),
        }
        try:
            result["snapshot"] = str(await write_snapshot(page, capture, directory, meta))
        except Exception as exc:  # a snapshot that cannot be written must not hide the failure
            result["detail"] += f" (snapshot failed: {short(exc)})"
    if hold:
        await hold(result, page)
    await context.close()
    return result


async def crawl(
    selected: list[dict[str, Any]],
    sites: dict[str, dict[str, Any]],
    filters: dict[str, Any],
    *,
    workers: int,
    timeout_s: float,
    headed: bool,
    force_detect: bool,
    slow_mo: int = 0,
    hold=None,
) -> list[dict[str, Any]]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed, slow_mo=slow_mo)
        # The default headless UA announces "HeadlessChrome", which many sites refuse
        # on sight. Use the real browser version, without the Headless marker.
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{browser.version} Safari/537.36"
        )
        semaphore = asyncio.Semaphore(workers)

        async def one(company: dict[str, Any]) -> dict[str, Any]:
            async with semaphore:
                return await scrape_site(
                    browser, company, sites.get(company["id"]), filters,
                    force_detect=force_detect, timeout_s=timeout_s, user_agent=user_agent,
                    hold=hold,
                )

        try:
            return await asyncio.gather(*(one(c) for c in selected))
        finally:
            await browser.close()


# --------------------------------------------------------------------------
# selection + CLI
# --------------------------------------------------------------------------


def select(
    board: list[dict[str, Any]],
    *,
    tiers: list[str],
    statuses: list[str],
    names: list[str],
) -> list[dict[str, Any]]:
    """Companies with no JSON board and a careers link, narrowed by the flags."""
    pool = [c for c in board if c["ats_provider"] == "none" and c.get("careers_url")]
    if names:
        return [c for c in pool if any(companies.matches(c, n) for n in names)]
    pool = [c for c in pool if c["status"] != "not_interested"]
    if tiers or statuses:
        pool = [c for c in pool if c["tier"] in tiers or c["status"] in statuses]
    return pool


def _csv(value: str | None) -> list[str] | None:
    return [p.strip() for p in value.split(",") if p.strip()] if value else None


def _one(board: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    hits = [c for c in board if c["ats_provider"] == "none" and companies.matches(c, name)]
    if len(hits) != 1:
        print(f"'{name}' matched {len(hits)} scraper companies; use the exact board name")
        return None
    return hits[0]


def _print_reviews(pool: list[dict[str, Any]], sites: dict[str, dict[str, Any]]) -> None:
    reviewed = [(c, latest_review(sites.get(c["id"]))) for c in pool]
    reviewed = [(c, r) for c, r in reviewed if r]
    print(f"reviewed {len(reviewed)} of {len(pool)}")
    for company, last in sorted(reviewed, key=lambda cr: (cr[1]["date"], cr[0]["name"])):
        note = f" - {last['note']}" if last["note"] else ""
        print(f"  {last['date']}  {last['verdict']:<9}  {company['name']}{note}")
    to_fix = [c["name"] for c, r in reviewed if r["verdict"] == "needs_fix"]
    if to_fix:
        print("needs a fix, then a re-review: " + ", ".join(to_fix))
    upcoming = review_queue(pool, sites)
    if upcoming:
        print("next to review: " + ", ".join(c["name"] for c in upcoming))


def _print_help(pool: list[dict[str, Any]], sites: dict[str, dict[str, Any]]) -> None:
    rows = help_rows(pool, sites)
    print(f"{len(rows)} companies need your help")
    for row in rows:
        print(f"  {row['company']} ({row['tier']}, since {row['since']}): {row['why']}\n    {row['url']}")


def _admin(args, board: list[dict[str, Any]], pool: list[dict[str, Any]]) -> int | None:
    """The bookkeeping commands. None means "not one of these — go and scrape"."""
    if not (args.mark_reviewed or args.reviews or args.flag_help or args.unflag_help or args.needs_help):
        return None
    sites = load_sites()
    if args.mark_reviewed:
        company = _one(board, args.mark_reviewed)
        if not company:
            return 2
        if not args.verdict:
            print("--mark-reviewed needs --verdict verified|needs_fix")
            return 2
        sites[company["id"]] = record_review(sites.get(company["id"]), company, args.verdict, args.note)
        print(f"recorded {company['name']}: {args.verdict}" + (f" - {args.note}" if args.note else ""))
    if args.flag_help:
        company = _one(board, args.flag_help)
        if not company:
            return 2
        try:
            sites[company["id"]] = flag_help(sites.get(company["id"]), company, args.note)
        except ValueError as exc:
            print(f"{exc} (pass --note)")
            return 2
        print(f"{company['name']} is on the needs-your-help list")
    if args.unflag_help:
        company = _one(board, args.unflag_help)
        if not company:
            return 2
        (sites.get(company["id"]) or {}).pop("help", None)
        print(f"{company['name']} is off the needs-your-help list")
    if args.mark_reviewed or args.flag_help or args.unflag_help:
        save_sites(sites)
    if args.reviews:
        _print_reviews(pool, sites)
    if args.needs_help:
        _print_help(pool, sites)
    return 0


def _review_hold(filters: dict[str, Any]):
    """Print what the scraper read, then keep the visible browser open until it is closed."""

    async def hold(result: dict[str, Any], page) -> None:
        company = result["company"]
        roles = [to_role(company, result["strategy"] or "-", row) for row in result["rows"]]
        matched = filter_scraped(roles, filters)
        print(f"REVIEW {company['name']}")
        print(f"  filtered page: {result['search_url']}")
        if result["problem"]:
            print(f"  problem: {result['problem']} - {result['detail']}")
        print(f"  read {len(roles)} roles via {result['strategy'] or 'nothing'}; {len(matched)} match your filters")
        for role in matched[:15]:
            print(f"    {role['title'][:70]} | {role['location'][:40]}")
        print(
            "  Compare with the open browser window, then close it. Record the verdict with\n"
            f"  --mark-reviewed \"{company['name']}\" --verdict verified|needs_fix --note \"...\"",
            flush=True,
        )
        try:
            # Back to the first filtered page: paging may have left it somewhere else.
            if result["problem"] != "skipped" and page.url != result["search_url"]:
                await page.goto(result["search_url"], wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:  # the whole window was closed — that is the signal too
            pass

    return hold


def main(argv: list[str] | None = None) -> int:
    # Scraped titles carry characters a Windows console code page cannot print.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Scrape open roles from careers pages into Excel.")
    parser.add_argument("--tier", help="comma list: faang,tier1,tier2,growth,early")
    parser.add_argument("--status", help="also include companies with these statuses, e.g. target")
    parser.add_argument("--only", help="comma list of company names (overrides tier/status)")
    parser.add_argument("--probe", action="store_true", help="ignore saved config and re-detect")
    parser.add_argument("--keywords", help="override the stored keywords for this run")
    parser.add_argument("--locations", help="override the stored locations for this run")
    parser.add_argument("--remote", action="store_true", help="include remote roles")
    parser.add_argument("--max-age-days", type=int)
    parser.add_argument("--experience", help='years wanted for this run, e.g. "0-3"; "any" turns it off')
    parser.add_argument("--out", help="workbook path (default exports/open-roles-<date>.xlsx)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=float, default=SITE_TIMEOUT_S)
    parser.add_argument("--headed", action="store_true", help="show the browser (debugging)")
    review = parser.add_argument_group("manual review and the help list (no scraping run)")
    review.add_argument("--review", metavar="NAME",
                        help="open one company in a visible browser and hold it until you close it")
    review.add_argument("--mark-reviewed", metavar="NAME", help="record your verdict on a company")
    review.add_argument("--verdict", choices=REVIEW_VERDICTS)
    review.add_argument("--note", default="", help="what you saw, for --mark-reviewed / --flag-help")
    review.add_argument("--reviews", action="store_true", help="list reviewed companies and what is next")
    review.add_argument("--flag-help", metavar="NAME", help="put a company on the needs-your-help list")
    review.add_argument("--unflag-help", metavar="NAME", help="take a company off that list")
    review.add_argument("--needs-help", action="store_true", help="print the needs-your-help list")
    args = parser.parse_args(argv)

    board = companies.load()[companies.KEY]
    pool = select(board, tiers=[], statuses=[], names=[])
    admin = _admin(args, board, pool)
    if admin is not None:
        return admin

    filters = load_filters(
        {
            "keywords": _csv(args.keywords),
            "locations": _csv(args.locations),
            "include_remote": True if args.remote else None,
            "max_age_days": args.max_age_days,
            "experience": args.experience if args.experience not in (None, "any") else None,
        }
    )
    if args.experience == "any":
        filters["experience"] = None
    tiers, statuses = _csv(args.tier) or [], _csv(args.status) or []
    names = [args.review] if args.review else _csv(args.only) or []
    selected = select(board, tiers=tiers, statuses=statuses, names=names)
    if not selected:
        print("no companies selected (need ats_provider none, a careers_url, and a match for the flags)")
        return 2
    if args.review and len(selected) != 1:
        print(f"--review takes one company; '{args.review}' matched {len(selected)}")
        return 2

    hold = _review_hold(filters) if args.review else None
    try:
        sites = load_sites()
        results = asyncio.run(
            crawl(
                selected, sites, filters, workers=max(1, args.workers),
                timeout_s=max(args.timeout, 120) if args.review else args.timeout,
                headed=args.headed or bool(args.review), force_detect=args.probe,
                slow_mo=250 if args.review else 0, hold=hold,
            )
        )
    except ImportError:
        print("playwright is not installed: .venv/Scripts/python.exe -m pip install playwright")
        return 2
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            print("chromium is not installed: .venv/Scripts/python.exe -m playwright install chromium")
            return 2
        raise

    for result in results:
        company = result["company"]
        sites[company["id"]] = merge_site(
            sites.get(company["id"]), company, result, result["template"] or company["careers_url"]
        )
    save_sites(sites)
    if not args.review:
        save_scraped(merge_scraped(load_scraped(), results, as_of=today()))
    companies.record_discovery_many(
        {
            r["company"]["id"]: (
                len(r["rows"])
                if not r["problem"] or (r["problem"] in KEEP_ROWS and r["rows"])
                else None,
                f"{r['problem']}: {r['detail']}"[:200] if r["problem"] else None,
            )
            for r in results
            if r["problem"] != "skipped"
        }
    )

    if args.review:
        return 0  # the verdict comes from the person, via --mark-reviewed

    suffix = selection_slug(tiers, statuses, names)
    out = (
        Path(args.out) if args.out
        else export_dir() / f"open-roles-{today()}{'-' + suffix if suffix else ''}.xlsx"
    )
    previous = out if out.exists() else roles_xlsx.latest_before(out.parent, out)
    built = assemble(
        results, filters, storage.list_jobs(), roles_xlsx.read_previous_urls(previous), sites
    )
    totals = built["totals"]
    roles_xlsx.write(
        out, built["roles"], built["links"], built["attention"],
        [
            ("Run date", today()),
            ("Companies", totals["companies"]),
            ("Read OK", totals["ok"]),
            ("Skipped", totals["skipped"]),
            ("Need attention", totals["failed"]),
            ("Roles seen", totals["roles_seen"]),
            ("After filters", totals["after_filters"]),
            ("Already tracked", totals["already_tracked"]),
            ("Roles listed", totals["roles"]),
            ("New since last run", totals["new"]),
            ("Keywords", ", ".join(filters["keywords"])),
            ("Locations", ", ".join(filters["locations"])),
            ("Excluded words", ", ".join(filters["exclude_keywords"])),
            ("Remote included", "yes" if filters["include_remote"] else "no"),
            ("Max age (days)", filters["max_age_days"] or "any"),
            ("Experience (years)", _experience_label(filters.get("experience"))),
            ("Levels excluded", ", ".join(filters.get("exclude_seniority") or []) or "none"),
            ("Reviewed by hand", f"{sum(1 for c in pool if latest_review(sites.get(c['id'])))} of {len(pool)}"),
        ],
        help_rows(pool, sites),
    )

    print(
        f"{totals['ok']} ok | {totals['skipped']} skipped | {totals['failed']} need attention | "
        f"{totals['roles']} roles ({totals['new']} new) -> {out}"
    )
    for failure in built["failures"]:
        print(f"FAIL {failure['company']} | {failure['problem']} | {failure['detail']} | {failure['snapshot']}")
    return 1 if built["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
