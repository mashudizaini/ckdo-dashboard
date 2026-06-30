"""
CV Screening Application
Menggunakan Claude API untuk screening CV kandidat
"""
from flask import Blueprint, render_template, request, jsonify
import anthropic
import os
import sys

# Add parent directory to path for config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import ANTHROPIC_API_KEY

# Create Blueprint
cv_bp = Blueprint('cv_screening', __name__, 
                  template_folder='templates',
                  url_prefix='/cv-screening')

# Initialize Claude client
client = None
if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY != 'your-api-key-here':
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================================
# DUMMY DATA (untuk demo tanpa API)
# ============================================
DUMMY_CANDIDATES = [
    {
        'id': 1,
        'name': 'Budi Santoso',
        'position': 'QC Analyst',
        'score': 92,
        'skills_match': 85,
        'experience': '5 years',
        'education': 'S1 Farmasi - UI',
        'status': 'Recommended',
        'ai_summary': 'Kandidat sangat qualified dengan pengalaman QC di industri farmasi. Memiliki sertifikasi GMP dan familiar dengan Oracle EBS.'
    },
    {
        'id': 2,
        'name': 'Dewi Lestari',
        'position': 'R&D Scientist',
        'score': 88,
        'skills_match': 90,
        'experience': '3 years',
        'education': 'S2 Kimia - ITB',
        'status': 'Recommended',
        'ai_summary': 'Background research yang kuat. Pengalaman di formulasi obat dan analytical method development.'
    },
    {
        'id': 3,
        'name': 'Eko Prasetyo',
        'position': 'Production Operator',
        'score': 72,
        'skills_match': 70,
        'experience': '2 years',
        'education': 'D3 Teknik Kimia',
        'status': 'Review Required',
        'ai_summary': 'Pengalaman terbatas di manufaktur farmasi. Perlu training tambahan untuk GMP compliance.'
    }
]

DUMMY_JOB_REQUIREMENTS = {
    'QC Analyst': {
        'skills': ['HPLC', 'GC', 'Spektrofotometri', 'GMP', 'Documentation'],
        'experience': '3+ years',
        'education': 'S1 Farmasi/Kimia'
    },
    'R&D Scientist': {
        'skills': ['Formulasi', 'Analytical Development', 'Stability Study', 'Research'],
        'experience': '2+ years',
        'education': 'S1/S2 Farmasi/Kimia'
    },
    'Production Operator': {
        'skills': ['GMP', 'Machine Operation', 'Batch Record', 'Safety'],
        'experience': '1+ years',
        'education': 'D3/S1 Teknik/Farmasi'
    }
}

# ============================================
# CORE FUNCTIONS
# ============================================

def screen_cv(cv_text: str, job_position: str) -> dict:
    """
    Screen CV menggunakan Claude API
    
    Args:
        cv_text: Text content dari CV
        job_position: Posisi yang dilamar
    
    Returns:
        dict dengan hasil screening
    """
    if not client:
        # Return dummy response jika tidak ada API key
        return {
            'score': 85,
            'skills_match': 80,
            'recommendation': 'Recommended',
            'summary': 'Demo mode - Claude API not configured',
            'strengths': ['Pengalaman relevan', 'Pendidikan sesuai'],
            'concerns': ['Perlu verifikasi referensi']
        }
    
    # Get job requirements
    requirements = DUMMY_JOB_REQUIREMENTS.get(job_position, {})
    
    prompt = f"""Analisis CV berikut untuk posisi {job_position}.

Requirements untuk posisi ini:
- Skills: {', '.join(requirements.get('skills', []))}
- Experience: {requirements.get('experience', 'N/A')}
- Education: {requirements.get('education', 'N/A')}

CV Content:
{cv_text}

Berikan analisis dalam format JSON:
{{
    "score": <skor 0-100>,
    "skills_match": <persentase kecocokan skills>,
    "recommendation": "<Recommended/Review Required/Not Recommended>",
    "summary": "<ringkasan 2-3 kalimat>",
    "strengths": ["<kelebihan 1>", "<kelebihan 2>"],
    "concerns": ["<concern 1>", "<concern 2>"]
}}
"""
    
    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Parse response
        import json
        result = json.loads(response.content[0].text)
        return result
        
    except Exception as e:
        return {
            'score': 0,
            'skills_match': 0,
            'recommendation': 'Error',
            'summary': f'Error processing CV: {str(e)}',
            'strengths': [],
            'concerns': ['Processing error']
        }


def get_candidates(position: str = None) -> list:
    """
    Get list of candidates, optionally filtered by position
    """
    if position:
        return [c for c in DUMMY_CANDIDATES if c['position'] == position]
    return DUMMY_CANDIDATES


def get_job_positions() -> list:
    """Get available job positions"""
    return list(DUMMY_JOB_REQUIREMENTS.keys())


# ============================================
# ROUTES (Blueprint)
# ============================================

@cv_bp.route('/')
def index():
    """Main CV Screening page"""
    candidates = get_candidates()
    positions = get_job_positions()
    return render_template('cv_screening/index.html', 
                         candidates=candidates,
                         positions=positions)


@cv_bp.route('/screen', methods=['POST'])
def screen():
    """API endpoint untuk screen CV"""
    data = request.json
    cv_text = data.get('cv_text', '')
    position = data.get('position', 'QC Analyst')
    
    result = screen_cv(cv_text, position)
    return jsonify(result)


@cv_bp.route('/candidates')
def list_candidates():
    """API endpoint untuk get candidates"""
    position = request.args.get('position')
    candidates = get_candidates(position)
    return jsonify(candidates)


@cv_bp.route('/candidate/<int:id>')
def get_candidate(id):
    """Get single candidate detail"""
    for c in DUMMY_CANDIDATES:
        if c['id'] == id:
            return jsonify(c)
    return jsonify({'error': 'Not found'}), 404


# ============================================
# STANDALONE EXECUTION
# ============================================

if __name__ == '__main__':
    # Untuk testing standalone
    print("CV Screening Module")
    print("=" * 40)
    print("Available positions:", get_job_positions())
    print("\nCandidates:")
    for c in get_candidates():
        print(f"  - {c['name']}: {c['position']} (Score: {c['score']})")
