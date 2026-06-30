"""
CV Screener - AI-Enhanced Version (Proof of Concept)
Uses Claude API for deep CV analysis with context understanding
"""

import os
import json
from datetime import datetime

# Import CVParser with relative import for package structure
try:
    from .cv_screener import CVParser
except ImportError:
    from cv_screener import CVParser  # Reuse existing parser

# Conditional import for Claude API
try:
    from anthropic import Anthropic
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    print("⚠️  anthropic package not installed. Install with: pip install anthropic")


class AIEnhancedCVScreener:
    """
    AI-Enhanced CV Screener using Claude API

    Benefits over rule-based approach:
    - Context understanding (knows difference between "want to learn" vs "expert in")
    - Relevance detection (only counts relevant experience)
    - Skill level assessment (beginner/intermediate/expert)
    - Red flag detection (job hopping, gaps, mismatches)
    - Detailed reasoning for recommendations
    """

    def __init__(self, job_config, api_key=None):
        """
        Initialize AI-Enhanced screener

        Args:
            job_config: Job configuration dict
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
        """
        self.job_config = job_config

        if not CLAUDE_AVAILABLE:
            raise Exception("anthropic package not installed. Run: pip install anthropic")

        # Get API key from environment or parameter
        api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        if not api_key:
            raise Exception("ANTHROPIC_API_KEY not found. Set environment variable or pass api_key parameter")

        self.client = Anthropic(api_key=api_key)

    def build_prompt(self, cv_text, job_config):
        """Build prompt for Claude API"""

        prompt = f"""You are an expert HR recruiter analyzing a CV for a job position.

**Job Position:** {job_config['position_title']}

**Job Requirements:**
- Required Skills: {', '.join(job_config['required_skills'])}
- Minimum Experience: {job_config.get('min_experience', 0)} years
- Education: {', '.join(job_config.get('education_keywords', []))}
- Certifications: {', '.join(job_config.get('certification_keywords', []))}

**Candidate CV:**
{cv_text}

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
  "candidate_info": {{
    "name": "Full name of candidate",
    "email": "email@example.com",
    "phone": "phone number"
  }},
  "experience": {{
    "total_years": 5,
    "relevant_years": 3,
    "details": "Brief summary of relevant experience",
    "positions": [
      {{"title": "Job Title", "company": "Company Name", "duration": "2020-2023", "relevant": true}}
    ]
  }},
  "education": {{
    "highest_degree": "S1/S2/S3/Bachelor/Master/PhD",
    "major": "Computer Science",
    "university": "University Name",
    "graduation_year": 2019,
    "matches_requirement": true
  }},
  "skills": {{
    "matched_skills": [
      {{"skill": "Python", "level": "expert", "evidence": "5 years Python development"}},
      {{"skill": "SQL", "level": "intermediate", "evidence": "Used in 2 projects"}}
    ],
    "missing_critical_skills": ["Skill1", "Skill2"],
    "additional_relevant_skills": ["Skill3", "Skill4"]
  }},
  "certifications": [
    {{"name": "Oracle Certified Professional", "year": 2022, "relevant": true}}
  ],
  "red_flags": [
    "Job hopping (3 jobs in 2 years)",
    "6-month employment gap in 2021"
  ],
  "strengths": [
    "Strong technical background in required stack",
    "Consistent career progression"
  ],
  "scoring": {{
    "skills_score": 35,
    "experience_score": 25,
    "education_score": 18,
    "certification_score": 8,
    "total_score": 86,
    "reasoning": "Detailed explanation of scoring"
  }},
  "recommendation": {{
    "decision": "Highly Recommended / Recommended / Consider / Not Recommended",
    "confidence": "high / medium / low",
    "reasoning": "Detailed reasoning for the decision",
    "interview_focus": ["Topic1", "Topic2"]
  }}
}}
```

**Important:**
- Be strict: "want to learn Python" ≠ Python skill
- Be context-aware: "5 years as cashier" ≠ relevant for software developer
- Return ONLY valid JSON, no extra text
"""
        return prompt

    def screen_cv(self, cv_file_path):
        """
        Screen a single CV using AI

        Returns:
            dict: Detailed analysis results
        """
        try:
            # Parse CV text
            cv_text = CVParser.parse_cv(cv_file_path)

            # Build prompt
            prompt = self.build_prompt(cv_text, self.job_config)

            # Call Claude API
            print(f"🤖 Analyzing {os.path.basename(cv_file_path)} with AI...")

            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0,  # Deterministic output
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            # Parse response
            response_text = response.content[0].text

            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            ai_result = json.loads(response_text)

            # Format result for compatibility with existing system
            result = {
                'filename': os.path.basename(cv_file_path),
                'filepath': cv_file_path,
                'name': ai_result['candidate_info']['name'],
                'email': ai_result['candidate_info']['email'],
                'phone': ai_result['candidate_info']['phone'],
                'education': f"{ai_result['education']['highest_degree']} {ai_result['education']['major']}",
                'experience_years': ai_result['experience']['relevant_years'],
                'total_experience_years': ai_result['experience']['total_years'],
                'skills_found': [s['skill'] for s in ai_result['skills']['matched_skills']],
                'skills_with_levels': ai_result['skills']['matched_skills'],
                'missing_skills': ai_result['skills']['missing_critical_skills'],
                'skills_matched': f"{len(ai_result['skills']['matched_skills'])}/{len(self.job_config['required_skills'])}",
                'skills_score': ai_result['scoring']['skills_score'],
                'experience_score': ai_result['scoring']['experience_score'],
                'education_score': ai_result['scoring']['education_score'],
                'certification_score': ai_result['scoring']['certification_score'],
                'total_score': ai_result['scoring']['total_score'],
                'recommendation': ai_result['recommendation']['decision'],
                'confidence': ai_result['recommendation']['confidence'],
                'reasoning': ai_result['recommendation']['reasoning'],
                'red_flags': ai_result.get('red_flags', []),
                'strengths': ai_result.get('strengths', []),
                'interview_focus': ai_result['recommendation'].get('interview_focus', []),
                'ai_analysis': ai_result,  # Full AI response
                'processed_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'analysis_method': 'AI-Enhanced (Claude API)'
            }

            print(f"✅ Analysis complete: {result['recommendation']} (Score: {result['total_score']})")

            return result

        except json.JSONDecodeError as e:
            print(f"❌ Error parsing AI response: {e}")
            print(f"Raw response: {response_text[:500]}...")
            return {
                'filename': os.path.basename(cv_file_path),
                'error': f"JSON parsing error: {str(e)}",
                'total_score': 0,
                'recommendation': 'Error Processing'
            }
        except Exception as e:
            print(f"❌ Error processing {os.path.basename(cv_file_path)}: {e}")
            return {
                'filename': os.path.basename(cv_file_path),
                'error': str(e),
                'total_score': 0,
                'recommendation': 'Error Processing'
            }

    def screen_multiple_cvs(self, cv_files):
        """Screen multiple CVs and return sorted results"""
        results = []

        for i, cv_file in enumerate(cv_files, 1):
            print(f"\n[{i}/{len(cv_files)}] Processing: {os.path.basename(cv_file)}")
            result = self.screen_cv(cv_file)
            results.append(result)

        # Sort by total score (descending)
        results.sort(key=lambda x: x.get('total_score', 0), reverse=True)

        return results


