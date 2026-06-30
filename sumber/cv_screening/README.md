# CV Screening System

🎯 **AI-Powered Recruitment Assistant** - Otomatis screening ratusan CV dalam hitungan menit!

Sistem ini dirancang untuk CKD Otto Pharma untuk mempercepat proses rekrutmen dengan menggunakan teknologi Python dan NLP untuk menganalisis CV kandidat secara otomatis.

---

## ✨ Fitur Utama

- ✅ **Multi-Format Support** - PDF, DOCX, DOC, TXT
- ✅ **Intelligent Parsing** - Extract nama, email, phone, pendidikan, skills, dan pengalaman
- ✅ **Smart Scoring** - Ranking otomatis berdasarkan kesesuaian dengan job requirements
- ✅ **Web Interface** - User-friendly dashboard untuk upload dan view results
- ✅ **Command Line Interface** - Batch processing untuk automation
- ✅ **Multiple Export** - Excel, JSON, CSV formats
- ✅ **Customizable** - Konfigurasi job requirements sesuai kebutuhan
- ✅ **No AI API Cost** - Pure Python, tidak perlu GPT-4 atau API berbayar

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone atau download project ini
cd cv_screening_system

# Install dependencies
pip install -r requirements.txt

# Download spaCy language model
python -m spacy download en_core_web_sm
```

### 2. Konfigurasi Job Requirements

Edit file `job_config.json` sesuai posisi yang dibutuhkan:

```json
{
  "position_title": "Oracle EBS Technical Consultant",
  "required_skills": [
    "Oracle EBS",
    "Oracle Forms",
    "PL/SQL",
    "SQL"
  ],
  "min_experience": 3,
  "education_keywords": [
    "S1 Teknik Informatika",
    "Bachelor Computer Science"
  ],
  "certification_keywords": [
    "OCP",
    "Oracle Certified"
  ]
}
```

### 3. Run Web Application

```bash
python app.py
```

Buka browser: `http://localhost:5000`

### 4. Upload & Screen CVs

1. **Tab Configuration** - Setup job requirements
2. **Tab Upload CVs** - Upload CV files (support multiple files)
3. **Tab Results** - View ranked candidates, export hasil

---

## 📋 Cara Penggunaan

### A. Web Interface (Recommended)

**Langkah 1: Configure Job**
- Masuk ke tab "Job Configuration"
- Input position title, skills, min. experience
- Tambahkan education & certification keywords
- Save configuration

**Langkah 2: Upload CVs**
- Masuk ke tab "Upload CVs"
- Click area upload atau drag & drop files
- Upload multiple CVs sekaligus (max 16MB per file)
- Click "Start Screening Process"

**Langkah 3: View Results**
- Masuk ke tab "Results"
- Lihat ranking candidates berdasarkan score
- View statistics & analytics
- Export to Excel/JSON untuk sharing

### B. Command Line Interface

Untuk batch processing atau automation:

```bash
# Basic usage - screen all CVs in folder
python cli_screen.py -d ./cv_folder

# With custom config
python cli_screen.py -d ./cv_folder -c my_config.json

# Export to Excel
python cli_screen.py -d ./cv_folder -e excel

# Export to CSV
python cli_screen.py -d ./cv_folder -e csv

# Show top 20 candidates
python cli_screen.py -d ./cv_folder -t 20

# Only export, no display
python cli_screen.py -d ./cv_folder --no-display -e excel
```

### C. Python API (Integration)

Untuk integrasi dengan sistem lain:

```python
from cv_screener import CVScreener, load_job_config

# Load configuration
job_config = load_job_config('job_config.json')

# Initialize screener
screener = CVScreener(job_config)

# Screen single CV
result = screener.screen_cv('path/to/cv.pdf')
print(f"Score: {result['total_score']}")
print(f"Recommendation: {result['recommendation']}")

# Screen multiple CVs
cv_files = ['cv1.pdf', 'cv2.pdf', 'cv3.pdf']
results = screener.screen_multiple_cvs(cv_files)

# Results sorted by score (highest first)
for i, result in enumerate(results[:10], 1):
    print(f"#{i}. {result['name']} - Score: {result['total_score']}")
```

---

## 📊 Scoring System

System memberikan score 0-100 berdasarkan:

| Kategori | Weight | Penjelasan |
|----------|--------|------------|
| **Skills** | 40 points | Matching dengan required skills |
| **Experience** | 30 points | Years of experience vs minimum required |
| **Education** | 20 points | Matching dengan education keywords |
| **Certification** | 10 points | Professional certifications |

**Recommendation Levels:**
- **Highly Recommended** (80-100) - Priority untuk interview
- **Recommended** (60-79) - Good candidates
- **Consider** (40-59) - Review manual diperlukan
- **Not Recommended** (<40) - Below minimum requirements

---

## 📁 Project Structure

```
cv_screening_system/
├── app.py                 # Flask web application
├── cv_screener.py         # Core screening engine
├── cli_screen.py          # Command line interface
├── job_config.json        # Job requirements configuration
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html        # Web interface
├── uploads/              # Uploaded CV files (auto-created)
├── results/              # Screening results (auto-created)
└── exports/              # Exported files (auto-created)
```

---

## 🔧 Customization

### Mengubah Scoring Weights

Edit `job_config.json`:

```json
{
  "weights": {
    "skills": 50,      // Increase skills importance
    "experience": 25,
    "education": 15,
    "certification": 10
  }
}
```

### Menambah Skill Variations

System otomatis check variations (spaces, dashes, underscores):
- "Oracle EBS" akan match dengan "OracleEBS", "Oracle-EBS"
- "PL/SQL" akan match dengan "PLSQL", "PL SQL"

### Custom Education Matching

Tambahkan berbagai format pendidikan:

