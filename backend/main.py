"""FastAPI app for the personal job tracker.

Local-only: no auth, CORS open for localhost. Domains — applications, the
company board, DSA practice, system design, resumes and the prep profile —
plus an AI chat endpoint (ai.py) that writes through the same storage modules
as these REST endpoints.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import companies
import company_seed
import design
import discover
import docx_export
import dsa
import latex_export
import pdf_export
import prep
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
    found_via: str | None = None
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
    found_via: str | None = None
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
    latex_content: str = ""
    is_latex_template: bool = False
    target_role: str | None = None
    is_master: bool = False
    notes: str = ""


class ResumePatch(BaseModel):
    name: str | None = None
    version_label: str | None = None
    based_on: str | None = None
    file_path: str | None = None
    content: str | None = None
    latex_content: str | None = None
    is_latex_template: bool | None = None
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


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@app.get("/api/latex/status")
def latex_status() -> dict[str, Any]:
    """Whether a TeX engine is installed, so the UI can explain a missing PDF."""
    return pdf_export.available()


@app.get("/api/resumes/{resume_id}/download")
def download_resume(resume_id: str, format: str = "pdf") -> Response:
    """Download a resume version as PDF, Word, or LaTeX source."""
    resume = _found(resumes.get_resume(resume_id), "Resume")

    if format == "pdf":
        latex = resume.get("latex_content") or ""
        if not latex.strip():
            raise HTTPException(
                400,
                "This version has no LaTeX source, so there's nothing to compile. "
                "Add LaTeX to it, or download the Word version instead.",
            )
        try:
            data = pdf_export.compile_pdf(latex)
        except pdf_export.LatexNotInstalled as exc:
            raise HTTPException(503, str(exc)) from exc
        except pdf_export.LatexCompileError as exc:
            raise HTTPException(400, f"LaTeX error: {exc}") from exc
        person = docx_export.parse(resume.get("content", ""))["name"]
        name = latex_export.filename_for(resume, person).removesuffix(".tex") + ".pdf"
        return Response(
            content=data,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    if format == "tex":
        latex = resume.get("latex_content") or ""
        if not latex.strip():
            raise HTTPException(
                400,
                "This version has no LaTeX source. Ask the assistant to generate a "
                "LaTeX version, or paste one in.",
            )
        # Served verbatim — the user's .tex must round-trip byte for byte.
        person = docx_export.parse(resume.get("content", ""))["name"]
        return Response(
            content=latex,
            media_type="application/x-tex",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{latex_export.filename_for(resume, person)}"'
                )
            },
        )

    if format != "docx":
        raise HTTPException(400, "format must be 'pdf', 'docx' or 'tex'")

    if not (resume.get("content") or "").strip():
        raise HTTPException(
            400, "This version has no resume text yet, so there is nothing to export."
        )
    return Response(
        content=docx_export.build(resume),
        media_type=DOCX_MIME,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{docx_export.filename_for(resume)}"'
            )
        },
    )


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
    time_complexity: str = ""
    space_complexity: str = ""
    phase: str | None = None
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
    time_complexity: str | None = None
    space_complexity: str | None = None
    phase: str | None = None
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


class TimerIn(BaseModel):
    action: str  # start | pause | reset


class DeferIn(BaseModel):
    reason: str
    # Problem ids that must reach a solved status before this resurfaces. The
    # gate is what separates a deferral from "I'll get back to it".
    until_solved: list[str] = Field(default_factory=list)
    review_on: str | None = None


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


@app.get("/api/dsa/missing-complexity")
def get_dsa_missing_complexity() -> list[dict[str, Any]]:
    return dsa.missing_complexity()


# Declared before /api/dsa/{problem_id} on purpose — routes match in order, and
# the wildcard would otherwise swallow these as problem_id="next-up"/"coach".
@app.get("/api/dsa/next-up")
def get_dsa_next_up(limit: int = dsa.NEXT_UP_LIMIT) -> list[dict[str, Any]]:
    return dsa.next_up(limit)


@app.get("/api/dsa/coach")
def get_dsa_coach() -> dict[str, Any]:
    return dsa.coach()


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


@app.post("/api/dsa/{problem_id}/timer")
def post_dsa_timer(problem_id: str, payload: TimerIn) -> dict[str, Any]:
    try:
        problem = dsa.set_timer(problem_id, payload.action)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _found(problem, "Problem")


@app.post("/api/dsa/{problem_id}/defer")
def post_dsa_defer(problem_id: str, payload: DeferIn) -> dict[str, Any]:
    return _found(
        dsa.defer_problem(problem_id, payload.reason, payload.until_solved, payload.review_on),
        "Problem",
    )


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
# interview prep profile
# --------------------------------------------------------------------------


class ProfilePatch(BaseModel):
    target_levels: list[str] | None = None
    target_companies: list[str] | None = None
    current_phase: str | None = None
    current_milestone: str | None = None
    notes: str | None = None


class PhaseIn(BaseModel):
    key: str
    name: str
    status: str = "upcoming"
    order: int = 0
    topics: list[str] = Field(default_factory=list)
    milestone: str = ""


class PhaseStatusIn(BaseModel):
    status: Literal["completed", "current", "upcoming"]


class MilestoneIn(BaseModel):
    milestone: str
    phase_key: str | None = None


class StandingIssueIn(BaseModel):
    issue: str
    category: str = "logic"
    date: str | None = None


class FlagIssueIn(BaseModel):
    date: str | None = None
    problem_id: str | None = None


@app.get("/api/prep")
def get_prep() -> dict[str, Any]:
    return prep.get_prep()


@app.get("/api/prep/stats")
def get_prep_stats() -> dict[str, Any]:
    return prep.stats()


@app.get("/api/prep/readiness")
def get_readiness() -> dict[str, Any]:
    """Cross-domain: scheduled rounds vs. what's still shaky."""
    return prep.readiness()


