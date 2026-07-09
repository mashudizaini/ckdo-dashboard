"""
Job Description Generator
Takes a raw job description and produces a structured, HR-friendly version
plus ready-to-use CV screening criteria.

Ported from sumber/cv_screening (jd_generator_template.py + AI method in
app_cv_screening_bp.py) into the FastAPI stack.
"""
import json
import re

import anthropic

from app.config import get_settings

settings = get_settings()


# ── AI-Powered (Claude) ──────────────────────────────────────────────

def _build_prompt(original_jd: str) -> str:
    return f"""You are an expert HR consultant specializing in writing clear, comprehensive job descriptions.

**Original Job Description:**
{original_jd}

---

**Your Task:**
Analyze this job description and create an IMPROVED, STRUCTURED version that is:
1. **Clear & Comprehensive** - Easy for non-technical HR to understand
2. **Well-Structured** - Organized into clear sections
3. **Specific & Measurable** - Concrete requirements, not vague terms
4. **Complete** - Include all necessary information for effective CV screening

**Return a JSON response with this EXACT structure:**

```json
{{
  "improved_jd": {{
    "position_title": "Clear, specific job title",
    "overview": "2-3 sentence summary of the role",
    "key_responsibilities": ["Responsibility 1", "Responsibility 2", "Responsibility 3"],
    "required_qualifications": {{
      "education": "Specific degree requirements (e.g., Bachelor in Computer Science)",
      "experience": "X years in specific field/industry",
      "technical_skills": ["Must-have skill 1", "Must-have skill 2", "Must-have skill 3"],
      "soft_skills": ["Communication", "Teamwork", "Problem-solving"],
      "certifications": ["Required certification 1", "Required certification 2"]
    }},
    "preferred_qualifications": {{
      "experience": "Additional preferred experience",
      "skills": ["Nice-to-have skill 1", "Nice-to-have skill 2"],
      "certifications": ["Preferred certification 1"]
    }},
    "screening_criteria": {{
      "position_title": "Job title for screening system",
      "required_skills": ["Skill1", "Skill2", "Skill3"],
      "min_experience": 3,
      "education_keywords": ["Bachelor", "Computer Science"],
      "certification_keywords": ["OCP", "Certified"]
    }}
  }},
  "improvements_made": ["What was improved/clarified", "What was added", "What was restructured"],
  "hr_notes": "Tips for HR when reviewing CVs based on this JD"
}}
```

**Important Guidelines:**
- Be specific: "5 years experience in pharmaceutical industry" NOT "experienced"
- Separate must-have from nice-to-have
- Make it easy for non-technical HR to understand technical requirements
- Provide clear screening criteria that can be used in CV screening system
- Return ONLY valid JSON, no extra text"""


def generate_jd_with_ai(original_jd: str) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = _build_prompt(original_jd)

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    result = json.loads(raw)
    result["improvements_made"] = result.get("improvements_made", [])
    result["hr_notes"] = result.get("hr_notes", "")
    return result


# ── Template-Based (free, no API required) ───────────────────────────

def generate_jd_template_based(original_jd: str) -> dict:
    lines = [line.strip() for line in original_jd.split("\n") if line.strip()]
    jd_lower = original_jd.lower()

    position_title = _extract_position_title(lines)
    experience_years = _extract_experience_years(original_jd)
    education_requirement = _extract_education(lines, jd_lower)
    technical_skills, soft_skills = _extract_skills(jd_lower)
    certifications_list = _extract_certifications(lines)
    responsibilities = _extract_responsibilities(lines)

    return {
        "improved_jd": {
            "position_title": position_title,
            "overview": f"We are seeking a qualified {position_title} to join our team. The ideal candidate will have {experience_years}+ years of relevant experience and strong expertise in required skills.",
            "key_responsibilities": responsibilities,
            "required_qualifications": {
                "education": education_requirement,
                "experience": f"Minimum {experience_years} years of relevant experience",
                "technical_skills": technical_skills,
                "soft_skills": soft_skills,
                "certifications": certifications_list,
            },
            "preferred_qualifications": {
                "experience": f"{experience_years + 1}+ years with proven track record",
                "skills": [f"Advanced {skill}" for skill in technical_skills[:2]] if technical_skills else ["Additional industry experience"],
                "certifications": ["Professional certifications in related field"],
            },
            "screening_criteria": {
                "position_title": position_title,
                "required_skills": technical_skills,
                "min_experience": experience_years,
                "education_keywords": [education_requirement],
                "certification_keywords": certifications_list,
            },
        },
        "improvements_made": [
            "Structured the job description into clear sections",
            "Extracted and organized requirements systematically",
            "Separated technical skills from soft skills",
            f"Identified minimum experience requirement: {experience_years} years",
            "Created screening criteria for CV evaluation",
            "Used template-based extraction (no AI required)",
        ],
        "hr_notes": f"Focus on candidates with {experience_years}+ years of experience and relevant technical skills. Verify education credentials and look for practical experience in the required areas. Note: This JD was generated using template-based extraction for quick structuring.",
    }