def compare_screeners(cv_file, job_config):
    """
    Compare rule-based vs AI-enhanced screening

    Usage example:
        from cv_screener import CVScreener
        from cv_screener_ai_enhanced import AIEnhancedCVScreener, compare_screeners

        job_config = {
            "position_title": "Oracle EBS Developer",
            "required_skills": ["Oracle EBS", "PL/SQL", "Oracle Forms"],
            "min_experience": 3,
            "education_keywords": ["S1", "Bachelor"],
            "certification_keywords": ["OCP"]
        }

        compare_screeners("cv_sample.pdf", job_config)
    """
    from cv_screener import CVScreener

    print("=" * 70)
    print("COMPARISON: Rule-Based vs AI-Enhanced CV Screening")
    print("=" * 70)

    # Rule-based screening
    print("\n🔷 RULE-BASED SCREENING:")
    print("-" * 70)
    rule_screener = CVScreener(job_config)
    rule_result = rule_screener.screen_cv(cv_file)

    print(f"Name: {rule_result['name']}")
    print(f"Experience: {rule_result['experience_years']} years")
    print(f"Skills: {rule_result['skills_matched']}")
    print(f"Score: {rule_result['total_score']}")
    print(f"Recommendation: {rule_result['recommendation']}")

    # AI-enhanced screening
    print("\n🤖 AI-ENHANCED SCREENING:")
    print("-" * 70)
    ai_screener = AIEnhancedCVScreener(job_config)
    ai_result = ai_screener.screen_cv(cv_file)

    print(f"Name: {ai_result['name']}")
    print(f"Relevant Experience: {ai_result['experience_years']} years (Total: {ai_result['total_experience_years']})")
    print(f"Skills Matched: {ai_result['skills_matched']}")
    print("\nSkills with Proficiency:")
    for skill in ai_result.get('skills_with_levels', []):
        print(f"  - {skill['skill']}: {skill['level']} ({skill['evidence']})")

    if ai_result.get('missing_skills'):
        print(f"\nMissing Critical Skills: {', '.join(ai_result['missing_skills'])}")

    if ai_result.get('red_flags'):
        print(f"\n⚠️  Red Flags:")
        for flag in ai_result['red_flags']:
            print(f"  - {flag}")

    if ai_result.get('strengths'):
        print(f"\n✅ Strengths:")
        for strength in ai_result['strengths']:
            print(f"  - {strength}")

    print(f"\nScore: {ai_result['total_score']}")
    print(f"Recommendation: {ai_result['recommendation']} (Confidence: {ai_result['confidence']})")
    print(f"\nReasoning: {ai_result['reasoning']}")

    if ai_result.get('interview_focus'):
        print(f"\nInterview Focus Areas: {', '.join(ai_result['interview_focus'])}")

    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY:")
    print("=" * 70)
    print(f"Score Difference: {abs(ai_result['total_score'] - rule_result['total_score'])} points")
    print(f"Rule-Based: {rule_result['recommendation']}")
    print(f"AI-Enhanced: {ai_result['recommendation']}")

    return {
        'rule_based': rule_result,
        'ai_enhanced': ai_result
    }


if __name__ == "__main__":
    print("AI-Enhanced CV Screener - Proof of Concept")
    print("=" * 70)
    print("\n⚠️  This is a DEMO. Requires:")
    print("1. pip install anthropic")
    print("2. Set ANTHROPIC_API_KEY environment variable")
    print("\nUsage:")
    print("  from cv_screener_ai_enhanced import compare_screeners")
    print("  compare_screeners('cv.pdf', job_config)")