@app.patch("/api/prep/profile")
def patch_profile(payload: ProfilePatch) -> dict[str, Any]:
    return prep.update_profile(payload.model_dump(exclude_unset=True))


@app.post("/api/prep/phases")
def post_phase(payload: PhaseIn) -> dict[str, Any]:
    return prep.upsert_phase(payload.model_dump())


@app.patch("/api/prep/phases/{phase_key}")
def patch_phase_status(phase_key: str, payload: PhaseStatusIn) -> dict[str, Any]:
    return _found(prep.set_phase_status(phase_key, payload.status), "Phase")


@app.post("/api/prep/milestone")
def post_milestone(payload: MilestoneIn) -> dict[str, Any]:
    return prep.set_milestone(payload.milestone, payload.phase_key)


@app.get("/api/prep/standing-issues")
def get_standing_issues(active_only: bool = False) -> list[dict[str, Any]]:
    return prep.list_standing_issues(active_only)


@app.post("/api/prep/standing-issues", status_code=201)
def post_standing_issue(payload: StandingIssueIn) -> dict[str, Any]:
    try:
        return prep.add_standing_issue(payload.issue, payload.category, payload.date)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/prep/standing-issues/{issue_id}/flag")
def post_flag_issue(issue_id: str, payload: FlagIssueIn) -> dict[str, Any]:
    return _found(
        prep.flag_standing_issue(issue_id, payload.date, payload.problem_id),
        "Standing issue",
    )


@app.post("/api/prep/standing-issues/{issue_id}/resolve")
def post_resolve_issue(issue_id: str) -> dict[str, Any]:
    return _found(prep.resolve_standing_issue(issue_id), "Standing issue")


@app.delete("/api/prep/standing-issues/{issue_id}", status_code=204)
def remove_standing_issue(issue_id: str) -> None:
    if not prep.delete_standing_issue(issue_id):
        raise HTTPException(404, "Standing issue not found")


# --------------------------------------------------------------------------
# company board
# --------------------------------------------------------------------------