def _extract_position_title(lines: list) -> str:
    position_title = "Position Not Specified"
    for line in lines[:5]:
        if any(keyword in line.lower() for keyword in ["position:", "title:", "role:", "job:", "vacancy:"]):
            position_title = line.split(":", 1)[-1].strip()
            break
        elif len(line.split()) <= 5 and len(line) < 50 and len(line.split()) > 1:
            position_title = line
            break
    return position_title


def _extract_experience_years(original_jd: str) -> int:
    exp_patterns = [
        r"(\d+)\+?\s*(?:years?|tahun)",
        r"minimum\s*(\d+)",
        r"at least\s*(\d+)",
        r"(\d+)\s*years?\s*(?:of\s*)?(?:experience|pengalaman)",
    ]
    for pattern in exp_patterns:
        matches = re.findall(pattern, original_jd.lower())
        if matches:
            return int(matches[0])
    return 2


def _extract_education(lines: list, jd_lower: str) -> str:
    education_patterns = {
        "s3": "S3 (Doctoral degree)", "phd": "PhD", "doktor": "Doctoral degree",
        "s2": "S2 (Master degree)", "master": "Master's degree", "magister": "Magister",
        "s1": "S1 (Bachelor degree)", "bachelor": "Bachelor's degree", "sarjana": "Sarjana",
        "d4": "D4", "d3": "D3 (Diploma)", "diploma": "Diploma",
    }
    for pattern, name in education_patterns.items():
        if pattern in jd_lower:
            for line in lines:
                if pattern in line.lower():
                    return line
            return name
    return "Bachelor's degree or equivalent"


def _extract_skills(jd_lower: str):
    tech_skills_db = {
        "python": "Python", "java": "Java", "javascript": "JavaScript", "c++": "C++",
        "php": "PHP", "ruby": "Ruby", "go": "Go", "rust": "Rust",
        "sql": "SQL", "mysql": "MySQL", "postgresql": "PostgreSQL", "mongodb": "MongoDB",
        "oracle": "Oracle", "database": "Database Management",
        "sap": "SAP", "oracle ebs": "Oracle EBS", "ebs": "EBS",
        "peoplesoft": "PeopleSoft", "dynamics": "Dynamics",
        "gmp": "GMP", "cgmp": "cGMP", "validation": "Validation",
        "qualification": "Qualification", "fda": "FDA", "iso": "ISO", "haccp": "HACCP",
        "excel": "Excel", "powerpoint": "PowerPoint", "word": "Word",
        "tableau": "Tableau", "power bi": "Power BI",
        "project management": "Project Management", "data analysis": "Data Analysis",
        "reporting": "Reporting", "documentation": "Documentation",
    }
    soft_skills_db = {
        "communication": "Communication", "teamwork": "Teamwork", "leadership": "Leadership",
        "problem solving": "Problem-solving", "analytical": "Analytical thinking",
        "detail oriented": "Detail-oriented", "time management": "Time management",
        "adaptability": "Adaptability", "collaboration": "Collaboration",
    }

    technical_skills = [name for kw, name in tech_skills_db.items() if kw in jd_lower]
    soft_skills = [name for kw, name in soft_skills_db.items() if kw in jd_lower]

    if not technical_skills:
        technical_skills = ["Industry-specific technical skills", "Computer proficiency"]
    if not soft_skills:
        soft_skills = ["Communication", "Teamwork", "Problem-solving"]

    return technical_skills, soft_skills


def _extract_certifications(lines: list) -> list:
    cert_keywords = ["certified", "certification", "certificate", "license",
                      "ocp", "pmp", "asq", "cissp", "aws", "azure", "gcp"]
    certifications = []
    for line in lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in cert_keywords) and line not in certifications:
            certifications.append(line)
    return certifications[:3]


def _extract_responsibilities(lines: list) -> list:
    action_verbs = ["manage", "develop", "lead", "coordinate", "ensure", "maintain",
                     "implement", "analyze", "prepare", "review", "monitor", "support",
                     "collaborate", "conduct", "perform", "oversee", "create", "design",
                     "execute", "supervise", "optimize", "facilitate"]
    responsibilities = []
    for line in lines:
        line_lower = line.lower()
        if any(verb in line_lower for verb in action_verbs) and len(line.split()) > 3:
            cleaned = line.lstrip("-•*").strip()
            if cleaned and len(cleaned) > 10:
                responsibilities.append(cleaned)
                if len(responsibilities) >= 6:
                    break

    if len(responsibilities) < 3:
        responsibilities = [
            "Perform duties as specified in the job description",
            "Collaborate with team members and stakeholders",
            "Maintain accurate documentation and reports",
            "Ensure quality and compliance with standards",
            "Support continuous improvement initiatives",
        ]
    return responsibilities[:6]
