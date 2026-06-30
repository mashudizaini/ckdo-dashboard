"""
CV Screening System - Web Interface
Flask application for uploading and screening CVs
"""

from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for
from werkzeug.utils import secure_filename
import os
import json
import pandas as pd
from datetime import datetime
from cv_screener import CVScreener, load_job_config, save_results_to_json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'docx', 'doc', 'txt'}

# Create necessary folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('results', exist_ok=True)
os.makedirs('exports', exist_ok=True)

# Global variable to store screening results
screening_results = []


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/')
def index():
    """Home page"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_files():
    """Handle CV file uploads"""
    if 'files[]' not in request.files:
        return jsonify({'error': 'No files uploaded'}), 400
    
    files = request.files.getlist('files[]')
    uploaded_files = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Add timestamp to avoid duplicates
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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


@app.route('/config', methods=['GET', 'POST'])
def job_config():
    """Manage job configuration"""
    if request.method == 'POST':
        config_data = request.json
        
        # Save configuration
        with open('job_config.json', 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        return jsonify({'success': True, 'message': 'Configuration saved'})
    
    else:
        # Load current configuration
        config = load_job_config()
        return jsonify(config)


@app.route('/screen', methods=['POST'])
def screen_cvs():
    """Start CV screening process"""
    global screening_results
    
    try:
        # Load job configuration
        job_config = load_job_config()
        
        # Get all uploaded CV files
        cv_files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath) and allowed_file(filename):
                cv_files.append(filepath)
        
        if not cv_files:
            return jsonify({'error': 'No CV files found to screen'}), 400
        
        # Initialize screener
        screener = CVScreener(job_config)
        
        # Screen all CVs
        results = screener.screen_multiple_cvs(cv_files)
        screening_results = results
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = f"results/screening_results_{timestamp}.json"
        save_results_to_json(results, results_file)
        
        return jsonify({
            'success': True,
            'total_cvs': len(results),
            'results': results,
            'results_file': results_file
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/results')
def get_results():
    """Get screening results"""
    global screening_results
    return jsonify(screening_results)


@app.route('/export/excel', methods=['POST'])
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
        export_file = f"exports/cv_screening_results_{timestamp}.xlsx"
        
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


@app.route('/export/json')
def export_json():
    """Export results to JSON"""
    global screening_results
    
    if not screening_results:
        return jsonify({'error': 'No results to export'}), 400
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    export_file = f"exports/cv_screening_results_{timestamp}.json"
    
    with open(export_file, 'w', encoding='utf-8') as f:
        json.dump(screening_results, f, indent=2, ensure_ascii=False)
    
    return send_file(
        export_file,
        as_attachment=True,
        download_name=f"cv_screening_results_{timestamp}.json"
    )


@app.route('/clear', methods=['POST'])
def clear_uploads():
    """Clear uploaded files and results"""
    global screening_results
    
    try:
        # Clear uploaded files
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.isfile(filepath):
                os.remove(filepath)
        
        # Clear results
        screening_results = []
        
        return jsonify({'success': True, 'message': 'All data cleared'})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/stats')
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


if __name__ == '__main__':
    print("=" * 60)
    print("CV SCREENING SYSTEM - Web Interface")
    print("=" * 60)
    print("\nStarting server...")
    print("Access the application at: http://localhost:5000")
    print("\nPress CTRL+C to stop the server")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
