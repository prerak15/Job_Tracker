"""Job applications domain — data/jobs.json.

Single source of truth for application records. Both the REST API and the AI
tools go through here, so there is exactly one place that knows the schema.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, parse_date, pct, read, today, write

FILE = "jobs.json"
KEY = "jobs"
_lock = lock_for(FILE)

STATUSES = [
    "saved",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "ghosted",
    "withdrawn",
]

COMPANY_TYPES = [
    "startup",
    "product",
    "service",
    "mnc",
    "agency",
    "nonprofit",
    "other",
]

CONTACT_ROLES = ["recruiter", "hr", "hiring_manager", "referral", "employee", "other"]

ROUND_RESULTS = ["pending", "waiting", "cleared", "rejected"]

SOURCES = ["linkedin", "careers_page", "referral", "naukri", "job_board", "other"]

# Statuses where the ball is still in play and a follow-up makes sense.
ACTIVE_STATUSES = {"applied", "interviewing"}

# Statuses that prove the company responded in some form.
RESPONDED_STATUSES = {"interviewing", "offer", "rejected"}

_DEFAULTS: dict[str, Any] = {
    "job_title": "",
    "organisation": "",
    "status": "saved",
    "date_created": None,
    "date_job_posted": None,
    "latest_update_date": None,
    "latest_update": "",
    "follow_ups_sent": [],
    "rounds": [],
    "contacts": [],
    "referred_by": None,
    "company_type": None,
    "industry": None,
    "org_summary": None,
    "source": None,
    # Free-text detail behind `source`: the specific place, person, or post.
    "found_via": None,
    "location": None,
    "salary_range": None,
    "job_description": "",
    "resume_id": None,
    "notes": "",
    "url": None,
}


def _normalize(job: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(job, _DEFAULTS)
    if not out["date_created"]:
        out["date_created"] = today()
    if not out["latest_update_date"]:
        out["latest_update_date"] = out["date_created"]
    for idx, rnd in enumerate(out["rounds"], start=1):
        rnd.setdefault("round", idx)
        rnd.setdefault("name", "")
        rnd.setdefault("date", None)
        rnd.setdefault("result", "pending")
        rnd.setdefault("feedback", "")
    for contact in out["contacts"]:
        contact.setdefault("name", "")
        contact.setdefault("role", "other")
        contact.setdefault("email", None)
        contact.setdefault("linkedin", None)
        contact.setdefault("phone", None)
        contact.setdefault("is_referral", False)
        contact.setdefault("notes", "")
    for follow_up in out["follow_ups_sent"]:
        follow_up.setdefault("date", out["date_created"])
        follow_up.setdefault("note", "")
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = [_normalize(job) for job in data[KEY]]
    return data


def save(data: dict[str, Any]) -> None:
    write(FILE, data)


# --------------------------------------------------------------------------
# queries
# --------------------------------------------------------------------------


def list_jobs() -> list[dict[str, Any]]:
    return load()[KEY]


def get_job(job_id: str) -> dict[str, Any] | None:
    return next((j for j in load()[KEY] if j["id"] == job_id), None)


def find_jobs(query: str) -> list[dict[str, Any]]:
    """Loose search over organisation and title — how the AI locates a record."""
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        job
        for job in load()[KEY]
        if needle in job["organisation"].lower() or needle in job["job_title"].lower()
    ]


# --------------------------------------------------------------------------
# mutations
# --------------------------------------------------------------------------


def create_job(payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        job = _normalize({**payload, "id": new_id()})
        if not job["latest_update"]:
            job["latest_update"] = "Record created"
        data[KEY].append(job)
        save(data)
        return job


def update_job(job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, job in enumerate(data[KEY]):
            if job["id"] != job_id:
                continue
            updated = {**job, **{k: v for k, v in patch.items() if k != "id"}}
            # A new update line counts as fresh activity on the application.
            if patch.get("latest_update"):
                updated["latest_update_date"] = patch.get("latest_update_date") or today()
            data[KEY][idx] = _normalize(updated)
            save(data)
            return data[KEY][idx]
        return None


def delete_job(job_id: str) -> bool:
    with _lock:
        data = load()
        remaining = [j for j in data[KEY] if j["id"] != job_id]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        save(data)
        return True


def add_followup(job_id: str, note: str, on: str | None = None) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, job in enumerate(data[KEY]):
            if job["id"] != job_id:
                continue
            when = on or today()
            job["follow_ups_sent"].append({"date": when, "note": note})
            job["latest_update_date"] = when
            job["latest_update"] = f"Follow-up sent: {note}" if note else "Follow-up sent"
            data[KEY][idx] = _normalize(job)
            save(data)
            return data[KEY][idx]
        return None


def add_round(job_id: str, round_data: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, job in enumerate(data[KEY]):
            if job["id"] != job_id:
                continue
            number = round_data.get("round") or len(job["rounds"]) + 1
            entry = {
                "round": number,
                "name": round_data.get("name") or "",
                "date": round_data.get("date") or today(),
                "result": round_data.get("result") or "pending",
                "feedback": round_data.get("feedback") or "",
            }
            job["rounds"].append(entry)
            job["rounds"].sort(key=lambda r: r["round"])
            job["latest_update_date"] = entry["date"]
            label = f" ({entry['name']})" if entry["name"] else ""
            job["latest_update"] = f"Round {number}{label}: {entry['result']}"
            if entry["result"] == "rejected":
                job["status"] = "rejected"
            elif job["status"] in ("saved", "applied"):
                job["status"] = "interviewing"
            data[KEY][idx] = _normalize(job)
            save(data)
            return data[KEY][idx]
        return None


def update_round(
    job_id: str, round_number: int, patch: dict[str, Any]
) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, job in enumerate(data[KEY]):
            if job["id"] != job_id:
                continue
            for rnd in job["rounds"]:
                if rnd["round"] != round_number:
                    continue
                rnd.update({k: v for k, v in patch.items() if v is not None})
                job["latest_update_date"] = today()
                job["latest_update"] = (
                    f"Round {round_number} updated: {rnd.get('result', 'pending')}"
                )
                if rnd.get("result") == "rejected":
                    job["status"] = "rejected"
                data[KEY][idx] = _normalize(job)
                save(data)
                return data[KEY][idx]
            return None
        return None


def add_contact(job_id: str, contact: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, job in enumerate(data[KEY]):
            if job["id"] != job_id:
                continue
            job["contacts"].append(
                {
                    "name": contact.get("name", ""),
                    "role": contact.get("role") or "other",
                    "email": contact.get("email"),
                    "linkedin": contact.get("linkedin"),
                    "phone": contact.get("phone"),
                    "is_referral": bool(contact.get("is_referral", False)),
                    "notes": contact.get("notes", ""),
                }
            )
            if contact.get("is_referral") and not job.get("referred_by"):
                job["referred_by"] = contact.get("name")
            data[KEY][idx] = _normalize(job)
            save(data)
            return data[KEY][idx]
        return None


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------


def last_activity(job: dict[str, Any]) -> date:
    """Most recent date anything happened on this application.

    date_created is only a fallback: _normalize already seeds
    latest_update_date from it, so including it in the max would let a
    freshly-created record mask a deliberately older update date.
    """
    candidates = [parse_date(job.get("latest_update_date"))]
    candidates += [parse_date(f.get("date")) for f in job.get("follow_ups_sent", [])]
    candidates += [parse_date(r.get("date")) for r in job.get("rounds", [])]
    real = [c for c in candidates if c]
    return max(real) if real else (parse_date(job.get("date_created")) or date.today())


def reached_interview(job: dict[str, Any]) -> bool:
    """True if they ever got to an interview, even if later rejected."""
    return bool(job.get("rounds")) or job["status"] in ("interviewing", "offer")


def stats() -> dict[str, Any]:
    jobs = list_jobs()
    total = len(jobs)
    by_status = {status: 0 for status in STATUSES}
    for job in jobs:
        by_status[job["status"]] = by_status.get(job["status"], 0) + 1

    # "Saved" records aren't applications yet, so they're excluded from rates.
    applied = [j for j in jobs if j["status"] != "saved"]
    applied_total = len(applied)
    responded = sum(1 for j in applied if j["status"] in RESPONDED_STATUSES)
    interviewed = sum(1 for j in applied if reached_interview(j))

    def breakdown(field: str) -> dict[str, dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for job in applied:
            groups.setdefault(job.get(field) or "unknown", []).append(job)
        return {
            key: {
                "applications": len(group),
                "response_rate": pct(
                    sum(1 for j in group if j["status"] in RESPONDED_STATUSES), len(group)
                ),
                "interview_rate": pct(
                    sum(1 for j in group if reached_interview(j)), len(group)
                ),
            }
            for key, group in sorted(groups.items())
        }

    cutoff = date.today() - timedelta(days=28)
    recent = [j for j in applied if (parse_date(j.get("date_created")) or date.today()) >= cutoff]

    return {
        "total": total,
        "applied_total": applied_total,
        "active": sum(1 for j in jobs if j["status"] in ACTIVE_STATUSES),
        "by_status": by_status,
        "status_percentages": {k: pct(v, total) for k, v in by_status.items()},
        "response_rate": pct(responded, applied_total),
        "interview_rate": pct(interviewed, applied_total),
        "offer_rate": pct(by_status.get("offer", 0), applied_total),
        "rejection_rate": pct(by_status.get("rejected", 0), applied_total),
        "follow_ups_sent": sum(len(j.get("follow_ups_sent", [])) for j in jobs),
        "rounds_completed": sum(len(j.get("rounds", [])) for j in jobs),
        "referrals": sum(1 for j in jobs if j.get("referred_by")),
        "applications_last_28_days": len(recent),
        "applications_per_week": round(len(recent) / 4, 1),
        "by_company_type": breakdown("company_type"),
        "by_source": breakdown("source"),
    }


def followup_suggestions(stale_days: int = 7) -> list[dict[str, Any]]:
    """Active applications with no activity for `stale_days` — who to chase."""
    current = date.today()
    out = []
    for job in list_jobs():
        if job["status"] not in ACTIVE_STATUSES:
            continue
        days = (current - last_activity(job)).days
        if days < stale_days:
            continue
        out.append(
            {
                "id": job["id"],
                "job_title": job["job_title"],
                "organisation": job["organisation"],
                "status": job["status"],
                "days_since_activity": days,
                "latest_update": job["latest_update"],
                "follow_ups_sent": len(job.get("follow_ups_sent", [])),
                "contacts": job.get("contacts", []),
            }
        )
    out.sort(key=lambda item: item["days_since_activity"], reverse=True)
    return out