```json
{
  "education_keywords": [
    "S1 Teknik Informatika",
    "S1 Sistem Informasi", 
    "Bachelor Computer Science",
    "Bachelor Information Technology",
    "S1 Komputer",
    "D3 Informatika"
  ]
}
```

---

## 🎨 Screenshots

### Dashboard - Job Configuration
```
⚙️ Configure job requirements:
- Position title
- Required skills (add multiple)
- Minimum experience
- Education & certification keywords
```

### Upload & Processing
```
📤 Upload CVs:
- Drag & drop multiple files
- Support PDF, DOCX, DOC, TXT
- Real-time upload progress
- One-click screening
```

### Results & Analytics
```
📊 View Results:
- Ranked candidates table
- Statistics overview
- Score breakdown per candidate
- Export to Excel/JSON/CSV
```

---

## 💡 Tips & Best Practices

### 1. Optimasi Skill Keywords
Gunakan skill keywords yang specific dan sering muncul di CV:
```json
// Good ✅
"required_skills": ["Python", "SQL", "Oracle EBS", "PL/SQL"]

// Too generic ❌
"required_skills": ["Programming", "Database", "Good communication"]
```

### 2. Realistic Minimum Experience
Set minimum experience yang realistic:
```json
// Junior position
"min_experience": 0

// Mid-level
"min_experience": 3

// Senior
"min_experience": 5
```

### 3. Multiple Education Formats
Include berbagai format untuk capture lebih banyak kandidat:
```json
"education_keywords": [
  "S1 Teknik Informatika",    // Format Indonesia
  "Bachelor Computer Science", // Format International
  "Sarjana Komputer",          // Alternative wording
  "S1 TI"                      // Abbreviation
]
```

### 4. Batch Processing for Large Volume
Untuk screening ratusan CV, gunakan CLI mode:
```bash
# Process 500 CVs in one command
python cli_screen.py -d ./bulk_cvs -e excel --no-display
```

---

## 🔌 Integration dengan Oracle EBS

### Menyimpan Results ke Database

```python
import cx_Oracle
from cv_screener import CVScreener, load_job_config

# Screen CVs
job_config = load_job_config()
screener = CVScreener(job_config)
results = screener.screen_multiple_cvs(cv_files)

# Connect to Oracle
connection = cx_Oracle.connect(
    user='hr_user',
    password='password',
    dsn='localhost:1521/orcl'
)

cursor = connection.cursor()

# Insert to recruitment table
for result in results:
    cursor.execute("""
        INSERT INTO hr_cv_screening_results 
        (candidate_name, email, phone, score, recommendation, 
         experience_years, skills_matched, screening_date)
        VALUES 
        (:1, :2, :3, :4, :5, :6, :7, SYSDATE)
    """, (
        result['name'],
        result['email'],
        result['phone'],
        result['total_score'],
        result['recommendation'],
        result['experience_years'],
        result['skills_matched']
    ))

connection.commit()
cursor.close()
connection.close()
```

### Create Oracle Table

```sql
CREATE TABLE hr_cv_screening_results (
    screening_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    candidate_name VARCHAR2(200),
    email VARCHAR2(200),
    phone VARCHAR2(50),
    score NUMBER(5,2),
    recommendation VARCHAR2(50),
    experience_years NUMBER,
    skills_matched VARCHAR2(100),
    screening_date DATE,
    created_by VARCHAR2(100),
    creation_date DATE DEFAULT SYSDATE
);
```

---

## 🚀 Next Steps: Upgrade dengan AI (Optional)

Kalau basic screening sudah jalan dan Anda ingin upgrade dengan GPT-4:

### Install OpenAI

```bash
pip install openai
```

### Add AI Enhancement

```python
import openai
from cv_screener import CVScreener

class AIEnhancedScreener(CVScreener):
    def __init__(self, job_config, openai_api_key):
        super().__init__(job_config)
        openai.api_key = openai_api_key
    
    def ai_analyze(self, cv_text):
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{
                "role": "user",
                "content": f"Analyze this CV and provide insights:\n\n{cv_text}"
            }]
        )
        return response.choices[0].message.content
```

**Cost Estimate:**
- 100 CVs × top 20 with AI = 20 API calls
- ~$1-2 per month for occasional use
- ~$10-20 per month for heavy use

---

## ❓ Troubleshooting

### Issue: "No module named 'pdfplumber'"
```bash
pip install pdfplumber
```

### Issue: "spaCy model not found"
```bash
python -m spacy download en_core_web_sm
```

### Issue: "Port 5000 already in use"
Edit `app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=8080)  # Change port
```

### Issue: "Error parsing PDF"
- Check file tidak corrupt
- Try convert PDF to text-based (bukan scanned image)
- For scanned PDFs, perlu OCR preprocessing

---

## 📞 Support & Contact

Untuk pertanyaan atau issue:
1. Check README dan troubleshooting section
2. Review code comments di `cv_screener.py`
3. Test dengan sample CVs untuk validasi

---

## 📝 License

Internal use untuk CKD Otto Pharma.

---

## 🎯 Roadmap

**v1.0 (Current)**
- ✅ Basic CV parsing
- ✅ Skills & experience matching
- ✅ Web interface
- ✅ Excel/JSON export

**v1.1 (Future)**
- 🔄 OCR support untuk scanned PDFs
- 🔄 Email integration untuk auto-notification
- 🔄 API endpoint untuk external systems
- 🔄 Multi-language support (Bahasa Indonesia)

**v2.0 (Optional)**
- 🔄 GPT-4 integration untuk deep analysis
- 🔄 Interview scheduling automation
- 🔄 Candidate tracking dashboard
- 🔄 Integration dengan ATS systems

---

**Built with ❤️ for CKD Otto Pharma HR Team**

Happy Screening! 🚀