class CompanyIn(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str = "product"
    tier: str | None = None
    hq: str | None = None
    locations: list[str] = Field(default_factory=list)
    website: str | None = None
    careers_url: str | None = None
    ats_provider: str = "none"
    ats_token: str | None = None
    focus: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    org_summary: str | None = None
    interest: int | None = None
    status: str = "researching"
    notes: str = ""


class CompanyPatch(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    category: str | None = None
    tier: str | None = None
    hq: str | None = None
    locations: list[str] | None = None
    website: str | None = None
    careers_url: str | None = None
    ats_provider: str | None = None
    ats_token: str | None = None
    focus: list[str] | None = None
    tech_stack: list[str] | None = None
    org_summary: str | None = None
    interest: int | None = None
    status: str | None = None
    notes: str | None = None


@app.get("/api/companies")
def get_companies(
    status: str | None = None,
    category: str | None = None,
    tier: str | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    return companies.list_companies(status=status, category=category, tier=tier, query=q)


@app.post("/api/companies", status_code=201)
def post_company(payload: CompanyIn) -> dict[str, Any]:
    try:
        return companies.create_company(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# Static segments must be declared before /{company_id} or the path parameter
# swallows them — the same ordering trap as /api/dsa/missing-complexity.
@app.get("/api/companies/stats")
def get_company_stats() -> dict[str, Any]:
    return companies.stats()


@app.get("/api/companies/target-gaps")
def get_target_gaps() -> list[dict[str, Any]]:
    """Companies marked as targets that you've never actually applied to."""
    return companies.target_gaps()


@app.post("/api/companies/seed")
def post_seed() -> dict[str, Any]:
    """Load the curated India board. Idempotent — re-running only adds what's new."""
    return companies.seed(company_seed.SEED)


@app.get("/api/companies/{company_id}")
def get_one_company(company_id: str) -> dict[str, Any]:
    return _found(companies.get_company(company_id), "Company")


@app.patch("/api/companies/{company_id}")
def patch_company(company_id: str, payload: CompanyPatch) -> dict[str, Any]:
    return _found(
        companies.update_company(company_id, payload.model_dump(exclude_unset=True)),
        "Company",
    )


@app.delete("/api/companies/{company_id}", status_code=204)
def remove_company(company_id: str) -> None:
    if not companies.delete_company(company_id):
        raise HTTPException(404, "Company not found")


# --------------------------------------------------------------------------
# role discovery
# --------------------------------------------------------------------------


class DiscoverIn(BaseModel):
    company_ids: list[str] | None = None
    keywords: list[str] = Field(default_factory=list)
    # None means "use the built-in defaults"; an empty list means "no filter".
    exclude_keywords: list[str] | None = None
    locations: list[str] | None = None
    include_remote: bool = False
    max_age_days: int | None = None
    exclude_seniority: list[str] = Field(default_factory=list)
    limit: int = 100
    include_description: bool = False
    force: bool = False


class PromoteIn(BaseModel):
    role: dict[str, Any]
    status: Status = "saved"


@app.get("/api/discover/providers")
def get_providers() -> dict[str, Any]:
    """Which boards are supported and how much of the board is wired up."""
    wired = companies.fetchable()
    by_provider: dict[str, int] = {p: 0 for p in discover.PROVIDERS}
    for company in wired:
        by_provider[company["ats_provider"]] = by_provider.get(company["ats_provider"], 0) + 1
    return {
        "providers": discover.PROVIDERS,
        "wired": len(wired),
        "by_provider": by_provider,
        "cache_ttl_seconds": discover.CACHE_TTL_SECONDS,
        "default_locations": list(discover.INDIA_TOKENS),
        "default_exclude_keywords": list(discover.NOISE_KEYWORDS),
    }


@app.post("/api/discover")
async def post_discover(payload: DiscoverIn) -> dict[str, Any]:
    """Check every wired job board and return roles that aren't tracked yet."""
    return await discover.search(
        company_ids=payload.company_ids,
        keywords=payload.keywords,
        exclude_keywords=(
            discover.NOISE_KEYWORDS
            if payload.exclude_keywords is None
            else payload.exclude_keywords
        ),
        locations=(
            discover.INDIA_TOKENS if payload.locations is None else payload.locations
        ),
        include_remote=payload.include_remote,
        max_age_days=payload.max_age_days,
        exclude_seniority=payload.exclude_seniority,
        limit=payload.limit,
        include_description=payload.include_description,
        force=payload.force,
    )


@app.post("/api/discover/promote", status_code=201)
def post_promote(payload: PromoteIn) -> dict[str, Any]:
    """Turn a discovered role into a tracked application record."""
    if not payload.role.get("title") or not payload.role.get("company"):
        raise HTTPException(400, "A role needs at least a title and a company.")
    return storage.create_job(discover.to_job(payload.role, payload.status))


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
        "phase_statuses": prep.PHASE_STATUSES,
        "standing_issue_categories": prep.ISSUE_CATEGORIES,
        "company_statuses": companies.STATUSES,
        "company_tiers": companies.TIERS,
        "company_focus_areas": companies.FOCUS_AREAS,
        "ats_providers": [*discover.PROVIDERS, "none"],
        "seniority_levels": ["intern", "entry", "mid", "senior"],
    }


@app.get("/api/overview")
def get_overview() -> dict[str, Any]:
    """One call for the whole dashboard header."""
    return {
        "jobs": storage.stats(),
        "dsa": dsa.stats(),
        "design": design.stats(),
        "resumes": resumes.stats(),
        "prep": prep.stats(),
        "companies": companies.stats(),
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
