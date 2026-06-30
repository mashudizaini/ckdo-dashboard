"""
CV Screening Blueprint - Converted from app_cv_screening.py
Flask Blueprint for uploading and screening CVs
"""

from flask import Blueprint, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
import json
import pandas as pd
from datetime import datetime

# Import from existing cv_screening module
try:
    from .cv_screener import CVScreener, load_job_config, save_results_to_json
    from .cv_screener_nlp import NLPEnhancedCVScreener, SPACY_AVAILABLE
    from .cv_screener_ai_enhanced import AIEnhancedCVScreener, CLAUDE_AVAILABLE
except ImportError:
    from cv_screener import CVScreener, load_job_config, save_results_to_json
    from cv_screener_nlp import NLPEnhancedCVScreener, SPACY_AVAILABLE
    from cv_screener_ai_enhanced import AIEnhancedCVScreener, CLAUDE_AVAILABLE

# Create Blueprint
cv_bp = Blueprint('cv_screening', __name__,
                  url_prefix='/cv-screening',
                  template_folder='templates',
                  static_folder='static')

# Configuration
UPLOAD_FOLDER = 'uploads/cv_screening'
RESULTS_FOLDER = 'results/cv_screening'
EXPORTS_FOLDER = 'exports/cv_screening'
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}

# Create necessary folders
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)
os.makedirs(EXPORTS_FOLDER, exist_ok=True)

# Global variable to store screening results
screening_results = []


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@cv_bp.route('/')
def index():
    """Home page"""
    # Use the standalone CV screening template, not the base.html version
    return render_template('cv_screening_app.html')


@cv_bp.route('/upload', methods=['POST'])
def upload_files():
    """Handle CV file uploads"""
    global screening_results

    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400

    files = request.files.getlist('files[]')
    uploaded_files = []

    # Clear old uploaded files from folder
    for filename in os.listdir(UPLOAD_FOLDER):
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.isfile(filepath):
                os.unlink(filepath)
        except Exception as e:
            print(f"Error deleting {filepath}: {e}")

    # Clear old results
    screening_results = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to avoid duplicates
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            file.save(filepath)
            uploaded_files.append({
                'filename': file.filename,
                'saved_as': filename,
                'filepath': filepath
            })

    return jsonify({
        'success': True,
        'files': uploaded_files,
        'count': len(uploaded_files)
    })


