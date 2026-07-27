"""System design study tracking (LLD + HLD) — data/design.json.

Mirrors the DSA module's started/completed/effort/issues/confidence shape so
the revision queue behaves the same way, but with design-specific vocabulary:
concepts (cross-cutting), components (HLD), patterns (LLD), and the tradeoffs
you'd actually have to defend in an interview.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from jsonstore import apply_defaults, lock_for, new_id, parse_date, pct, read, today, write

FILE = "design.json"
KEY = "topics"
_lock = lock_for(FILE)

KINDS = ["hld", "lld"]
DESIGN_STATUSES = ["todo", "studying", "practiced", "revisit", "stuck"]
ARTIFACT_TYPES = ["diagram", "doc", "code", "video", "other"]

# "practiced" means you can produce the design yourself, not just read it.
DONE_STATUSES = {"practiced", "revisit"}

LOW_CONFIDENCE = 3
REVISIT_AFTER_DAYS = 30

_DEFAULTS: dict[str, Any] = {
    "title": "",
    "kind": "hld",
    "source": None,
    "url": None,
    "status": "todo",
    "date_started": None,
    "date_completed": None,
    "time_spent_minutes": None,
    "concepts": [],
    "components": [],
    "patterns": [],
    "tradeoffs": "",
    "issues": [],
    "artifacts": [],
    "notes": "",
    "confidence": None,
    "revisits": [],
    "company_tags": [],
    "linked_job_id": None,
}


def _normalize(topic: dict[str, Any]) -> dict[str, Any]:
    out = apply_defaults(topic, _DEFAULTS)
    for issue in out["issues"]:
        issue.setdefault("date", out.get("date_started") or today())
        issue.setdefault("issue", "")
    for revisit in out["revisits"]:
        revisit.setdefault("date", today())
        revisit.setdefault("outcome", "")
    for artifact in out["artifacts"]:
        artifact.setdefault("type", "other")
        artifact.setdefault("path_or_url", "")
        artifact.setdefault("note", "")
    return out


def load() -> dict[str, Any]:
    data = read(FILE, KEY)
    data[KEY] = [_normalize(t) for t in data[KEY]]
    return data


def list_topics() -> list[dict[str, Any]]:
    return load()[KEY]


def get_topic(topic_id: str) -> dict[str, Any] | None:
    return next((t for t in load()[KEY] if t["id"] == topic_id), None)


def find_topics(query: str) -> list[dict[str, Any]]:
    needle = query.strip().lower()
    if not needle:
        return []
    return [
        t
        for t in load()[KEY]
        if needle in t["title"].lower() or any(needle in c.lower() for c in t["concepts"])
    ]


def create_topic(payload: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load()
        topic = _normalize({**payload, "id": new_id()})
        if topic["status"] in ("studying", *DONE_STATUSES) and not topic["date_started"]:
            topic["date_started"] = today()
        if topic["status"] in DONE_STATUSES and not topic["date_completed"]:
            topic["date_completed"] = today()
        data[KEY].append(topic)
        write(FILE, data)
        return topic


def update_topic(topic_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, topic in enumerate(data[KEY]):
            if topic["id"] != topic_id:
                continue
            updated = {**topic, **{k: v for k, v in patch.items() if k != "id"}}
            status = updated.get("status")
            if status in ("studying", *DONE_STATUSES) and not updated.get("date_started"):
                updated["date_started"] = today()
            if status in DONE_STATUSES and not updated.get("date_completed"):
                updated["date_completed"] = today()
            if status in ("todo", "stuck"):
                updated["date_completed"] = None
            data[KEY][idx] = _normalize(updated)
            write(FILE, data)
            return data[KEY][idx]
        return None


def delete_topic(topic_id: str) -> bool:
    with _lock:
        data = load()
        remaining = [t for t in data[KEY] if t["id"] != topic_id]
        if len(remaining) == len(data[KEY]):
            return False
        data[KEY] = remaining
        write(FILE, data)
        return True


def log_issue(topic_id: str, issue: str, on: str | None = None) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, topic in enumerate(data[KEY]):
            if topic["id"] != topic_id:
                continue
            topic["issues"].append({"date": on or today(), "issue": issue})
            data[KEY][idx] = _normalize(topic)
            write(FILE, data)
            return data[KEY][idx]
        return None


def log_revisit(
    topic_id: str, outcome: str, confidence: int | None = None, on: str | None = None
) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, topic in enumerate(data[KEY]):
            if topic["id"] != topic_id:
                continue
            topic["revisits"].append({"date": on or today(), "outcome": outcome})
            if confidence is not None:
                topic["confidence"] = confidence
            if topic["status"] == "revisit":
                topic["status"] = "practiced"
            data[KEY][idx] = _normalize(topic)
            write(FILE, data)
            return data[KEY][idx]
        return None


def add_artifact(topic_id: str, artifact: dict[str, Any]) -> dict[str, Any] | None:
    with _lock:
        data = load()
        for idx, topic in enumerate(data[KEY]):
            if topic["id"] != topic_id:
                continue
            topic["artifacts"].append(
                {
                    "type": artifact.get("type") or "other",
                    "path_or_url": artifact.get("path_or_url", ""),
                    "note": artifact.get("note", ""),
                }
            )
            data[KEY][idx] = _normalize(topic)
            write(FILE, data)
            return data[KEY][idx]
        return None


# --------------------------------------------------------------------------
# derived views
# --------------------------------------------------------------------------


def _last_touched(topic: dict[str, Any]) -> date | None:
    candidates = [parse_date(topic.get("date_completed")), parse_date(topic.get("date_started"))]
    candidates += [parse_date(r.get("date")) for r in topic.get("revisits", [])]
    real = [c for c in candidates if c]
    return max(real) if real else None


def stats() -> dict[str, Any]:
    topics = list_topics()
    total = len(topics)
    done = [t for t in topics if t["status"] in DONE_STATUSES]

    by_status = {status: 0 for status in DESIGN_STATUSES}
    for topic in topics:
        by_status[topic["status"]] = by_status.get(topic["status"], 0) + 1

    by_kind = {}
    for kind in KINDS:
        of_kind = [t for t in topics if t["kind"] == kind]
        done_of_kind = [t for t in of_kind if t["status"] in DONE_STATUSES]
        by_kind[kind] = {
            "total": len(of_kind),
            "practiced": len(done_of_kind),
            "completion_rate": pct(len(done_of_kind), len(of_kind)),
            "avg_confidence": (
                round(
                    sum(t["confidence"] for t in of_kind if t.get("confidence"))
                    / max(1, sum(1 for t in of_kind if t.get("confidence"))),
                    1,
                )
                if any(t.get("confidence") for t in of_kind)
                else 0
            ),
        }

    concepts: dict[str, dict[str, Any]] = {}
    for topic in topics:
        for concept in topic["concepts"] or ["untagged"]:
            bucket = concepts.setdefault(
                concept, {"total": 0, "practiced": 0, "stuck": 0, "issues": 0}
            )
            bucket["total"] += 1
            if topic["status"] in DONE_STATUSES:
                bucket["practiced"] += 1
            if topic["status"] == "stuck":
                bucket["stuck"] += 1
            bucket["issues"] += len(topic["issues"])
    for bucket in concepts.values():
        bucket["completion_rate"] = pct(bucket["practiced"], bucket["total"])

    weak_concepts = sorted(
        ({"concept": name, **bucket} for name, bucket in concepts.items()),
        key=lambda c: (c["completion_rate"], -(c["issues"] + c["stuck"])),
    )[:5]

    times = [t["time_spent_minutes"] for t in done if t.get("time_spent_minutes")]
    cutoff = date.today() - timedelta(days=28)
    recent = [
        t for t in done if (parse_date(t.get("date_completed")) or date.today()) >= cutoff
    ]

    return {
        "total": total,
        "practiced": len(done),
        "completion_rate": pct(len(done), total),
        "studying": by_status.get("studying", 0),
        "stuck": by_status.get("stuck", 0),
        "by_status": by_status,
        "status_percentages": {k: pct(v, total) for k, v in by_status.items()},
        "by_kind": by_kind,
        "by_concept": dict(sorted(concepts.items())),
        "weak_concepts": weak_concepts,
        "avg_time_minutes": round(sum(times) / len(times), 1) if times else 0,
        "issues_logged": sum(len(t["issues"]) for t in topics),
        "artifacts": sum(len(t["artifacts"]) for t in topics),
        "practiced_last_28_days": len(recent),
        "practiced_per_week": round(len(recent) / 4, 1),
        "revision_due": len(revision_queue()),
    }


def revision_queue() -> list[dict[str, Any]]:
    """Designs that are shaky or stale — re-derive these from scratch."""
    current = date.today()
    out = []
    for topic in list_topics():
        if topic["status"] == "revisit":
            reason = "flagged for revisit"
        elif topic["status"] in DONE_STATUSES:
            confidence = topic.get("confidence")
            touched = _last_touched(topic)
            days = (current - touched).days if touched else None
            if confidence is not None and confidence <= LOW_CONFIDENCE:
                reason = f"low confidence ({confidence}/5)"
            elif days is not None and days >= REVISIT_AFTER_DAYS:
                reason = f"not revisited in {days} days"
            elif topic["issues"] and not topic["revisits"]:
                reason = "had open issues, never redone"
            else:
                continue
        else:
            continue

        touched = _last_touched(topic)
        out.append(
            {
                "id": topic["id"],
                "title": topic["title"],
                "kind": topic["kind"],
                "url": topic["url"],
                "concepts": topic["concepts"],
                "confidence": topic.get("confidence"),
                "days_since_touched": (current - touched).days if touched else None,
                "reason": reason,
                "issues": topic["issues"],
            }
        )
    out.sort(key=lambda t: (t["confidence"] or 0, -(t["days_since_touched"] or 0)))
    return out
