"""Resume versions and JD-based tailoring — data/resumes.json.

A resume is a version of the document (master or a tailored copy). Tailoring
entries are AI-generated suggestions against a specific job description; they
are advisory — nothing is rewritten automatically, and each suggestion is
marked `applied` once actually made.
"""

from __future__ import annotations

from typing import Any

import storage
from jsonstore import apply_defaults, lock_for, new_id, pct, read, today, write

FILE = "resumes.json"
KEY = "resumes"
_lock = lock_for(FILE)

_DEFAULTS: dict[str, Any] = {
    "name": "",
    "version_label": "",
    "based_on": None,
    "file_path": None,
    "content": "",
    "target_role": None,
    "created_date": None,
    "is_master": False,
    "used_for": [],
    "tailoring": [],
    "notes": "",
}


def _normalize(resume: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(resume, _DEFAULTS)
    if not out["created_date"]:
        out["created_date"] = today()
    for entry in out["tailoring"]:
        entry.setdefault("date", out["created_date"])
        entry.setdefault("job_id", None)
        entry.setdefault("organisation", "")
        entry.setdefault("missing_keywords", [])
        entry.setdefault("suggestions", [])
        entry.setdefault("applied", False)
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = [_normalize(r) for r in data[KEY]]
    return data


def list_resumes() -> list[dict[str, Any]]:
    return load()[KEY]


def get_resume(resume_id: str) -> dict[str, Any] | None:
    return next((r for r in load()[KEY] if r["id"] == resume_id), None)


def create_resume(payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        resume = _normalize({**payload, "id": new_id()})
        data[KEY].append(resume)
        write(FILE, data)
        return resume


def update_resume(resume_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, resume in enumerate(data[KEY]):
            if resume["id"] != resume_id:
                continue
            data[KEY][idx] = _normalize({**resume, **{k: v for k, v in patch.items() if k != "id"}})
            write(FILE, data)
            return data[KEY][idx]
        return None


def delete_resume(resume_id: str) -> bool:
    with _lock:
        data = load()
        remaining = [r for r in data[KEY] if r["id"] != resume_id]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        write(FILE, data)
        return True


def add_tailoring(resume_id: str, entry: dict[str, Any]) -> dict[str, Any] | None:
    """Record a set of JD-based suggestions against this resume version."""
    with _lock:
        data = load()
        for idx, resume in enumerate(data[KEY]):
            if resume["id"] != resume_id:
                continue
            job_id = entry.get("job_id")
            organisation = entry.get("organisation") or ""
            if job_id and not organisation:
                job = storage.get_job(job_id)
                if job:
                    organisation = job["organisation"]
            resume["tailoring"].append(
                {
                    "date": entry.get("date") or today(),
                    "job_id": job_id,
                    "organisation": organisation,
                    "missing_keywords": entry.get("missing_keywords") or [],
                    "suggestions": entry.get("suggestions") or [],
                    "applied": bool(entry.get("applied", False)),
                }
            )
            data[KEY][idx] = _normalize(resume)
            write(FILE, data)
            return data[KEY][idx]
        return None


def set_tailoring_applied(
    resume_id: str, index: int, applied: bool
) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, resume in enumerate(data[KEY]):
            if resume["id"] != resume_id:
                continue
            if not 0 <= index < len(resume["tailoring"]):
                return None
            resume["tailoring"][index]["applied"] = applied
            data[KEY][idx] = _normalize(resume)
            write(FILE, data)
            return data[KEY][idx]
        return None


def link_to_job(resume_id: str, job_id: str) -> dict[str, Any] | None:
    """Record that this version was the one sent to a given application."""
    with _lock:
        data = load()
        for idx, resume in enumerate(data[KEY]):
            if resume["id"] != resume_id:
                continue
            if job_id not in resume["used_for"]:
                resume["used_for"].append(job_id)
            data[KEY][idx] = _normalize(resume)
            write(FILE, data)
            break
        else:
            return None
    storage.update_job(job_id, {"resume_id": resume_id})
    return get_resume(resume_id)


def stats() -> dict[str, Any]:
    """Per-version outcomes: which resume actually gets replies."""
    resumes = list_resumes()
    jobs_by_id = {j["id"]: j for j in storage.list_jobs()}

    per_version = []
    for resume in resumes:
        # Trust the job's resume_id as the authority, falling back to used_for.
        linked = [
            j
            for j in jobs_by_id.values()
            if j.get("resume_id") == resume["id"] or j["id"] in resume["used_for"]
        ]
        sent = [j for j in linked if j["status"] != "saved"]
        per_version.append(
            {
                "id": resume["id"],
                "name": resume["name"],
                "version_label": resume["version_label"],
                "is_master": resume["is_master"],
                "applications": len(sent),
                "responses": sum(
                    1 for j in sent if j["status"] in storage.RESPONDED_STATUSES
                ),
                "interviews": sum(1 for j in sent if storage.reached_interview(j)),
                "response_rate": pct(
                    sum(1 for j in sent if j["status"] in storage.RESPONDED_STATUSES),
                    len(sent),
                ),
                "interview_rate": pct(
                    sum(1 for j in sent if storage.reached_interview(j)), len(sent)
                ),
                "tailoring_entries": len(resume["tailoring"]),
                "tailoring_applied": sum(1 for t in resume["tailoring"] if t["applied"]),
            }
        )

    per_version.sort(key=lambda v: (-v["applications"], v["name"]))
    total_tailoring = sum(len(r["tailoring"]) for r in resumes)
    return {
        "total_versions": len(resumes),
        "master_versions": sum(1 for r in resumes if r["is_master"]),
        "tailoring_entries": total_tailoring,
        "tailoring_applied": sum(
            1 for r in resumes for t in r["tailoring"] if t["applied"]
        ),
        "jobs_without_resume": sum(
            1
            for j in jobs_by_id.values()
            if j["status"] != "saved" and not j.get("resume_id")
        ),
        "by_version": per_version,
    }
