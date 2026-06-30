"""
CV Screening Service
Parse CV (PDF/DOCX/TXT) → analyze with Claude AI → structured score + recommendation.

Ported from sumber/cv_screening (AI-Enhanced screener) into the FastAPI stack.
"""
import os
import json
import re
from typing import Optional

import fitz  # PyMuPDF
import docx
import anthropic

from app.config import get_settings

settings = get_settings()

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "cv_screening")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ── Text Extraction ────────────────────────────────────────────────

def extract_cv_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        doc = fitz.open(file_path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    elif ext in (".docx", ".doc"):
        d = docx.Document(file_path)
        return "\n".join(p.text for p in d.paragraphs).strip()
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    else:
        raise ValueError(f"Unsupported file format: {ext}")


# ── AI Analysis ─────────────────────────────────────────────────────

def _build_prompt(cv_text: str, job: dict) -> str:
    return f"""You are an expert HR recruiter analyzing a CV for a job position.

**Job Position:** {job['position_title']}

**Job Requirements:**
- Required Skills: {', '.join(job['required_skills'])}
- Minimum Experience: {job.get('min_experience', 0)} years
- Education: {', '.join(job.get('education_keywords', []))}
- Certifications: {', '.join(job.get('certification_keywords', []))}

**Candidate CV:**
{cv_text[:12000]}

---

**Your Task:**
Analyze this CV deeply and extract structured information. Be smart about:
1. Only count RELEVANT work experience (not education, not unrelated jobs)
2. Assess skill proficiency level (beginner/intermediate/expert) based on context
3. Detect if candidate just "wants to learn" vs "has experience with"
4. Identify red flags (job hopping, employment gaps, skill mismatches)

**Return a JSON response with this EXACT structure:**

```json
{{
  "candidate_info": {{"name": "Full name", "email": "email@example.com or null", "phone": "phone number or null"}},
  "experience": {{"total_years": 5, "relevant_years": 3, "details": "Brief summary"}},
  "education": {{"highest_degree": "S1/S2/S3/Bachelor/Master/PhD", "major": "Computer Science", "matches_requirement": true}},
  "skills": {{
    "matched_skills": [{{"skill": "Python", "level": "expert", "evidence": "5 years Python development"}}],
    "missing_critical_skills": ["Skill1"]
  }},
  "red_flags": ["Job hopping (3 jobs in 2 years)"],
  "strengths": ["Strong technical background"],
  "scoring": {{
    "skills_score": 35, "experience_score": 25, "education_score": 18, "certification_score": 8,
    "total_score": 86, "reasoning": "Detailed explanation"
  }},
  "recommendation": {{
    "decision": "Highly Recommended / Recommended / Consider / Not Recommended",
    "confidence": "high / medium / low",
    "reasoning": "Detailed reasoning"
  }}
}}
```

Scoring weights to apply: skills={job.get('weight_skills', 40)}, experience={job.get('weight_experience', 30)}, education={job.get('weight_education', 20)}, certification={job.get('weight_certification', 10)}. The 4 scores must sum to total_score, each capped at its weight.

**Important:**
- Be strict: "want to learn Python" is NOT a Python skill
- Be context-aware: irrelevant past jobs should not inflate relevant_years
- Return ONLY valid JSON, no extra text"""


def analyze_cv_with_ai(cv_text: str, job: dict) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = _build_prompt(cv_text, job)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def screen_cv(file_path: str, filename: str, job: dict) -> dict:
    """Extract + analyze a single CV. Returns a dict matching CvScreeningCandidate fields."""
    try:
        cv_text = extract_cv_text(file_path)
        if not cv_text or len(cv_text) < 30:
            raise ValueError("Could not extract readable text from file")

        ai = analyze_cv_with_ai(cv_text, job)

        scoring = ai.get("scoring", {})
        rec = ai.get("recommendation", {})
        matched = ai.get("skills", {}).get("matched_skills", [])

        return {
            "filename": filename,
            "name": ai.get("candidate_info", {}).get("name") or "Unknown",
            "email": ai.get("candidate_info", {}).get("email"),
            "phone": ai.get("candidate_info", {}).get("phone"),
            "education": f"{ai.get('education', {}).get('highest_degree', '')} {ai.get('education', {}).get('major', '')}".strip() or "Not Found",
            "experience_years": int(ai.get("experience", {}).get("relevant_years", 0) or 0),
            "total_experience_years": int(ai.get("experience", {}).get("total_years", 0) or 0),
            "skills_found": json.dumps([s["skill"] for s in matched]),
            "missing_skills": json.dumps(ai.get("skills", {}).get("missing_critical_skills", [])),
            "skills_score": float(scoring.get("skills_score", 0) or 0),
            "experience_score": float(scoring.get("experience_score", 0) or 0),
            "education_score": float(scoring.get("education_score", 0) or 0),
            "certification_score": float(scoring.get("certification_score", 0) or 0),
            "total_score": float(scoring.get("total_score", 0) or 0),
            "recommendation": rec.get("decision", "Consider"),
            "confidence": rec.get("confidence"),
            "reasoning": rec.get("reasoning") or scoring.get("reasoning"),
            "red_flags": json.dumps(ai.get("red_flags", [])),
            "strengths": json.dumps(ai.get("strengths", [])),
            "error": None,
        }
    except Exception as e:
        return {
            "filename": filename,
            "name": "Unknown",
            "email": None, "phone": None, "education": None,
            "experience_years": 0, "total_experience_years": 0,
            "skills_found": "[]", "missing_skills": "[]",
            "skills_score": 0, "experience_score": 0, "education_score": 0, "certification_score": 0,
            "total_score": 0, "recommendation": "Error Processing",
            "confidence": None, "reasoning": None,
            "red_flags": "[]", "strengths": "[]",
            "error": str(e),
        }
