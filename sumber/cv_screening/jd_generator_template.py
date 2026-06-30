"""
JD Generator - Template-Based (Free, No API Required)
Extracts information from JD and structures it using templates
"""

import re


def generate_jd_template_based(original_jd):
    """
    Generate improved JD using template-based extraction

    No AI/API required - uses pattern matching and templates
    Free to use, good for basic JD improvement

    Args:
        original_jd: Original job description text

    Returns:
        dict: Structured JD in same format as AI version
    """

    # Split into lines
    lines = [line.strip() for line in original_jd.split('\n') if line.strip()]
    jd_lower = original_jd.lower()

    # =====================================
    # 1. EXTRACT POSITION TITLE
    # =====================================
    position_title = extract_position_title(lines)

    # =====================================
    # 2. EXTRACT EXPERIENCE YEARS
    # =====================================
    experience_years = extract_experience_years(original_jd)

    # =====================================
    # 3. EXTRACT EDUCATION
    # =====================================
    education_requirement = extract_education(lines, jd_lower)

    # =====================================
    # 4. EXTRACT SKILLS
    # =====================================
    technical_skills, soft_skills = extract_skills(jd_lower)

    # =====================================
    # 5. EXTRACT CERTIFICATIONS
    # =====================================
    certifications_list = extract_certifications(lines)

    # =====================================
    # 6. EXTRACT RESPONSIBILITIES
    # =====================================
    responsibilities = extract_responsibilities(lines)

    # =====================================
    # 7. BUILD STRUCTURED JD
    # =====================================
    result = {
        "improved_jd": {
            "position_title": position_title,
            "overview": f"We are seeking a qualified {position_title} to join our team. The ideal candidate will have {experience_years}+ years of relevant experience and strong expertise in required skills.",
            "key_responsibilities": responsibilities,
            "required_qualifications": {
                "education": education_requirement,
                "experience": f"Minimum {experience_years} years of relevant experience",
                "technical_skills": technical_skills,
                "soft_skills": soft_skills,
                "certifications": certifications_list
            },
            "preferred_qualifications": {
                "experience": f"{experience_years + 1}+ years with proven track record",
                "skills": [f"Advanced {skill}" for skill in technical_skills[:2]] if technical_skills else ["Additional industry experience"],
                "certifications": ["Professional certifications in related field"]
            },
            "screening_criteria": {
                "position_title": position_title,
                "required_skills": technical_skills,
                "min_experience": experience_years,
                "education_keywords": [education_requirement],
                "certification_keywords": certifications_list if certifications_list else []
            }
        },
        "improvements_made": [
            "Structured the job description into clear sections",
            "Extracted and organized requirements systematically",
            "Separated technical skills from soft skills",
            f"Identified minimum experience requirement: {experience_years} years",
            "Created screening criteria for CV evaluation",
            "Used template-based extraction (no AI required)"
        ],
        "hr_notes": f"Focus on candidates with {experience_years}+ years of experience and relevant technical skills. Verify education credentials and look for practical experience in the required areas. Note: This JD was generated using template-based extraction for quick structuring."
    }

    return result


def extract_position_title(lines):
    """Extract position title from JD"""
    position_title = "Position Not Specified"

    for line in lines[:5]:
        # Check for position indicators
        if any(keyword in line.lower() for keyword in ['position:', 'title:', 'role:', 'job:', 'vacancy:']):
            position_title = line.split(':', 1)[-1].strip()
            break
        # First short line might be title
        elif len(line.split()) <= 5 and len(line) < 50 and len(line.split()) > 1:
            position_title = line
            break

    return position_title


def extract_experience_years(original_jd):
    """Extract minimum experience years"""
    exp_patterns = [
        r'(\d+)\+?\s*(?:years?|tahun)',
        r'minimum\s*(\d+)',
        r'at least\s*(\d+)',
        r'(\d+)\s*years?\s*(?:of\s*)?(?:experience|pengalaman)'
    ]

    for pattern in exp_patterns:
        matches = re.findall(pattern, original_jd.lower())
        if matches:
            return int(matches[0])

    return 2  # Default


def extract_education(lines, jd_lower):
    """Extract education requirements"""
    education_patterns = {
        's3': 'S3 (Doctoral degree)',
        'phd': 'PhD',
        'doktor': 'Doctoral degree',
        's2': 'S2 (Master degree)',
        'master': "Master's degree",
        'magister': 'Magister',
        's1': 'S1 (Bachelor degree)',
        'bachelor': "Bachelor's degree",
        'sarjana': 'Sarjana',
        'd4': 'D4',
        'd3': 'D3 (Diploma)',
        'diploma': 'Diploma'
    }

    for pattern, name in education_patterns.items():
        if pattern in jd_lower:
            # Try to get full line for context
            for line in lines:
                if pattern in line.lower():
                    return line
            return name

    return "Bachelor's degree or equivalent"


