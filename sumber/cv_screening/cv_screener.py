"""
CV Screener - Main Module
Handles CV parsing, skills extraction, and scoring
"""

import pdfplumber
import docx
import re
import os
from datetime import datetime
import json


class CVParser:
    """Parse CV from various formats (PDF, DOCX, TXT)"""
    
    @staticmethod
    def parse_pdf(file_path):
        """Extract text from PDF file"""
        try:
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
            return text.strip()
        except Exception as e:
            raise Exception(f"Error parsing PDF: {str(e)}")
    
    @staticmethod
    def parse_docx(file_path):
        """Extract text from DOCX file"""
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text.strip()
        except Exception as e:
            raise Exception(f"Error parsing DOCX: {str(e)}")
    
    @staticmethod
    def parse_txt(file_path):
        """Extract text from TXT file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except Exception as e:
            raise Exception(f"Error parsing TXT: {str(e)}")
    
    @staticmethod
    def parse_cv(file_path):
        """Auto-detect format and parse CV"""
        ext = os.path.splitext(file_path)[1].lower()
        
        if ext == '.pdf':
            return CVParser.parse_pdf(file_path)
        elif ext in ['.docx', '.doc']:
            return CVParser.parse_docx(file_path)
        elif ext == '.txt':
            return CVParser.parse_txt(file_path)
        else:
            raise Exception(f"Unsupported file format: {ext}")


class CVAnalyzer:
    """Analyze CV content and extract information"""
    
    @staticmethod
    def extract_email(text):
        """Extract email address from CV"""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text)
        return emails[0] if emails else None
    
    @staticmethod
    def extract_phone(text):
        """Extract phone number from CV"""
        # Pattern untuk nomor telepon Indonesia dan internasional
        phone_patterns = [
            r'\+?62\s?[0-9]{9,13}',  # Indonesian format
            r'0[0-9]{9,11}',  # Local Indonesian
            r'\+?[0-9]{10,15}',  # International
            r'\([0-9]{3}\)\s?[0-9]{3,4}-?[0-9]{4}'  # (021) 1234-5678
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            if phones:
                return phones[0]
        return None
    
    @staticmethod
    def extract_name(text):
        """Extract candidate name - usually in first few lines"""
        lines = text.split('\n')
        # Ambil baris pertama yang ada isinya dan tidak terlalu panjang
        for line in lines[:10]:
            line = line.strip()
            if line and len(line.split()) <= 5 and len(line) < 50:
                # Skip jika line adalah email atau phone
                if '@' not in line and not re.search(r'\d{8,}', line):
                    return line
        return "Unknown"
    
    @staticmethod
    def extract_education(text):
        """Extract education information"""
        education_keywords = [
            'S3', 'S2', 'S1', 'D3', 'D4',
            'PhD', 'Master', 'Bachelor', 'Diploma',
            'Sarjana', 'Magister', 'Doktor',
            'University', 'Universitas', 'Institut'
        ]
        
        found_education = []
        text_lower = text.lower()
        
        for keyword in education_keywords:
            if keyword.lower() in text_lower:
                found_education.append(keyword)
        
        # Remove duplicates
        return list(set(found_education))
    
    @staticmethod
    def calculate_experience_years(text):
        """Calculate years of experience from CV"""
        # Pattern untuk mencari tahun pengalaman
        patterns = [
            r'(\d+)\s*(?:years?|tahun)\s*(?:of)?\s*(?:experience|pengalaman)',
            r'(?:experience|pengalaman)[:\s]+(\d+)\s*(?:years?|tahun)',
            r'(\d+)\+?\s*(?:years?|tahun)',
        ]
        
        years = []
        text_lower = text.lower()
        
        for pattern in patterns:
            matches = re.findall(pattern, text_lower)
            years.extend([int(y) for y in matches])
        
        # Coba hitung dari range tahun (2018-2023, dll)
        year_ranges = re.findall(r'(20\d{2})\s*[-–—]\s*(20\d{2}|present|now|sekarang)', text_lower)
        for start, end in year_ranges:
            start_year = int(start)
            end_year = datetime.now().year if end.lower() in ['present', 'now', 'sekarang'] else int(end)
            years.append(end_year - start_year)
        
        return max(years) if years else 0
    
    @staticmethod
    def extract_skills(text, required_skills):
        """Extract skills from CV based on required skills list"""
        found_skills = []
        text_lower = text.lower()
        
        for skill in required_skills:
            # Check exact match dan variations
            skill_lower = skill.lower()
            
            # Exact match
            if skill_lower in text_lower:
                found_skills.append(skill)
                continue
            
            # Check with common variations
            variations = [
                skill_lower.replace(' ', ''),  # Remove spaces
                skill_lower.replace('-', ' '),  # Replace dash with space
                skill_lower.replace('_', ' '),  # Replace underscore with space
            ]
            
            for variation in variations:
                if variation in text_lower:
                    found_skills.append(skill)
                    break
        
        return list(set(found_skills))  # Remove duplicates


class CVScreener:
    """Main CV Screening Engine"""
    
    def __init__(self, job_config):
        """
        Initialize screener with job configuration
        
        job_config should contain:
        - position_title: str
        - required_skills: list
        - min_experience: int (years)
        - education_keywords: list
        - certification_keywords: list (optional)
        - weights: dict (optional) - scoring weights
        """
        self.job_config = job_config
        
        # Default weights if not provided
        default_weights = {
            'skills': 40,
            'experience': 30,
            'education': 20,
            'certification': 10
        }
        self.weights = job_config.get('weights', default_weights)
    
    def score_skills(self, found_skills):
        """Score based on skills matching"""
        required_skills = self.job_config['required_skills']
        
        if not required_skills:
            return 0
        
        match_percentage = len(found_skills) / len(required_skills)
        score = match_percentage * self.weights['skills']
        
        return min(score, self.weights['skills'])
    
    def score_experience(self, years):
        """Score based on years of experience"""
        min_exp = self.job_config.get('min_experience', 0)
        
        if min_exp == 0:
            return self.weights['experience']
        
        if years >= min_exp:
            # Full score if meets minimum
            score = self.weights['experience']
            # Bonus for additional experience (up to 2x minimum)
            if years > min_exp:
                bonus = min(years - min_exp, min_exp) / min_exp * 10
                score += bonus
            return min(score, self.weights['experience'] + 10)
        else:
            # Partial score if below minimum
            return (years / min_exp) * self.weights['experience']
    
    def score_education(self, education_found, cv_text):
        """Score based on education matching"""
        education_keywords = self.job_config.get('education_keywords', [])
        
        if not education_keywords:
            return self.weights['education']
        
        text_lower = cv_text.lower()
        
        # Check if any required education keyword is found
        for keyword in education_keywords:
            if keyword.lower() in text_lower:
                return self.weights['education']
        
        # Partial score if education is mentioned but not matching
        if education_found:
            return self.weights['education'] * 0.5
        
        return 0
    
    def score_certification(self, cv_text):
        """Score based on certifications"""
        cert_keywords = self.job_config.get('certification_keywords', [])
        
        if not cert_keywords:
            return self.weights['certification']
        
        text_lower = cv_text.lower()
        found_certs = 0
        
        for cert in cert_keywords:
            if cert.lower() in text_lower:
                found_certs += 1
        
        if found_certs > 0:
            return self.weights['certification']
        
        return 0
    
    def screen_cv(self, cv_file_path):
        """Screen a single CV and return results"""
        try:
            # Parse CV
            cv_text = CVParser.parse_cv(cv_file_path)
            
            # Extract information
            name = CVAnalyzer.extract_name(cv_text)
            email = CVAnalyzer.extract_email(cv_text)
            phone = CVAnalyzer.extract_phone(cv_text)
            education = CVAnalyzer.extract_education(cv_text)
            experience_years = CVAnalyzer.calculate_experience_years(cv_text)
            found_skills = CVAnalyzer.extract_skills(cv_text, self.job_config['required_skills'])
            
            # Calculate scores
            skills_score = self.score_skills(found_skills)
            experience_score = self.score_experience(experience_years)
            education_score = self.score_education(education, cv_text)
            certification_score = self.score_certification(cv_text)
            
            total_score = skills_score + experience_score + education_score + certification_score
            
            # Determine recommendation
            if total_score >= 80:
                recommendation = "Highly Recommended"
            elif total_score >= 60:
                recommendation = "Recommended"
            elif total_score >= 40:
                recommendation = "Consider"
            else:
                recommendation = "Not Recommended"
            
            result = {
                'filename': os.path.basename(cv_file_path),
                'filepath': cv_file_path,
                'name': name,
                'email': email,
                'phone': phone,
                'education': ', '.join(education) if education else 'Not Found',
                'experience_years': experience_years,
                'skills_found': found_skills,
                'skills_matched': f"{len(found_skills)}/{len(self.job_config['required_skills'])}",
                'skills_score': round(skills_score, 2),
                'experience_score': round(experience_score, 2),
                'education_score': round(education_score, 2),
                'certification_score': round(certification_score, 2),
                'total_score': round(total_score, 2),
                'recommendation': recommendation,
                'cv_preview': cv_text[:500] + '...' if len(cv_text) > 500 else cv_text,
                'processed_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return result
            
        except Exception as e:
            return {
                'filename': os.path.basename(cv_file_path),
                'error': str(e),
                'total_score': 0,
                'recommendation': 'Error Processing'
            }
    
    def screen_multiple_cvs(self, cv_files):
        """Screen multiple CVs and return sorted results"""
        results = []
        
        for cv_file in cv_files:
            print(f"Processing: {os.path.basename(cv_file)}...")
            result = self.screen_cv(cv_file)
            results.append(result)
        
        # Sort by total score (descending)
        results.sort(key=lambda x: x.get('total_score', 0), reverse=True)
        
        return results


def load_job_config(config_file='job_config.json'):
    """Load job configuration from JSON file"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Return default config if file not found
        return {
            "position_title": "IT Specialist",
            "required_skills": ["Python", "SQL", "Oracle"],
            "min_experience": 3,
            "education_keywords": ["S1", "Bachelor"],
            "certification_keywords": ["OCP", "Certified"]
        }


def save_results_to_json(results, output_file='results.json'):
    """Save screening results to JSON file"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {output_file}")


if __name__ == "__main__":
    # Example usage
    print("CV Screening System - Testing Mode")
    print("=" * 50)
    
    # Sample job configuration
    job_config = {
        "position_title": "Oracle EBS Technical Consultant",
        "required_skills": [
            "Oracle EBS", "Oracle Forms", "Oracle Reports",
            "PL/SQL", "SQL", "Database Administration"
        ],
        "min_experience": 3,
        "education_keywords": ["S1 Teknik Informatika", "S1 Sistem Informasi", "Bachelor Computer Science"],
        "certification_keywords": ["OCP", "Oracle Certified Professional", "Oracle Certified Associate"]
    }
    
    screener = CVScreener(job_config)
    print(f"\nJob Position: {job_config['position_title']}")
    print(f"Required Skills: {', '.join(job_config['required_skills'])}")
    print(f"Min. Experience: {job_config['min_experience']} years")
    print("\nReady to screen CVs!")
