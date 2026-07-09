"""
HR CV Screening Router
Route prefix: /api/v1/dashboard/hr/cv-screening

Upload candidate CVs (PDF/DOCX/TXT) for a job position → Claude AI analyzes
each CV against the position's requirements → structured score + recommendation.
"""
import io
import json
import os
from datetime import datetime
from typing import Optional, List

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_role, CurrentUser, Roles
from app.models.cv_screening import CvScreeningJob, CvScreeningCandidate
from app.services import cv_screening_service as svc
from app.services import jd_generator_service as jd_svc

router = APIRouter()

ALLOWED_EXT = (".pdf", ".docx", ".doc", ".txt")


class JobCreate(BaseModel):
    position_title: str
    required_skills: List[str] = []
    min_experience: int = 0
    education_keywords: List[str] = []
    certification_keywords: List[str] = []
    weight_skills: int = 40
    weight_experience: int = 30
    weight_education: int = 20
    weight_certification: int = 10


def _job_to_dict(j: CvScreeningJob) -> dict:
    return {
        "id": j.id,
        "position_title": j.position_title,
        "required_skills": json.loads(j.required_skills or "[]"),
        "min_experience": j.min_experience,
        "education_keywords": json.loads(j.education_keywords or "[]"),
        "certification_keywords": json.loads(j.certification_keywords or "[]"),
        "weight_skills": j.weight_skills,
        "weight_experience": j.weight_experience,
        "weight_education": j.weight_education,
        "weight_certification": j.weight_certification,
        "created_by": j.created_by,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


def _job_to_config(j: CvScreeningJob) -> dict:
    d = _job_to_dict(j)
    return d


def _candidate_to_dict(c: CvScreeningCandidate) -> dict:
    return {
        "id": c.id,
        "job_id": c.job_id,
        "filename": c.filename,
        "name": c.name,
        "email": c.email,
        "phone": c.phone,
        "education": c.education,
        "experience_years": c.experience_years,
        "total_experience_years": c.total_experience_years,
        "positions": json.loads(c.positions or "[]"),
        "skills_found": json.loads(c.skills_found or "[]"),
        "missing_skills": json.loads(c.missing_skills or "[]"),
        "additional_relevant_skills": json.loads(c.additional_relevant_skills or "[]"),
        "certifications": json.loads(c.certifications or "[]"),
        "skills_score": c.skills_score,
        "experience_score": c.experience_score,
        "education_score": c.education_score,
        "certification_score": c.certification_score,
        "total_score": c.total_score,
        "recommendation": c.recommendation,
        "confidence": c.confidence,
        "reasoning": c.reasoning,
        "interview_focus": json.loads(c.interview_focus or "[]"),
        "red_flags": json.loads(c.red_flags or "[]"),
        "strengths": json.loads(c.strengths or "[]"),
        "error": c.error,
        "screened_at": c.screened_at.isoformat() if c.screened_at else None,
    }


# ── Job Config CRUD ────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(CvScreeningJob).order_by(CvScreeningJob.created_at.desc()))
    return [_job_to_dict(j) for j in result.scalars().all()]


@router.post("/jobs")
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    if not body.position_title.strip():
        raise HTTPException(400, "Position title is required")
    j = CvScreeningJob(
        position_title=body.position_title.strip(),
        required_skills=json.dumps(body.required_skills),
        min_experience=body.min_experience,
        education_keywords=json.dumps(body.education_keywords),
        certification_keywords=json.dumps(body.certification_keywords),
        weight_skills=body.weight_skills,
        weight_experience=body.weight_experience,
        weight_education=body.weight_education,
        weight_certification=body.weight_certification,
        created_by=user.username,
    )
    db.add(j)
    await db.flush()
    return _job_to_dict(j)


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(CvScreeningJob).where(CvScreeningJob.id == job_id))
    j = result.scalars().first()
    if not j:
        raise HTTPException(404, "Job not found")
    await db.delete(j)
    return {"message": "Deleted"}


# ── Upload & Screen ─────────────────────────────────────────────────

@router.post("/jobs/{job_id}/upload")
async def upload_and_screen(
    job_id: int,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(CvScreeningJob).where(CvScreeningJob.id == job_id))
    job_row = result.scalars().first()
    if not job_row:
        raise HTTPException(404, "Job not found")
    job = _job_to_config(job_row)

    if not job["required_skills"]:
        raise HTTPException(400, "Job has no required skills configured")

    candidates = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            continue

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        safe_name = f"{timestamp}_{f.filename}"
        file_path = os.path.join(svc.UPLOAD_DIR, safe_name)
        content = await f.read()
        with open(file_path, "wb") as out:
            out.write(content)

        try:
            data = svc.screen_cv(file_path, f.filename, job)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

        c = CvScreeningCandidate(job_id=job_id, **data)
        db.add(c)
        candidates.append(c)

    if not candidates:
        raise HTTPException(400, f"No valid CV files uploaded. Allowed: {', '.join(ALLOWED_EXT)}")

    await db.flush()
    candidates.sort(key=lambda c: c.total_score, reverse=True)
    return {"count": len(candidates), "candidates": [_candidate_to_dict(c) for c in candidates]}


