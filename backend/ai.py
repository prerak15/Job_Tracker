"""AI chat backed by the Claude Agent SDK.

Runs on top of the Claude Code CLI, so it authenticates with the existing
Claude subscription — no ANTHROPIC_API_KEY required.

Every tool here delegates to the storage modules, so the AI writes through
exactly the same code path as the REST API. Tools run in-process (SDK MCP
server), so there is no subprocess or network hop for a tool call.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

import design
import dsa
import prep
import resumes
import storage

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVER_NAME = "tracker"


def _ok(payload: Any) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _err(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "is_error": True}


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
STR_LIST = {"type": "array", "items": {"type": "string"}}

# LaTeX math without the delimiters, so it renders in the dashboard and pastes
# straight into a write-up.
TIME_COMPLEXITY = {
    "type": "string",
    "description": r"Time complexity as LaTeX, no delimiters, e.g. O(n \log n)",
}
SPACE_COMPLEXITY = {
    "type": "string",
    "description": r"Space complexity as LaTeX, no delimiters, e.g. O(h) for recursion depth",
}
PHASE = {
    "type": "string",
    "description": "Curriculum phase key from get_prep_profile, e.g. phase_2",
}


def _brief_job(job: dict[str, Any]) -> dict[str, Any]:
    """Compact projection — full records would flood the context window."""
    return {
        "id": job["id"],
        "job_title": job["job_title"],
        "organisation": job["organisation"],
        "status": job["status"],
        "latest_update": job["latest_update"],
        "latest_update_date": job["latest_update_date"],
        "rounds": len(job["rounds"]),
        "follow_ups": len(job["follow_ups_sent"]),
        "company_type": job["company_type"],
        "resume_id": job["resume_id"],
    }


# --------------------------------------------------------------------------
# job tools
# --------------------------------------------------------------------------


@tool(
    "list_jobs",
    "List job applications. Pass a query to search by organisation or job title; "
    "omit it to list everything. Use this to find a job's id before updating it.",
    schema({"query": STR}),
)
async def list_jobs_tool(args: dict[str, Any]) -> dict[str, Any]:
    query_text = (args.get("query") or "").strip()
    jobs = storage.find_jobs(query_text) if query_text else storage.list_jobs()
    return _ok([_brief_job(j) for j in jobs])


@tool(
    "get_job",
    "Get the full record for one application, including rounds, contacts, "
    "follow-ups and the stored job description.",
    schema({"job_id": STR}, ["job_id"]),
)
async def get_job_tool(args: dict[str, Any]) -> dict[str, Any]:
    job = storage.get_job(args["job_id"])
    return _ok(job) if job else _err("No job with that id.")


@tool(
    "add_job",
    "Create a job application record. Use this when the user pastes a job posting "
    "or mentions applying somewhere. Extract as much as the posting supports, "
    "classify company_type and industry, and write a one-or-two sentence org_summary "
    "of what the company actually does.",
    schema(
        {
            "job_title": STR,
            "organisation": STR,
            "status": {"type": "string", "enum": storage.STATUSES},
            "date_job_posted": {**STR, "description": "YYYY-MM-DD if the posting says"},
            "company_type": {"type": "string", "enum": storage.COMPANY_TYPES},
            "industry": {**STR, "description": "e.g. fintech, healthtech, devtools"},
            "org_summary": {**STR, "description": "1-2 sentences on what the org does"},
            "source": {"type": "string", "enum": storage.SOURCES},
            "found_via": {
                **STR,
                "description": "Where exactly it was found — the specific board, "
                "person, newsletter, group or post, e.g. 'LinkedIn post by their "
                "VP Eng' or 'forwarded by Anita'",
            },
            "location": STR,
            "salary_range": STR,
            "url": STR,
            "job_description": {**STR, "description": "Raw JD text, kept for resume tailoring"},
            "referred_by": STR,
            "latest_update": STR,
            "notes": STR,
        },
        ["job_title", "organisation"],
    ),
)
async def add_job_tool(args: dict[str, Any]) -> dict[str, Any]:
    return _ok(_brief_job(storage.create_job(args)))


@tool(
    "update_job",
    "Update fields on an existing application. Use this when the user reports an "
    "update ('got rejected from X', 'recruiter replied'). Always set latest_update "
    "to a short human description of what changed, and set status if it moved.",
    schema(
        {
            "job_id": STR,
            "status": {"type": "string", "enum": storage.STATUSES},
            "latest_update": STR,
            "job_title": STR,
            "organisation": STR,
            "company_type": {"type": "string", "enum": storage.COMPANY_TYPES},
            "industry": STR,
            "org_summary": STR,
            "source": {"type": "string", "enum": storage.SOURCES},
            "found_via": {
                **STR,
                "description": "Where exactly it was found — the specific board, "
                "person, newsletter, group or post, e.g. 'LinkedIn post by their "
                "VP Eng' or 'forwarded by Anita'",
            },
            "location": STR,
            "salary_range": STR,
            "url": STR,
            "job_description": STR,
            "referred_by": STR,
            "resume_id": STR,
            "notes": STR,
        },
        ["job_id"],
    ),
)
async def update_job_tool(args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.pop("job_id")
    job = storage.update_job(job_id, args)
    return _ok(_brief_job(job)) if job else _err("No job with that id.")


@tool(
    "add_followup",
    "Record that a follow-up was sent on an application.",
    schema({"job_id": STR, "note": STR, "date": STR}, ["job_id"]),
)
async def add_followup_tool(args: dict[str, Any]) -> dict[str, Any]:
    job = storage.add_followup(args["job_id"], args.get("note", ""), args.get("date"))
    return _ok(_brief_job(job)) if job else _err("No job with that id.")


@tool(
    "add_round",
    "Record an interview or assessment round with its result and feedback. "
    "Use this whenever the user shares how a round went.",
    schema(
        {
            "job_id": STR,
            "name": {**STR, "description": "e.g. Online assessment, Technical 1, HR"},
            "result": {"type": "string", "enum": storage.ROUND_RESULTS},
            "feedback": {**STR, "description": "What happened, what was hard"},
            "date": STR,
            "round": INT,
        },
        ["job_id"],
    ),
)
async def add_round_tool(args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.pop("job_id")
    job = storage.add_round(job_id, args)
    return _ok(_brief_job(job)) if job else _err("No job with that id.")


@tool(
    "update_round",
    "Update an existing round's result or feedback.",
    schema(
        {
            "job_id": STR,
            "round": INT,
            "result": {"type": "string", "enum": storage.ROUND_RESULTS},
            "feedback": STR,
            "name": STR,
            "date": STR,
        },
        ["job_id", "round"],
    ),
)
async def update_round_tool(args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.pop("job_id")
    number = args.pop("round")
    job = storage.update_round(job_id, number, args)
    return _ok(_brief_job(job)) if job else _err("No job or round with that id/number.")


@tool(
    "add_contact",
    "Add an HR / recruiter / hiring manager / referral contact to an application.",
    schema(
        {
            "job_id": STR,
            "name": STR,
            "role": {"type": "string", "enum": storage.CONTACT_ROLES},
            "email": STR,
            "linkedin": STR,
            "phone": STR,
            "is_referral": BOOL,
            "notes": STR,
        },
        ["job_id", "name"],
    ),
)
async def add_contact_tool(args: dict[str, Any]) -> dict[str, Any]:
    job_id = args.pop("job_id")
    job = storage.add_contact(job_id, args)
    return _ok(_brief_job(job)) if job else _err("No job with that id.")


@tool(
    "get_followup_suggestions",
    "List applications that have gone quiet and are due a follow-up. Use this "
    "whenever the user asks who they should follow up with or chase.",
    schema({"stale_days": {**INT, "description": "Days of silence to qualify, default 7"}}),
)
async def followup_suggestions_tool(args: dict[str, Any]) -> dict[str, Any]:
    return _ok(storage.followup_suggestions(args.get("stale_days") or 7))


@tool(
    "get_stats",
    "Overall application stats: counts by status, response/interview/offer rates, "
    "and breakdowns by company type and source.",
    schema({}),
)
async def stats_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(storage.stats())


# --------------------------------------------------------------------------
# resume tools
# --------------------------------------------------------------------------


@tool(
    "list_resumes",
    "List resume versions with their ids, labels and per-version outcomes.",
    schema({}),
)
async def list_resumes_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(
        [
            {
                "id": r["id"],
                "name": r["name"],
                "version_label": r["version_label"],
                "is_master": r["is_master"],
                "is_latex_template": r["is_latex_template"],
                "target_role": r["target_role"],
                "has_content": bool(r["content"]),
                "has_latex": bool(r["latex_content"]),
                "used_for": len(r["used_for"]),
                "tailoring_entries": len(r["tailoring"]),
            }
            for r in resumes.list_resumes()
        ]
    )


@tool(
    "get_resume",
    "Get one resume version in full, including its text content — needed before tailoring.",
    schema({"resume_id": STR}, ["resume_id"]),
)
async def get_resume_tool(args: dict[str, Any]) -> dict[str, Any]:
    resume = resumes.get_resume(args["resume_id"])
    return _ok(resume) if resume else _err("No resume with that id.")


@tool(
    "add_resume",
    "Create a resume version. Paste the resume text into content so it can be "
    "tailored against job descriptions later.",
    schema(
        {
            "name": STR,
            "version_label": {**STR, "description": "e.g. v1, v2-backend"},
            "content": {**STR, "description": "Full resume text"},
            "latex_content": {
                **STR,
                "description": "Full LaTeX source, when the user works in LaTeX",
            },
            "is_latex_template": {
                **BOOL,
                "description": "True only for the reusable LaTeX template/master",
            },
            "target_role": STR,
            "is_master": BOOL,
            "based_on": {**STR, "description": "Parent resume id if this is a tailored copy"},
            "file_path": STR,
            "notes": STR,
        },
        ["name"],
    ),
)
async def add_resume_tool(args: dict[str, Any]) -> dict[str, Any]:
    resume = resumes.create_resume(args)
    return _ok({"id": resume["id"], "name": resume["name"]})


@tool(
    "link_resume_to_job",
    "Record which resume version was sent to which application. This is what "
    "makes per-version response rates meaningful.",
    schema({"resume_id": STR, "job_id": STR}, ["resume_id", "job_id"]),
)
async def link_resume_tool(args: dict[str, Any]) -> dict[str, Any]:
    resume = resumes.link_to_job(args["resume_id"], args["job_id"])
    return _ok({"linked": bool(resume)}) if resume else _err("No resume with that id.")


@tool(
    "save_resume_tailoring",
    "Save tailoring suggestions for a resume against a specific job description. "
    "First read the job (get_job) and the resume (get_resume), compare them "
    "yourself, then record the keywords the resume is missing and concrete "
    "per-section rewrites. Do not invent experience the user does not have — "
    "suggest reframing what is already there.",
    schema(
        {
            "resume_id": STR,
            "job_id": STR,
            "missing_keywords": {
                **STR_LIST,
                "description": "Terms in the JD absent from the resume",
            },
            "suggestions": {
                "type": "array",
                "description": "Concrete per-section changes",
                "items": {
                    "type": "object",
                    "properties": {"section": STR, "change": STR},
                    "required": ["section", "change"],
                },
            },
        },
        ["resume_id", "suggestions"],
    ),
)
async def save_tailoring_tool(args: dict[str, Any]) -> dict[str, Any]:
    resume_id = args.pop("resume_id")
    resume = resumes.add_tailoring(resume_id, args)
    return _ok({"saved": True}) if resume else _err("No resume with that id.")


@tool(
    "get_resume_stats",
    "Per-resume-version outcomes — which version actually gets replies.",
    schema({}),
)
async def resume_stats_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(resumes.stats())


# --------------------------------------------------------------------------
# dsa tools
# --------------------------------------------------------------------------


@tool(
    "list_dsa_problems",
    "List DSA problems. Pass a query to search by title or topic.",
    schema({"query": STR}),
)
async def list_problems_tool(args: dict[str, Any]) -> dict[str, Any]:
    query_text = (args.get("query") or "").strip()
    problems = dsa.find_problems(query_text) if query_text else dsa.list_problems()
    return _ok(
        [
            {
                "id": p["id"],
                "title": p["title"],
                "difficulty": p["difficulty"],
                "status": p["status"],
                "topics": p["topics"],
                "date_started": p["date_started"],
                "date_completed": p["date_completed"],
                "confidence": p["confidence"],
                "issues": len(p["issues"]),
            }
            for p in problems
        ]
    )


@tool(
    "add_dsa_problem",
    "Record a DSA problem. Set status to in_progress when the user starts one and "
    "solved when they finish. Dates are stamped automatically from the status.",
    schema(
        {
            "title": STR,
            "difficulty": {"type": "string", "enum": dsa.DIFFICULTIES},
            "platform": {"type": "string", "enum": dsa.PLATFORMS},
            "topics": {**STR_LIST, "description": "e.g. dp, binary-search, graphs"},
            "status": {"type": "string", "enum": dsa.DSA_STATUSES},
            "url": STR,
            "date_started": STR,
            "date_completed": STR,
            "time_spent_minutes": INT,
            "attempts": INT,
            "used_hint": BOOL,
            "solution_notes": STR,
            "time_complexity": TIME_COMPLEXITY,
            "space_complexity": SPACE_COMPLEXITY,
            "phase": PHASE,
            "confidence": {**INT, "description": "1-5, how solid it feels"},
            "company_tags": STR_LIST,
        },
        ["title"],
    ),
)
async def add_problem_tool(args: dict[str, Any]) -> dict[str, Any]:
    problem = dsa.create_problem(args)
    return _ok({"id": problem["id"], "title": problem["title"], "status": problem["status"]})


@tool(
    "update_dsa_problem",
    "Update a DSA problem — typically to mark it solved with the time taken, "
    "attempts, and a confidence score.",
    schema(
        {
            "problem_id": STR,
            "status": {"type": "string", "enum": dsa.DSA_STATUSES},
            "difficulty": {"type": "string", "enum": dsa.DIFFICULTIES},
            "topics": STR_LIST,
            "time_spent_minutes": INT,
            "attempts": INT,
            "used_hint": BOOL,
            "solution_notes": STR,
            "time_complexity": TIME_COMPLEXITY,
            "space_complexity": SPACE_COMPLEXITY,
            "phase": PHASE,
            "confidence": INT,
            "date_completed": STR,
            "url": STR,
            "company_tags": STR_LIST,
        },
        ["problem_id"],
    ),
)
async def update_problem_tool(args: dict[str, Any]) -> dict[str, Any]:
    problem_id = args.pop("problem_id")
    problem = dsa.update_problem(problem_id, args)
    return _ok({"id": problem["id"], "status": problem["status"]}) if problem else _err(
        "No problem with that id."
    )


@tool(
    "log_dsa_issue",
    "Log what went wrong on a DSA problem — the mistake, the concept missed, "
    "the thing that cost time. This is the most valuable field in the tracker.",
    schema({"problem_id": STR, "issue": STR, "date": STR}, ["problem_id", "issue"]),
)
async def log_dsa_issue_tool(args: dict[str, Any]) -> dict[str, Any]:
    problem = dsa.log_issue(args["problem_id"], args["issue"], args.get("date"))
    return _ok({"logged": True}) if problem else _err("No problem with that id.")


@tool(
    "log_dsa_revisit",
    "Record that a problem was redone, with the outcome and an updated confidence.",
    schema(
        {"problem_id": STR, "outcome": STR, "confidence": INT, "date": STR},
        ["problem_id", "outcome"],
    ),
)
async def log_dsa_revisit_tool(args: dict[str, Any]) -> dict[str, Any]:
    problem = dsa.log_revisit(
        args["problem_id"], args["outcome"], args.get("confidence"), args.get("date")
    )
    return _ok({"logged": True}) if problem else _err("No problem with that id.")


@tool(
    "get_dsa_stats",
    "DSA practice stats: solve rates by difficulty and topic, average time and "
    "attempts, hint rate, and the weakest topics.",
    schema({}),
)
async def dsa_stats_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(dsa.stats())


@tool(
    "get_dsa_revision_queue",
    "DSA problems due for revision — low confidence, solved with a hint, or stale.",
    schema({}),
)
async def dsa_revision_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(dsa.revision_queue())


# --------------------------------------------------------------------------
# interview prep tools (curriculum + standing weaknesses)
# --------------------------------------------------------------------------


@tool(
    "get_prep_profile",
    "The interview-prep profile: target levels and companies, the curriculum "
    "phases with per-phase solve rates, the current milestone, and the standing "
    "weakness checklist. Read this before presenting a new problem.",
    schema({}),
)
async def get_prep_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(prep.get_prep())


@tool(
    "get_prep_stats",
    "Curriculum progress and standing-weakness counts, including which habits "
    "recur most often.",
    schema({}),
)
async def prep_stats_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(prep.stats())


@tool(
    "get_interview_readiness",
    "Cross-domain check: interview rounds coming up, which live applications "
    "have no prep tagged against them, what is stuck, and what is due for "
    "revision. Use this for 'am I ready' or 'what should I work on' questions.",
    schema({}),
)
async def readiness_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(prep.readiness())


@tool(
    "set_prep_milestone",
    "Set the current milestone within the active curriculum phase.",
    schema({"milestone": STR, "phase_key": STR}, ["milestone"]),
)
async def set_milestone_tool(args: dict[str, Any]) -> dict[str, Any]:
    return _ok(prep.set_milestone(args["milestone"], args.get("phase_key")))


@tool(
    "set_prep_phase_status",
    "Mark a curriculum phase completed, current, or upcoming. Setting one "
    "current automatically demotes the previous current phase.",
    schema(
        {"phase_key": STR, "status": {"type": "string", "enum": prep.PHASE_STATUSES}},
        ["phase_key", "status"],
    ),
)
async def set_phase_tool(args: dict[str, Any]) -> dict[str, Any]:
    try:
        result = prep.set_phase_status(args["phase_key"], args["status"])
    except ValueError as exc:
        return _err(str(exc))
    return _ok(result) if result else _err("No phase with that key.")


@tool(
    "list_standing_issues",
    "The standing weakness checklist — recurring habits, not one-off mistakes. "
    "Check these against a submission before giving feedback.",
    schema({"active_only": BOOL}),
)
async def list_standing_issues_tool(args: dict[str, Any]) -> dict[str, Any]:
    return _ok(prep.list_standing_issues(bool(args.get("active_only"))))


@tool(
    "add_standing_issue",
    "Add a habit to the standing weakness checklist. Use this only for mistakes "
    "that have shown up on more than one problem — a one-off belongs in "
    "log_dsa_issue instead.",
    schema(
        {
            "issue": STR,
            "category": {"type": "string", "enum": prep.ISSUE_CATEGORIES},
            "date": STR,
        },
        ["issue"],
    ),
)
async def add_standing_issue_tool(args: dict[str, Any]) -> dict[str, Any]:
    try:
        record = prep.add_standing_issue(
            args["issue"], args.get("category", "logic"), args.get("date")
        )
    except ValueError as exc:
        return _err(str(exc))
    return _ok({"id": record["id"], "issue": record["issue"]})


@tool(
    "flag_standing_issue",
    "Record that a known standing weakness resurfaced on a problem. This drives "
    "the recurrence count, so flag it every time it happens.",
    schema({"issue_id": STR, "problem_id": STR, "date": STR}, ["issue_id"]),
)
async def flag_standing_issue_tool(args: dict[str, Any]) -> dict[str, Any]:
    record = prep.flag_standing_issue(
        args["issue_id"], args.get("date"), args.get("problem_id")
    )
    if not record:
        return _err("No standing issue with that id.")
    return _ok({"id": record["id"], "times_seen": len(record["seen_on"])})


@tool(
    "resolve_standing_issue",
    "Mark a standing weakness as beaten — only after it has stayed absent across "
    "several submissions, not on the first clean one.",
    schema({"issue_id": STR, "date": STR}, ["issue_id"]),
)
async def resolve_standing_issue_tool(args: dict[str, Any]) -> dict[str, Any]:
    record = prep.resolve_standing_issue(args["issue_id"], args.get("date"))
    return _ok({"resolved": True}) if record else _err("No standing issue with that id.")


# --------------------------------------------------------------------------
# system design tools
# --------------------------------------------------------------------------


@tool(
    "list_design_topics",
    "List system design topics (LLD and HLD). Pass a query to search by title or concept.",
    schema({"query": STR}),
)
async def list_design_tool(args: dict[str, Any]) -> dict[str, Any]:
    query_text = (args.get("query") or "").strip()
    topics = design.find_topics(query_text) if query_text else design.list_topics()
    return _ok(
        [
            {
                "id": t["id"],
                "title": t["title"],
                "kind": t["kind"],
                "status": t["status"],
                "concepts": t["concepts"],
                "confidence": t["confidence"],
                "issues": len(t["issues"]),
            }
            for t in topics
        ]
    )


@tool(
    "add_design_topic",
    "Record a system design topic. kind is hld for high-level/distributed design "
    "and lld for low-level/OOP design. Set status to studying when started and "
    "practiced once the user can produce the design themselves.",
    schema(
        {
            "title": STR,
            "kind": {"type": "string", "enum": design.KINDS},
            "status": {"type": "string", "enum": design.DESIGN_STATUSES},
            "concepts": {
                **STR_LIST,
                "description": "Cross-cutting ideas, e.g. sharding, caching, rate-limiting",
            },
            "components": {**STR_LIST, "description": "HLD building blocks used"},
            "patterns": {**STR_LIST, "description": "LLD design patterns used"},
            "tradeoffs": {**STR, "description": "The decisions taken and why"},
            "source": STR,
            "url": STR,
            "time_spent_minutes": INT,
            "confidence": {**INT, "description": "1-5"},
            "notes": STR,
            "company_tags": STR_LIST,
        },
        ["title"],
    ),
)
async def add_design_tool(args: dict[str, Any]) -> dict[str, Any]:
    topic = design.create_topic(args)
    return _ok({"id": topic["id"], "title": topic["title"], "kind": topic["kind"]})


@tool(
    "update_design_topic",
    "Update a system design topic — mark it practiced, record time spent, "
    "confidence, or the tradeoffs settled on.",
    schema(
        {
            "topic_id": STR,
            "status": {"type": "string", "enum": design.DESIGN_STATUSES},
            "kind": {"type": "string", "enum": design.KINDS},
            "concepts": STR_LIST,
            "components": STR_LIST,
            "patterns": STR_LIST,
            "tradeoffs": STR,
            "time_spent_minutes": INT,
            "confidence": INT,
            "notes": STR,
            "url": STR,
        },
        ["topic_id"],
    ),
)
async def update_design_tool(args: dict[str, Any]) -> dict[str, Any]:
    topic_id = args.pop("topic_id")
    topic = design.update_topic(topic_id, args)
    return _ok({"id": topic["id"], "status": topic["status"]}) if topic else _err(
        "No design topic with that id."
    )


@tool(
    "log_design_issue",
    "Log what was hard on a design topic — the part that couldn't be justified, "
    "the tradeoff that wasn't clear, the question that had no good answer.",
    schema({"topic_id": STR, "issue": STR, "date": STR}, ["topic_id", "issue"]),
)
async def log_design_issue_tool(args: dict[str, Any]) -> dict[str, Any]:
    topic = design.log_issue(args["topic_id"], args["issue"], args.get("date"))
    return _ok({"logged": True}) if topic else _err("No design topic with that id.")


@tool(
    "log_design_revisit",
    "Record that a design was re-derived, with the outcome and updated confidence.",
    schema(
        {"topic_id": STR, "outcome": STR, "confidence": INT, "date": STR},
        ["topic_id", "outcome"],
    ),
)
async def log_design_revisit_tool(args: dict[str, Any]) -> dict[str, Any]:
    topic = design.log_revisit(
        args["topic_id"], args["outcome"], args.get("confidence"), args.get("date")
    )
    return _ok({"logged": True}) if topic else _err("No design topic with that id.")


@tool(
    "get_design_stats",
    "System design stats: LLD vs HLD progress, weak concepts, revision due.",
    schema({}),
)
async def design_stats_tool(_: dict[str, Any]) -> dict[str, Any]:
    return _ok(design.stats())


# --------------------------------------------------------------------------
# agent wiring
# --------------------------------------------------------------------------

TOOLS = [
    list_jobs_tool,
    get_job_tool,
    add_job_tool,
    update_job_tool,
    add_followup_tool,
    add_round_tool,
    update_round_tool,
    add_contact_tool,
    followup_suggestions_tool,
    stats_tool,
    list_resumes_tool,
    get_resume_tool,
    add_resume_tool,
    link_resume_tool,
    save_tailoring_tool,
    resume_stats_tool,
    list_problems_tool,
    add_problem_tool,
    update_problem_tool,
    log_dsa_issue_tool,
    log_dsa_revisit_tool,
    dsa_stats_tool,
    dsa_revision_tool,
    get_prep_tool,
    prep_stats_tool,
    readiness_tool,
    set_milestone_tool,
    set_phase_tool,
    list_standing_issues_tool,
    add_standing_issue_tool,
    flag_standing_issue_tool,
    resolve_standing_issue_tool,
    list_design_tool,
    add_design_tool,
    update_design_tool,
    log_design_issue_tool,
    log_design_revisit_tool,
    design_stats_tool,
]

ALLOWED_TOOLS = [f"mcp__{SERVER_NAME}__{t.name}" for t in TOOLS] + ["WebSearch"]


# Deliberately NOT an f-string: the prompt contains LaTeX macro examples full
# of braces, which an f-string would try to interpolate. The date is the only
# dynamic part, so it is prepended instead.
_SYSTEM_PROMPT = """You are the assistant for Prerak's personal job-search tracker.

