"""FastAPI app for the personal job tracker.

Local-only: no auth, CORS open for localhost. Four domains — applications,
DSA practice, system design, resumes — plus an AI chat endpoint (ai.py) that
writes through the same storage modules as these REST endpoints.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import design
import dsa
import resumes
import storage

app = FastAPI(title="Job Tracker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _found(value: Any, what: str = "Record") -> Any:
    if value is None:
        raise HTTPException(404, f"{what} not found")
    return value


# --------------------------------------------------------------------------
# applications
# --------------------------------------------------------------------------

Status = Literal[
    "saved", "applied", "interviewing", "offer", "rejected", "ghosted", "withdrawn"
]


class ContactIn(BaseModel):
    name: str
    role: str = "other"
    email: str | None = None
    linkedin: str | None = None
    phone: str | None = None
    is_referral: bool = False
    notes: str = ""


class RoundIn(BaseModel):
    round: int | None = None
    name: str = ""
    date: str | None = None
    result: str = "pending"
    feedback: str = ""


class RoundPatch(BaseModel):
    name: str | None = None
    date: str | None = None
    result: str | None = None
    feedback: str | None = None


class JobIn(BaseModel):
    job_title: str
    organisation: str
    status: Status = "applied"
    date_job_posted: str | None = None
    latest_update: str = ""
    latest_update_date: str | None = None
    referred_by: str | None = None
    company_type: str | None = None
    industry: str | None = None
    org_summary: str | None = None
    source: str | None = None
    location: str | None = None
    salary_range: str | None = None
    job_description: str = ""
    resume_id: str | None = None
    notes: str = ""
    url: str | None = None
    contacts: list[ContactIn] = Field(default_factory=list)


class JobPatch(BaseModel):
    job_title: str | None = None
    organisation: str | None = None
    status: Status | None = None
    date_job_posted: str | None = None
    latest_update: str | None = None
    latest_update_date: str | None = None
    referred_by: str | None = None
    company_type: str | None = None
    industry: str | None = None
    org_summary: str | None = None
    source: str | None = None
    location: str | None = None
    salary_range: str | None = None
    job_description: str | None = None
    resume_id: str | None = None
    notes: str | None = None
    url: str | None = None


class FollowUpIn(BaseModel):
    note: str = ""
    date: str | None = None


@app.get("/api/jobs")
def get_jobs() -> list[dict[str, Any]]:
    return storage.list_jobs()


@app.post("/api/jobs", status_code=201)
def post_job(payload: JobIn) -> dict[str, Any]:
    return storage.create_job(payload.model_dump())


@app.get("/api/jobs/{job_id}")
def get_one_job(job_id: str) -> dict[str, Any]:
    return _found(storage.get_job(job_id), "Job")


@app.patch("/api/jobs/{job_id}")
def patch_job(job_id: str, payload: JobPatch) -> dict[str, Any]:
    return _found(
        storage.update_job(job_id, payload.model_dump(exclude_unset=True)), "Job"
    )


@app.delete("/api/jobs/{job_id}", status_code=204)
def remove_job(job_id: str) -> None:
    if not storage.delete_job(job_id):
        raise HTTPException(404, "Job not found")


@app.post("/api/jobs/{job_id}/followup")
def post_followup(job_id: str, payload: FollowUpIn) -> dict[str, Any]:
    return _found(storage.add_followup(job_id, payload.note, payload.date), "Job")


@app.post("/api/jobs/{job_id}/rounds")
def post_round(job_id: str, payload: RoundIn) -> dict[str, Any]:
    return _found(storage.add_round(job_id, payload.model_dump()), "Job")


@app.patch("/api/jobs/{job_id}/rounds/{round_number}")
def patch_round(job_id: str, round_number: int, payload: RoundPatch) -> dict[str, Any]:
    return _found(
        storage.update_round(job_id, round_number, payload.model_dump(exclude_unset=True)),
        "Job or round",
    )


@app.post("/api/jobs/{job_id}/contacts")
def post_contact(job_id: str, payload: ContactIn) -> dict[str, Any]:
    return _found(storage.add_contact(job_id, payload.model_dump()), "Job")


@app.get("/api/stats")
def get_stats() -> dict[str, Any]:
    return storage.stats()


@app.get("/api/followup-suggestions")
def get_followup_suggestions(stale_days: int = 7) -> list[dict[str, Any]]:
    return storage.followup_suggestions(stale_days)


# --------------------------------------------------------------------------
# resumes
# --------------------------------------------------------------------------


class ResumeIn(BaseModel):
    name: str
    version_label: str = ""
    based_on: str | None = None
    file_path: str | None = None
    content: str = ""
    target_role: str | None = None
    is_master: bool = False
    notes: str = ""


class ResumePatch(BaseModel):
    name: str | None = None
    version_label: str | None = None
    based_on: str | None = None
    file_path: str | None = None
    content: str | None = None
    target_role: str | None = None
    is_master: bool | None = None
    notes: str | None = None


class SuggestionIn(BaseModel):
    section: str = ""
    change: str = ""


class TailoringIn(BaseModel):
    job_id: str | None = None
    organisation: str = ""
    missing_keywords: list[str] = Field(default_factory=list)
    suggestions: list[SuggestionIn] = Field(default_factory=list)
    date: str | None = None


class AppliedIn(BaseModel):
    applied: bool = True


@app.get("/api/resumes")
def get_resumes() -> list[dict[str, Any]]:
    return resumes.list_resumes()


@app.post("/api/resumes", status_code=201)
def post_resume(payload: ResumeIn) -> dict[str, Any]:
    return resumes.create_resume(payload.model_dump())


@app.get("/api/resumes/stats")
def get_resume_stats() -> dict[str, Any]:
    return resumes.stats()


@app.get("/api/resumes/{resume_id}")
def get_one_resume(resume_id: str) -> dict[str, Any]:
    return _found(resumes.get_resume(resume_id), "Resume")


@app.patch("/api/resumes/{resume_id}")
def patch_resume(resume_id: str, payload: ResumePatch) -> dict[str, Any]:
    return _found(
        resumes.update_resume(resume_id, payload.model_dump(exclude_unset=True)), "Resume"
    )


@app.delete("/api/resumes/{resume_id}", status_code=204)
def remove_resume(resume_id: str) -> None:
    if not resumes.delete_resume(resume_id):
        raise HTTPException(404, "Resume not found")


@app.post("/api/resumes/{resume_id}/tailor")
def post_tailoring(resume_id: str, payload: TailoringIn) -> dict[str, Any]:
    return _found(resumes.add_tailoring(resume_id, payload.model_dump()), "Resume")


@app.patch("/api/resumes/{resume_id}/tailor/{index}")
def patch_tailoring(resume_id: str, index: int, payload: AppliedIn) -> dict[str, Any]:
    return _found(
        resumes.set_tailoring_applied(resume_id, index, payload.applied),
        "Resume or tailoring entry",
    )


@app.post("/api/resumes/{resume_id}/link/{job_id}")
def post_resume_link(resume_id: str, job_id: str) -> dict[str, Any]:
    return _found(resumes.link_to_job(resume_id, job_id), "Resume")


# --------------------------------------------------------------------------
# dsa
# --------------------------------------------------------------------------


class ProblemIn(BaseModel):
    title: str
    platform: str = "leetcode"
    url: str | None = None
    difficulty: str = "medium"
    topics: list[str] = Field(default_factory=list)
    status: str = "todo"
    date_started: str | None = None
    date_completed: str | None = None
    time_spent_minutes: int | None = None
    attempts: int = 0
    used_hint: bool = False
    solution_notes: str = ""
    confidence: int | None = None
    company_tags: list[str] = Field(default_factory=list)
    linked_job_id: str | None = None


class ProblemPatch(BaseModel):
    title: str | None = None
    platform: str | None = None
    url: str | None = None
    difficulty: str | None = None
    topics: list[str] | None = None
    status: str | None = None
    date_started: str | None = None
    date_completed: str | None = None
    time_spent_minutes: int | None = None
    attempts: int | None = None
    used_hint: bool | None = None
    solution_notes: str | None = None
    confidence: int | None = None
    company_tags: list[str] | None = None
    linked_job_id: str | None = None


class IssueIn(BaseModel):
    issue: str
    date: str | None = None


class RevisitIn(BaseModel):
    outcome: str = ""
    confidence: int | None = None
    date: str | None = None


@app.get("/api/dsa")
def get_problems() -> list[dict[str, Any]]:
    return dsa.list_problems()


@app.post("/api/dsa", status_code=201)
def post_problem(payload: ProblemIn) -> dict[str, Any]:
    return dsa.create_problem(payload.model_dump())


@app.get("/api/dsa/stats")
def get_dsa_stats() -> dict[str, Any]:
    return dsa.stats()


@app.get("/api/dsa/revision-queue")
def get_dsa_revision_queue() -> list[dict[str, Any]]:
    return dsa.revision_queue()


@app.get("/api/dsa/{problem_id}")
def get_one_problem(problem_id: str) -> dict[str, Any]:
    return _found(dsa.get_problem(problem_id), "Problem")


@app.patch("/api/dsa/{problem_id}")
def patch_problem(problem_id: str, payload: ProblemPatch) -> dict[str, Any]:
    return _found(
        dsa.update_problem(problem_id, payload.model_dump(exclude_unset=True)), "Problem"
    )


@app.delete("/api/dsa/{problem_id}", status_code=204)
def remove_problem(problem_id: str) -> None:
    if not dsa.delete_problem(problem_id):
        raise HTTPException(404, "Problem not found")


@app.post("/api/dsa/{problem_id}/issue")
def post_dsa_issue(problem_id: str, payload: IssueIn) -> dict[str, Any]:
    return _found(dsa.log_issue(problem_id, payload.issue, payload.date), "Problem")


@app.post("/api/dsa/{problem_id}/revisit")
def post_dsa_revisit(problem_id: str, payload: RevisitIn) -> dict[str, Any]:
    return _found(
        dsa.log_revisit(problem_id, payload.outcome, payload.confidence, payload.date),
        "Problem",
    )


# --------------------------------------------------------------------------
# system design
# --------------------------------------------------------------------------


class DesignIn(BaseModel):
    title: str
    kind: str = "hld"
    source: str | None = None
    url: str | None = None
    status: str = "todo"
    date_started: str | None = None
    date_completed: str | None = None
    time_spent_minutes: int | None = None
    concepts: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    tradeoffs: str = ""
    notes: str = ""
    confidence: int | None = None
    company_tags: list[str] = Field(default_factory=list)
    linked_job_id: str | None = None


class DesignPatch(BaseModel):
    title: str | None = None
    kind: str | None = None
    source: str | None = None
    url: str | None = None
    status: str | None = None
    date_started: str | None = None
    date_completed: str | None = None
    time_spent_minutes: int | None = None
    concepts: list[str] | None = None
    components: list[str] | None = None
    patterns: list[str] | None = None
    tradeoffs: str | None = None
    notes: str | None = None
    confidence: int | None = None
    company_tags: list[str] | None = None
    linked_job_id: str | None = None


class ArtifactIn(BaseModel):
    type: str = "other"
    path_or_url: str = ""
    note: str = ""


@app.get("/api/design")
def get_design_topics() -> list[dict[str, Any]]:
    return design.list_topics()


@app.post("/api/design", status_code=201)
def post_design_topic(payload: DesignIn) -> dict[str, Any]:
    return design.create_topic(payload.model_dump())


@app.get("/api/design/stats")
def get_design_stats() -> dict[str, Any]:
    return design.stats()


@app.get("/api/design/revision-queue")
def get_design_revision_queue() -> list[dict[str, Any]]:
    return design.revision_queue()


@app.get("/api/design/{topic_id}")
def get_one_design_topic(topic_id: str) -> dict[str, Any]:
    return _found(design.get_topic(topic_id), "Topic")


@app.patch("/api/design/{topic_id}")
def patch_design_topic(topic_id: str, payload: DesignPatch) -> dict[str, Any]:
    return _found(
        design.update_topic(topic_id, payload.model_dump(exclude_unset=True)), "Topic"
    )


@app.delete("/api/design/{topic_id}", status_code=204)
def remove_design_topic(topic_id: str) -> None:
    if not design.delete_topic(topic_id):
        raise HTTPException(404, "Topic not found")


@app.post("/api/design/{topic_id}/issue")
def post_design_issue(topic_id: str, payload: IssueIn) -> dict[str, Any]:
    return _found(design.log_issue(topic_id, payload.issue, payload.date), "Topic")


@app.post("/api/design/{topic_id}/revisit")
def post_design_revisit(topic_id: str, payload: RevisitIn) -> dict[str, Any]:
    return _found(
        design.log_revisit(topic_id, payload.outcome, payload.confidence, payload.date),
        "Topic",
    )


@app.post("/api/design/{topic_id}/artifact")
def post_design_artifact(topic_id: str, payload: ArtifactIn) -> dict[str, Any]:
    return _found(design.add_artifact(topic_id, payload.model_dump()), "Topic")


# --------------------------------------------------------------------------
# meta + overview
# --------------------------------------------------------------------------


@app.get("/api/meta")
def get_meta() -> dict[str, Any]:
    """Enum values the frontend renders as dropdowns."""
    return {
        "statuses": storage.STATUSES,
        "company_types": storage.COMPANY_TYPES,
        "contact_roles": storage.CONTACT_ROLES,
        "round_results": storage.ROUND_RESULTS,
        "sources": storage.SOURCES,
        "dsa_platforms": dsa.PLATFORMS,
        "dsa_difficulties": dsa.DIFFICULTIES,
        "dsa_statuses": dsa.DSA_STATUSES,
        "design_kinds": design.KINDS,
        "design_statuses": design.DESIGN_STATUSES,
        "artifact_types": design.ARTIFACT_TYPES,
    }


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    """One call for the whole dashboard header."""
    return {
        "jobs": storage.stats(),
        "dsa": dsa.stats(),
        "design": design.stats(),
        "resumes": resumes.stats(),
        "followups_due": len(storage.followup_suggestions()),
    }


# --------------------------------------------------------------------------
# AI chat
# --------------------------------------------------------------------------


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None


@app.get("/api/chat/health")
def chat_health() -> dict[str, Any]:
    import ai

    return ai.health()


@app.post("/api/chat")
async def post_chat(payload: ChatIn) -> StreamingResponse:
    import ai

    return StreamingResponse(
        ai.stream_chat(payload.message, payload.session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