# ── Candidates ───────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/candidates")
async def list_candidates(
    job_id: int,
    recommendation: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    q = select(CvScreeningCandidate).where(CvScreeningCandidate.job_id == job_id)
    if recommendation:
        q = q.where(CvScreeningCandidate.recommendation == recommendation)
    if search:
        pat = f"%{search}%"
        q = q.where(CvScreeningCandidate.name.ilike(pat) | CvScreeningCandidate.email.ilike(pat))
    q = q.order_by(CvScreeningCandidate.total_score.desc())
    result = await db.execute(q)
    return [_candidate_to_dict(c) for c in result.scalars().all()]


@router.delete("/candidates/{candidate_id}")
async def delete_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(CvScreeningCandidate).where(CvScreeningCandidate.id == candidate_id))
    c = result.scalars().first()
    if not c:
        raise HTTPException(404, "Candidate not found")
    await db.delete(c)
    return {"message": "Deleted"}


@router.get("/jobs/{job_id}/stats")
async def get_stats(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    result = await db.execute(select(CvScreeningCandidate).where(CvScreeningCandidate.job_id == job_id))
    candidates = result.scalars().all()
    total = len(candidates)
    by_rec = {}
    for c in candidates:
        by_rec[c.recommendation] = by_rec.get(c.recommendation, 0) + 1
    scores = [c.total_score for c in candidates if c.recommendation != "Error Processing"]
    return {
        "total": total,
        "highly_recommended": by_rec.get("Highly Recommended", 0),
        "recommended": by_rec.get("Recommended", 0),
        "consider": by_rec.get("Consider", 0),
        "not_recommended": by_rec.get("Not Recommended", 0),
        "errors": by_rec.get("Error Processing", 0),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
    }


# ── Job Description Generator ──────────────────────────────────────

class JdGenerateRequest(BaseModel):
    jd_text: str
    method: str = "template"  # "ai" or "template"


@router.post("/jd/upload")
async def upload_jd(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"File type not supported. Allowed: {', '.join(ALLOWED_EXT)}")

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    file_path = os.path.join(svc.UPLOAD_DIR, f"jd_{timestamp}_{file.filename}")
    content = await file.read()
    with open(file_path, "wb") as out:
        out.write(content)

    try:
        jd_text = svc.extract_cv_text(file_path)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    return {"filename": file.filename, "text": jd_text, "length": len(jd_text)}


@router.post("/jd/generate")
async def generate_jd(
    body: JdGenerateRequest,
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    if not body.jd_text.strip():
        raise HTTPException(400, "No job description text provided")

    if body.method == "ai":
        result = jd_svc.generate_jd_with_ai(body.jd_text)
    elif body.method == "template":
        result = jd_svc.generate_jd_template_based(body.jd_text)
    else:
        raise HTTPException(400, f'Invalid method: {body.method}. Use "ai" or "template"')

    return {"result": result, "method": body.method}


# ── Export ──────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/export")
async def export_excel(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_role(Roles.HR)),
):
    job_result = await db.execute(select(CvScreeningJob).where(CvScreeningJob.id == job_id))
    job_row = job_result.scalars().first()
    if not job_row:
        raise HTTPException(404, "Job not found")

    result = await db.execute(
        select(CvScreeningCandidate).where(CvScreeningCandidate.job_id == job_id)
        .order_by(CvScreeningCandidate.total_score.desc())
    )
    candidates = result.scalars().all()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Screening Results"
    headers = ["Name", "Email", "Phone", "Total Score", "Recommendation", "Confidence",
               "Relevant Exp (yrs)", "Total Exp (yrs)", "Education", "Skills Found",
               "Missing Skills", "Skills Score", "Experience Score", "Education Score",
               "Certification Score", "Filename", "Screened At"]
    ws.append(headers)
    for c in candidates:
        ws.append([
            c.name, c.email, c.phone, c.total_score, c.recommendation, c.confidence,
            c.experience_years, c.total_experience_years, c.education,
            ", ".join(json.loads(c.skills_found or "[]")),
            ", ".join(json.loads(c.missing_skills or "[]")),
            c.skills_score, c.experience_score, c.education_score, c.certification_score,
            c.filename, c.screened_at.strftime("%Y-%m-%d %H:%M:%S") if c.screened_at else "",
        ])

    for col in ws.columns:
        max_len = max((len(str(cell.value)) for cell in col if cell.value), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    safe_title = "".join(c for c in job_row.position_title if c.isalnum() or c in (" ", "-", "_")).strip()
    filename = f"cv_screening_{safe_title}_{datetime.utcnow().strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