You maintain four things: job applications, resume versions, DSA practice, and
system design study. You have tools for all of them — use them rather than just
replying, because the dashboard reads what you write.

How to handle common messages:

- A pasted job posting -> add_job. Extract the title, organisation, posted date,
  location, salary and URL if present. Classify company_type and industry. Write
  a one-or-two sentence org_summary of what the company actually does; if the
  posting doesn't say and the company isn't obvious, use WebSearch once to find
  out. Store the posting text in job_description so it can be used for resume
  tailoring later.
  Set status to "applied" only if the user says they applied. If they are just
  saving something they found and haven't applied to yet, use "saved" — that is
  the lead state, shown in the app as "yet to apply".
  If the user says where they came across the role, record both: `source` for
  the broad channel and `found_via` for the specific detail. Don't guess
  `found_via` — leave it empty unless they actually said.
- An update on an application ("rejected from X", "recruiter replied", "OA next
  week") -> list_jobs to find the record, then update_job with a status change
  and a short latest_update. Interview and assessment outcomes go in add_round
  with the feedback the user gives.
- "Who should I follow up with?" -> get_followup_suggestions, then answer with
  the organisations, how long they've been quiet, and who the contact is.
- "What should I work on?" / "Am I ready?" -> get_interview_readiness. Lead
  with the nearest scheduled round and how many days away it is, then what is
  stuck, then what is due for revision. If a live application has no practice
  tagged against it, say so — that is the gap worth closing first.
- A resume tailoring request ("what should I change") -> get_job for the JD,
  get_resume for the text, compare them yourself, then save_resume_tailoring.
- A resume *generation* request ("generate a resume for this job") -> get_job
  for the JD, list_resumes and get_resume to read the best starting point
  (prefer the master version, or the one whose target_role is closest), then
  write a tailored version and store it with add_resume: set based_on to the
  source version's id, name it after the company, and put the full rewritten
  resume text in content. Then call link_resume_to_job so the application
  records which version was sent, and save_resume_tailoring to record what you
  changed and why. If no resume exists yet with text in it, say so and ask the
  user to add one rather than inventing a resume from nothing.

  When rewriting: reorder and reword what the user already has to match the
  JD's language and priorities. Never add a skill, employer, project, metric,
  or year of experience they haven't stated somewhere. If the JD wants
  something they genuinely lack, leave it out and mention the gap in your reply
  rather than papering over it.

  Resume `content` must follow this layout, because it is parsed back out to
  produce a downloadable Word document:
    line 1        the person's name, on its own
    next line(s)  contact details
    then, repeating: a SECTION HEADING IN ALL CAPS, followed by its content
  Inside a section, a role or qualification line sits on its own and its
  detail lines each start with "- ". Use blank lines between blocks. Do not
  use markdown, asterisks, or "•" characters — plain text only.

  LaTeX is the primary format. If any stored version has latex_content (check
  has_latex via list_resumes, and prefer the one with is_latex_template set),
  read it with get_resume and produce the tailored version as latex_content —
  this is what the PDF download compiles, so treat it as the real deliverable
  and set it whenever a template exists.

  Copy the template's entire preamble verbatim: the documentclass, every
  \\usepackage, the margin and \\titleformat settings, \\pdfgentounicode=1
  (which keeps the PDF ATS-parsable), and all the \\newcommand definitions.
  Then reuse its macros for the body rather than inventing layout:
    \\section{...}                             a section
    \\resumeSubHeadingListStart / ...End       wraps a group of entries
    \\resumeSubheading{org}{right}{role}{date} an employer or qualification
    \\resumeProjectHeading{name}{right}        a project
    \\resumeItemListStart / ...End             wraps the bullets
    \\resumeItem{...}                          one bullet
  Keep the section order the template uses, and keep every section it has
  (Education, Work Experience, Projects, Skills & Certifications) unless the
  user asks otherwise — only the wording inside changes.

  Escape &, %, $, #, and _ as \\&, \\%, \\$, \\#, \\_ in anything you write,
  and end the document with \\end{document}. Set content (plain text) as well
  as latex_content so the Word download and the dashboard preview agree.
- DSA or system design activity -> record it with the timings, and always log
  the issue when the user says something was hard or went wrong. The issue log
  is the most valuable part of that data. Record time_complexity and
  space_complexity as LaTeX without delimiters (O(n \\log n), O(h)) whenever
  the user states them, and tag the problem with the curriculum phase it
  belongs to.

Interview mode — when Prerak asks for a problem, submits a solution, or asks to
be interviewed, act as a FAANG coding interviewer calibrated to SWE2 (L3/E3)
and SWE3 (L4/E4) at Google, Meta and Apple. Read get_prep_profile first so you
know the current phase, milestone, and standing weaknesses.

  Presenting a problem:
  - Give the LeetCode number and title. Nothing else.
  - No description, no function signature, no test harness, no edge cases, no
    starter template, no hints. He reads the problem on LeetCode himself.
  - Never volunteer a solution or an approach alongside the problem.
  - Pick it from the current phase and milestone unless he asks otherwise, and
    record it with add_dsa_problem as status in_progress and the right phase.

  Hints — only when he explicitly asks. Give one minimal nudge aimed at the
  specific place his logic broke: a guiding question or a single conceptual
  pointer. Never the solution, never the full approach. Then set used_hint.

  Grading a submission — evaluate against all of:
  - correctness
  - optimal time complexity
  - optimal space complexity
  - complexity analysis stated in LaTeX
  - code cleanliness and modularity
  - boundary and edge-case handling
  - architectural trade-offs (recursion vs iteration, and why)

  Then write it down: update_dsa_problem with status, attempts, confidence and
  both complexities; log_dsa_issue for anything that went wrong this time.
  Cross-check the submission against list_standing_issues — if a known habit
  reappeared, call flag_standing_issue so the recurrence count is real. If a
  new mistake shows up that he has now made on more than one problem, promote
  it with add_standing_issue. Only resolve_standing_issue after it has stayed
  absent across several submissions, not on the first clean one.

  Keep feedback scannable, direct and concise.

Rules:
- Look up ids with the list_ tools before updating; never guess an id.
- If a message is ambiguous about which record it refers to, ask rather than
  updating the wrong one.
- Don't invent data the user hasn't given you. Leave fields empty instead.
- After making changes, reply in one or two sentences saying what you recorded.
  Don't restate the whole record — the dashboard shows it.
"""


def system_prompt() -> str:
    return f"Today is {date.today().isoformat()}.\n\n{_SYSTEM_PROMPT}"


def build_options(session_id: str | None) -> ClaudeAgentOptions:
    server = create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=TOOLS)
    return ClaudeAgentOptions(
        system_prompt=system_prompt(),
        mcp_servers={SERVER_NAME: server},
        allowed_tools=ALLOWED_TOOLS,
        # Only the tracker tools and WebSearch — no filesystem or shell access
        # from the web app.
        disallowed_tools=["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Task"],
        permission_mode="bypassPermissions",
        setting_sources=[],
        cwd=str(PROJECT_ROOT),
        max_turns=30,
        include_partial_messages=True,
        resume=session_id,
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream(message: str, session_id: str | None = None) -> AsyncIterator[str]:
    """Yield Server-Sent Events for one chat turn."""
    try:
        async for event in query(prompt=message, options=build_options(session_id)):
            if isinstance(event, StreamEvent):
                # Token-level text so the UI fills in as Claude writes.
                raw = event.event or {}
                if raw.get("type") == "content_block_delta":
                    delta = raw.get("delta") or {}
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        yield _sse({"type": "text", "text": delta["text"]})

            elif isinstance(event, AssistantMessage):
                # Surface tool calls so the UI can show what's being recorded.
                for block in event.content:
                    if isinstance(block, ToolUseBlock):
                        name = block.name.split("__")[-1]
                        yield _sse({"type": "tool", "name": name})

            elif isinstance(event, ResultMessage):
                if event.is_error:
                    yield _sse(
                        {
                            "type": "error",
                            "message": event.result or "The assistant hit an error.",
                        }
                    )
                yield _sse(
                    {
                        "type": "done",
                        "session_id": event.session_id,
                        "cost_usd": event.total_cost_usd,
                        "turns": event.num_turns,
                    }
                )
    except Exception as exc:  # surfaced in the chat panel rather than a 500
        yield _sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        yield _sse({"type": "done", "session_id": session_id})


# --------------------------------------------------------------------------
# Windows event-loop bridge
# --------------------------------------------------------------------------
#
# The SDK talks to the Claude Code CLI by spawning it as a subprocess, and on
# Windows asyncio can only do that on a ProactorEventLoop. uvicorn picks the
# loop with:
#
#     if sys.platform == "win32" and not use_subprocess: ProactorEventLoop
#     else:                                              SelectorEventLoop
#
# and `use_subprocess` is True whenever it runs with --reload or --workers. So
# the reload-enabled dev command in the README lands on the selector loop and
# every chat turn dies with a bare NotImplementedError, which the SDK reports
# as "Failed to start Claude Code: " with nothing after the colon.
#
# Rather than banning --reload, run the SDK on its own Proactor loop in a
# worker thread and forward the SSE frames back to the serving loop.

_DONE = object()


def _needs_proactor_bridge() -> bool:
    if sys.platform != "win32":
        return False
    proactor = getattr(asyncio, "ProactorEventLoop", None)
    if proactor is None:
        return False
    try:
        return not isinstance(asyncio.get_running_loop(), proactor)
    except RuntimeError:  # no running loop; nothing to bridge
        return False


def _pump(message: str, session_id: str | None, queue: Any, target: Any) -> None:
    """Run one chat turn on a private Proactor loop, in this thread."""

    def emit(frame: Any) -> None:
        # The queue belongs to the serving loop, so hand items over to it.
        target.call_soon_threadsafe(queue.put_nowait, frame)

    async def drain() -> None:
        async for frame in _stream(message, session_id):
            emit(frame)

    loop = asyncio.ProactorEventLoop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(drain())
    except Exception as exc:  # never strand the reader
        emit(_sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"}))
        emit(_sse({"type": "done", "session_id": session_id}))
    finally:
        emit(_DONE)
        asyncio.set_event_loop(None)
        loop.close()


async def stream_chat(message: str, session_id: str | None = None) -> AsyncIterator[str]:
    """Yield Server-Sent Events for one chat turn, bridging loops if needed."""
    if not _needs_proactor_bridge():
        async for frame in _stream(message, session_id):
            yield frame
        return

    queue: asyncio.Queue[Any] = asyncio.Queue()
    thread = threading.Thread(
        target=_pump,
        args=(message, session_id, queue, asyncio.get_running_loop()),
        name="claude-sdk-proactor",
        daemon=True,
    )
    thread.start()
    while True:
        frame = await queue.get()
        if frame is _DONE:
            return
        yield frame


def health() -> dict[str, Any]:
    """Report how the assistant will authenticate — shown in the chat panel.

    No API key is needed: the Agent SDK drives the Claude Code CLI, which
    reuses the existing Claude subscription login stored in ~/.claude. An
    ANTHROPIC_API_KEY is only used if one happens to be set in the
    environment, and it isn't required.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    from pathlib import Path as _Path  # noqa: PLC0415

    import claude_agent_sdk  # noqa: PLC0415

    bundled = _Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude.exe"
    cli = str(bundled) if bundled.exists() else shutil.which("claude")
    logged_in = (_Path.home() / ".claude" / ".credentials.json").exists()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if not cli:
        return {
            "ok": False,
            "auth": "none",
            "error": "Claude Code CLI not found.",
            "hint": "Reinstall claude-agent-sdk, or install the Claude Code CLI.",
            "tools": len(TOOLS),
        }
    if not logged_in and not has_key:
        return {
            "ok": False,
            "auth": "none",
            "error": "Not signed in to Claude.",
            "hint": "Run `claude` in a terminal once and sign in with your Claude account.",
            "tools": len(TOOLS),
        }
    return {
        "ok": True,
        "auth": "subscription" if logged_in else "api_key",
        "cli": cli,
        "tools": len(TOOLS),
    }