def extract_skills(jd_lower):
    """Extract technical and soft skills"""
    # Common technical skills database
    tech_skills_db = {
        # Programming
        'python': 'Python', 'java': 'Java', 'javascript': 'JavaScript', 'c++': 'C++',
        'php': 'PHP', 'ruby': 'Ruby', 'go': 'Go', 'rust': 'Rust',

        # Databases
        'sql': 'SQL', 'mysql': 'MySQL', 'postgresql': 'PostgreSQL', 'mongodb': 'MongoDB',
        'oracle': 'Oracle', 'database': 'Database Management',

        # ERP/Systems
        'sap': 'SAP', 'oracle ebs': 'Oracle EBS', 'ebs': 'EBS',
        'peoplesoft': 'PeopleSoft', 'dynamics': 'Dynamics',

        # Pharmaceutical/Manufacturing
        'gmp': 'GMP', 'cgmp': 'cGMP', 'validation': 'Validation',
        'qualification': 'Qualification', 'fda': 'FDA',
        'iso': 'ISO', 'haccp': 'HACCP',

        # Tools
        'excel': 'Excel', 'powerpoint': 'PowerPoint', 'word': 'Word',
        'tableau': 'Tableau', 'power bi': 'Power BI',

        # Other
        'project management': 'Project Management', 'data analysis': 'Data Analysis',
        'reporting': 'Reporting', 'documentation': 'Documentation'
    }

    # Soft skills database
    soft_skills_db = {
        'communication': 'Communication',
        'teamwork': 'Teamwork',
        'leadership': 'Leadership',
        'problem solving': 'Problem-solving',
        'analytical': 'Analytical thinking',
        'detail oriented': 'Detail-oriented',
        'time management': 'Time management',
        'adaptability': 'Adaptability',
        'collaboration': 'Collaboration'
    }

    technical_skills = []
    soft_skills = []

    # Find technical skills
    for keyword, proper_name in tech_skills_db.items():
        if keyword in jd_lower:
            if proper_name not in technical_skills:
                technical_skills.append(proper_name)

    # Find soft skills
    for keyword, proper_name in soft_skills_db.items():
        if keyword in jd_lower:
            if proper_name not in soft_skills:
                soft_skills.append(proper_name)

    # Default values if nothing found
    if not technical_skills:
        technical_skills = ['Industry-specific technical skills', 'Computer proficiency']

    if not soft_skills:
        soft_skills = ['Communication', 'Teamwork', 'Problem-solving']

    return technical_skills, soft_skills


def extract_certifications(lines):
    """Extract certification requirements"""
    cert_keywords = ['certified', 'certification', 'certificate', 'license',
                     'ocp', 'pmp', 'asq', 'cissp', 'aws', 'azure', 'gcp']

    certifications = []
    for line in lines:
        line_lower = line.lower()
        for keyword in cert_keywords:
            if keyword in line_lower and line not in certifications:
                certifications.append(line)
                break

    return certifications[:3]  # Max 3


def extract_responsibilities(lines):
    """Extract job responsibilities"""
    action_verbs = ['manage', 'develop', 'lead', 'coordinate', 'ensure', 'maintain',
                    'implement', 'analyze', 'prepare', 'review', 'monitor', 'support',
                    'collaborate', 'conduct', 'perform', 'oversee', 'create', 'design',
                    'execute', 'supervise', 'optimize', 'facilitate']

    responsibilities = []
    for line in lines:
        line_lower = line.lower()
        # Check if line starts with action verb or contains it
        if any(verb in line_lower for verb in action_verbs) and len(line.split()) > 3:
            # Clean up bullet points
            cleaned = line.lstrip('-•*').strip()
            if cleaned and len(cleaned) > 10:
                responsibilities.append(cleaned)
                if len(responsibilities) >= 6:
                    break

    # Default responsibilities if nothing found
    if not responsibilities or len(responsibilities) < 3:
        responsibilities = [
            "Perform duties as specified in the job description",
            "Collaborate with team members and stakeholders",
            "Maintain accurate documentation and reports",
            "Ensure quality and compliance with standards",
            "Support continuous improvement initiatives"
        ]

    return responsibilities[:6]  # Max 6