@cv_bp.route('/config', methods=['GET', 'POST'])
def job_config():
    """Manage job configuration"""
    if request.method == 'POST':
        config_data = request.json
        config_name = config_data.pop('config_name', 'job_config')  # Get custom name, default to 'job_config'

        # Sanitize filename
        safe_name = "".join(c for c in config_name if c.isalnum() or c in (' ', '-', '_')).strip()
        if not safe_name:
            safe_name = 'job_config'

        # Save configuration with custom name
        config_filename = f"{safe_name}.json"
        config_path = os.path.join(RESULTS_FOLDER, config_filename)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        return jsonify({
            'success': True,
            'message': f'Configuration saved as "{config_filename}"',
            'filename': config_filename
        })

    else:
        # Load current configuration
        config_name = request.args.get('name', 'job_config')  # Get config name from query param

        try:
            # Try to load specified config
            config_path = os.path.join(RESULTS_FOLDER, f"{config_name}.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            else:
                # Try to load from app directory
                app_config_path = os.path.join(os.path.dirname(__file__), 'job_config.json')
                if os.path.exists(app_config_path):
                    with open(app_config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                else:
                    config = load_job_config()
        except:
            config = load_job_config()
        return jsonify(config)


@cv_bp.route('/config/list', methods=['GET'])
def list_configs():
    """List all saved job configurations"""
    try:
        config_files = []
        for filename in os.listdir(RESULTS_FOLDER):
            if filename.endswith('.json') and ('job_config' in filename.lower() or 'config' in filename.lower()):
                filepath = os.path.join(RESULTS_FOLDER, filename)
                stat_info = os.stat(filepath)
                config_files.append({
                    'name': filename.replace('.json', ''),
                    'filename': filename,
                    'modified': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'size': stat_info.st_size
                })

        # Sort by modified date (newest first)
        config_files.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({
            'success': True,
            'configs': config_files,
            'count': len(config_files)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'configs': []
        })


@cv_bp.route('/methods/available', methods=['GET'])
def available_methods():
    """Check which screening methods are available"""
    methods = {
        'rule-based': {
            'available': True,
            'name': 'Rule-Based',
            'description': 'Pattern matching and keyword search (45% accuracy)',
            'accuracy': '45%',
            'speed': 'Fast',
            'cost': 'Free'
        },
        'nlp': {
            'available': SPACY_AVAILABLE,
            'name': 'NLP-Enhanced (spaCy)',
            'description': 'Named Entity Recognition and context-aware parsing (70% accuracy)',
            'accuracy': '70%',
            'speed': 'Medium',
            'cost': 'Free',
            'requirements': 'pip install spacy && python -m spacy download en_core_web_sm'
        },
        'ai': {
            'available': CLAUDE_AVAILABLE,
            'name': 'AI-Powered (Claude)',
            'description': 'Deep understanding with LLM analysis (93% accuracy)',
            'accuracy': '93%',
            'speed': 'Slow',
            'cost': '$0.01-0.03 per CV',
            'requirements': 'pip install anthropic + ANTHROPIC_API_KEY'
        }
    }

    return jsonify({
        'success': True,
        'methods': methods,
        'default': 'rule-based'
    })


@cv_bp.route('/jd/upload', methods=['POST'])
def upload_jd():
    """Upload and analyze job description file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Check file extension
        allowed_extensions = {'txt', 'pdf', 'docx', 'doc'}
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({'error': f'File type not supported. Allowed: {", ".join(allowed_extensions)}'}), 400

        # Save uploaded file temporarily
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_filename = f"jd_{timestamp}_{filename}"
        temp_filepath = os.path.join(UPLOAD_FOLDER, temp_filename)
        file.save(temp_filepath)

        # Extract text from file
        try:
            from .cv_screener import CVParser
        except ImportError:
            from cv_screener import CVParser

        jd_text = CVParser.parse_cv(temp_filepath)

        # Delete temporary file
        try:
            os.unlink(temp_filepath)
        except:
            pass

        return jsonify({
            'success': True,
            'filename': file.filename,
            'text': jd_text,
            'length': len(jd_text)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cv_bp.route('/jd/generate', methods=['POST'])
def generate_jd():
    """Generate improved job description using AI or Template method"""
    try:
        data = request.json
        original_jd = data.get('jd_text', '')
        method = data.get('method', 'template')  # 'ai' or 'template'

        if not original_jd:
            return jsonify({'error': 'No job description text provided'}), 400

        # ===================================
        # TEMPLATE-BASED METHOD (FREE)
        # ===================================
        if method == 'template':
            from .jd_generator_template import generate_jd_template_based

            print(f"📋 Generating improved JD with Template method (FREE)...")
            result = generate_jd_template_based(original_jd)

            return jsonify({
                'success': True,
                'result': result,
                'method': 'template',
                'original_length': len(original_jd),
                'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        # ===================================
        # AI-POWERED METHOD (CLAUDE API)
        # ===================================
        elif method == 'ai':
            # Check if Claude API is available
            if not CLAUDE_AVAILABLE:
                return jsonify({
                    'error': 'Claude API not available. Install with: pip install anthropic',
                    'suggestion': 'Use Template-Based method instead (free, no API required)'
                }), 400

            # Get API key
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if not api_key:
                return jsonify({
                    'error': 'ANTHROPIC_API_KEY not found. Set environment variable.',
                    'suggestion': 'Use Template-Based method instead (free, no API required)'
                }), 400

            # Import Anthropic
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)

            # Build prompt for JD improvement
            prompt = f"""You are an expert HR consultant specializing in writing clear, comprehensive job descriptions.

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
    "key_responsibilities": [
      "Responsibility 1",
      "Responsibility 2",
      "Responsibility 3"
    ],
    "required_qualifications": {{
      "education": "Specific degree requirements (e.g., Bachelor in Computer Science)",
      "experience": "X years in specific field/industry",
      "technical_skills": [
        "Must-have skill 1",
        "Must-have skill 2",
        "Must-have skill 3"
      ],
      "soft_skills": [
        "Communication",
        "Teamwork",
        "Problem-solving"
      ],
      "certifications": [
        "Required certification 1",
        "Required certification 2"
      ]
    }},
    "preferred_qualifications": {{
      "experience": "Additional preferred experience",
      "skills": [
        "Nice-to-have skill 1",
        "Nice-to-have skill 2"
      ],
      "certifications": [
        "Preferred certification 1"
      ]
    }},
    "screening_criteria": {{
      "position_title": "Job title for screening system",
      "required_skills": ["Skill1", "Skill2", "Skill3"],
      "min_experience": 3,
      "education_keywords": ["Bachelor", "Computer Science"],
      "certification_keywords": ["OCP", "Certified"]
    }}
  }},
  "improvements_made": [
    "What was improved/clarified",
    "What was added",
    "What was restructured"
  ],
  "hr_notes": "Tips for HR when reviewing CVs based on this JD"
}}
```

**Important Guidelines:**
- Be specific: "5 years experience in pharmaceutical industry" NOT "experienced"
- Separate must-have from nice-to-have
- Make it easy for non-technical HR to understand technical requirements
- Provide clear screening criteria that can be used in CV screening system
- Return ONLY valid JSON, no extra text
"""

            # Call Claude API
            print(f"🤖 Generating improved JD with AI...")
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse response
            response_text = response.content[0].text

            # Extract JSON from response
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()

            result = json.loads(response_text)

            return jsonify({
                'success': True,
                'result': result,
                'method': 'ai',
                'original_length': len(original_jd),
                'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })

        else:
            return jsonify({
                'error': f'Invalid method: {method}. Use "ai" or "template"'
            }), 400

    except json.JSONDecodeError as e:
        return jsonify({
            'error': f'Failed to parse AI response: {str(e)}',
            'raw_response': response_text[:500] if 'response_text' in locals() else 'N/A'
        }), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cv_bp.route('/screen', methods=['POST'])
def screen_cvs():
    """Start CV screening process"""
    global screening_results

    try:
        # Load job configuration
        config_path = os.path.join(RESULTS_FOLDER, 'job_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                job_config = json.load(f)
        else:
            # Try to load from app directory
            app_config_path = os.path.join(os.path.dirname(__file__), 'job_config.json')
            if os.path.exists(app_config_path):
                with open(app_config_path, 'r', encoding='utf-8') as f:
                    job_config = json.load(f)
            else:
                job_config = load_job_config()

        # Get all uploaded CV files
        cv_files = []
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath) and allowed_file(filename):
                cv_files.append(filepath)

        if not cv_files:
            return jsonify({'error': 'No CV files found to screen'}), 400

        # Get screening method from config (default to 'rule-based')
        screening_method = job_config.get('screening_method', 'rule-based')

        # Initialize appropriate screener based on method
        if screening_method == 'nlp' and SPACY_AVAILABLE:
            screener = NLPEnhancedCVScreener(job_config)
        elif screening_method == 'ai' and CLAUDE_AVAILABLE:
            screener = AIEnhancedCVScreener(job_config)
        else:
            # Fallback to rule-based if method not available
            screener = CVScreener(job_config)
            if screening_method != 'rule-based':
                print(f"⚠️  Requested method '{screening_method}' not available, using rule-based")

        # Screen all CVs
        results = screener.screen_multiple_cvs(cv_files)
        screening_results = results

        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = os.path.join(RESULTS_FOLDER, f"screening_results_{timestamp}.json")
        save_results_to_json(results, results_file)

        return jsonify({
            'success': True,
            'total_cvs': len(results),
            'results': results,
            'results_file': results_file
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cv_bp.route('/results')
def get_results():
    """Get screening results with pagination for large datasets"""
    global screening_results

    # Ensure screening_results is a list
    if screening_results is None:
        screening_results = []

    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)  # Default 50 results per page

    # For very large datasets, limit per_page
    if per_page > 100:
        per_page = 100

    total_count = len(screening_results) if isinstance(screening_results, list) else 0

    # If dataset is too large (>50 items), use pagination
    if total_count > 50:
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_results = screening_results[start_idx:end_idx]

        return jsonify({
            'results': paginated_results,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total_count': total_count,
                'total_pages': (total_count + per_page - 1) // per_page,
                'has_next': end_idx < total_count,
                'has_prev': page > 1
            },
            'warning': 'Large dataset detected. Showing paginated results. Use Export to Excel for full data.'
        })
    else:
        # For small datasets, return all results
        try:
            return jsonify(screening_results)
        except Exception as e:
            # If jsonify still fails, return error
            return jsonify({
                'error': f'Results too large to transfer: {str(e)}',
                'total_count': total_count,
                'suggestion': 'Use Export to Excel instead'
            }), 413


@cv_bp.route('/export/excel', methods=['POST'])
def export_excel():
    """Export results to Excel"""
    global screening_results

    if not screening_results:
        return jsonify({'error': 'No results to export'}), 400

    try:
        # Convert to DataFrame
        df = pd.DataFrame(screening_results)

        # Select and order columns
        columns = [
            'name', 'email', 'phone', 'total_score', 'recommendation',
            'experience_years', 'skills_matched', 'education',
            'skills_score', 'experience_score', 'education_score', 'certification_score',
            'filename', 'processed_date'
        ]

        # Filter columns that exist
        available_columns = [col for col in columns if col in df.columns]
        df = df[available_columns]

        # Sort by score
        df = df.sort_values('total_score', ascending=False)

        # Export to Excel
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_file = os.path.join(EXPORTS_FOLDER, f"cv_screening_results_{timestamp}.xlsx")

        with pd.ExcelWriter(export_file, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Screening Results', index=False)

            # Get workbook and worksheet
            workbook = writer.book
            worksheet = writer.sheets['Screening Results']

            # Auto-adjust column width
            for column in worksheet.columns:
                max_length = 0
                column = [cell for cell in column]
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column[0].column_letter].width = adjusted_width

        return send_file(
            export_file,
            as_attachment=True,
            download_name=f"cv_screening_results_{timestamp}.xlsx"
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cv_bp.route('/export/json')
def export_json():
    """Export results to JSON"""
    global screening_results

    if not screening_results:
        return jsonify({'error': 'No results to export'}), 400

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    export_file = os.path.join(EXPORTS_FOLDER, f"cv_screening_results_{timestamp}.json")

    with open(export_file, 'w', encoding='utf-8') as f:
        json.dump(screening_results, f, indent=2, ensure_ascii=False)

    return send_file(
        export_file,
        as_attachment=True,
        download_name=f"cv_screening_results_{timestamp}.json"
    )


@cv_bp.route('/clear', methods=['POST'])
def clear_uploads():
    """Clear uploaded files and results"""
    global screening_results

    try:
        # Clear uploaded files
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                os.remove(filepath)

        # Clear results
        screening_results = []

        return jsonify({'success': True, 'message': 'All data cleared'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@cv_bp.route('/stats')
def get_stats():
    """Get screening statistics"""
    global screening_results

    if not screening_results:
        return jsonify({'error': 'No results available'}), 404

    # Calculate statistics
    total = len(screening_results)
    highly_recommended = sum(1 for r in screening_results if r.get('recommendation') == 'Highly Recommended')
    recommended = sum(1 for r in screening_results if r.get('recommendation') == 'Recommended')
    consider = sum(1 for r in screening_results if r.get('recommendation') == 'Consider')
    not_recommended = sum(1 for r in screening_results if r.get('recommendation') == 'Not Recommended')

    scores = [r.get('total_score', 0) for r in screening_results]
    avg_score = sum(scores) / len(scores) if scores else 0

    stats = {
        'total_cvs': total,
        'highly_recommended': highly_recommended,
        'recommended': recommended,
        'consider': consider,
        'not_recommended': not_recommended,
        'average_score': round(avg_score, 2),
        'highest_score': max(scores) if scores else 0,
        'lowest_score': min(scores) if scores else 0
    }

    return jsonify(stats)


# Helper functions for external import
def screen_cv(cv_path, job_config):
    """Screen a single CV"""
    screener = CVScreener(job_config)
    return screener.screen_cv(cv_path)


def get_candidates():
    """Get current screening results"""
    global screening_results
    return screening_results
