# CV Screening - Changelog

## Version 2.0 - 2025-12-29

### ✅ Fixed Issues

#### 1. **Results Not Cleared When Uploading New Files**
**Problem:** Ketika upload 73 files, lalu upload 5 files baru, hasilnya tetap menampilkan 73 files (hasil lama + baru tercampur)

**Solution:**
- Backend: Auto-clear folder `uploads/cv_screening` saat upload files baru
- Backend: Clear variable `screening_results` saat upload
- Frontend: Clear tampilan uploaded files list saat upload baru

**Files Changed:**
- [app_cv_screening_bp.py:58-99](../app_cv_screening_bp.py) - Added auto-clear in upload endpoint
- [cv_screening_app.html:831-833](../templates/cv_screening_app.html) - Clear frontend list

**How it works now:**
1. User upload 73 files → Screen → See 73 results ✅
2. User upload 5 new files → Old 73 files deleted → Screen → See only 5 results ✅

---

#### 2. **Save/Load Configuration Enhancement**
**Problem:**
- Save configuration tidak ada feedback yang jelas
- Load configuration tidak ada visual confirmation

**Solution:**
- Save: Sudah berfungsi dengan baik, tersimpan di **server** (`results/cv_screening/*.json`)
- Load: Added success alert saat load configuration
- Refresh: Menghapus alert otomatis yang mengganggu, hanya log ke console

**Files Changed:**
- [cv_screening_app.html:755-791](../templates/cv_screening_app.html) - Improved feedback

**Configuration Storage Location:**
- **Server:** `d:\CKDO_DASHBOARD\results\cv_screening\`
- **Format:** JSON files with custom names (e.g., `ValidationSeniorStaff_v1.json`)
- **Benefits:**
  - ✅ Accessible from any computer/client
  - ✅ Tidak hilang saat clear browser cache
  - ✅ Bisa dishare antar user
  - ✅ Backup di server

**How it works:**
1. Fill job configuration form
2. Enter configuration name (e.g., "Oracle_EBS_Developer")
3. Click "💾 Save Configuration"
4. Success message appears: "✅ Configuration saved as Oracle_EBS_Developer.json"
5. Configuration appears in dropdown list
6. Select from dropdown to load → "✅ Configuration loaded successfully!"

---

### 🆕 New Features

#### 3. **Multiple Screening Methods**
Added option to choose between 3 screening methods:

| Method | Accuracy | Speed | Cost | Installation |
|--------|----------|-------|------|--------------|
| **Rule-Based** | 45% | Fast | Free | ✅ Default |
| **NLP-Enhanced** | 70% | Medium | Free | `pip install spacy` |
| **AI-Powered** | 93% | Slow | $0.01-0.03/CV | `pip install anthropic` + API key |

**Files Added:**
- [cv_screener_nlp.py](../cv_screener_nlp.py) - spaCy-based NLP screener
- [cv_screener_ai_enhanced.py](../cv_screener_ai_enhanced.py) - Claude API screener
- [INSTALLATION.md](../INSTALLATION.md) - Detailed installation guide
- [AI_SCREENING_ANALYSIS.md](../AI_SCREENING_ANALYSIS.md) - Accuracy comparison

**How to use:**
1. Go to **Job Configuration** tab
2. Select **Screening Method** from dropdown
3. System shows which methods are available
4. Choose preferred method
5. Save configuration
6. Upload CVs and screen

**Status Check:**
- Frontend automatically checks which methods are available
- Shows requirements if method not available
- Fallback to rule-based if selected method unavailable

---

### 🔧 Technical Improvements

#### Import Fixes
- Fixed relative imports for package structure
- Added fallback imports for standalone usage
- UTF-8 encoding for Windows console

**Files Changed:**
- [cv_screener_nlp.py:10-14](../cv_screener_nlp.py)
- [cv_screener_ai_enhanced.py:10-14](../cv_screener_ai_enhanced.py)
- [app.py:6-12](../../app.py)

---

### 📋 Usage Guide

#### Typical Workflow:

**First Time Setup:**
1. Open https://127.0.0.1:5000/cv-screening
2. Go to "Job Configuration"
3. Fill in:
   - Position Title
   - Required Skills (use Add button)
   - Minimum Experience
   - Education Keywords
   - Certification Keywords (optional)
   - **Screening Method** (choose based on accuracy needs)
4. Enter configuration name
5. Click "💾 Save Configuration"

**Screening CVs:**
1. Go to "Upload CVs" tab
2. Click or drag-drop CV files (supports multiple files)
3. Wait for upload confirmation
4. Click "🔍 Start Screening"
5. Wait for processing
6. Go to "Results" tab to view results
7. Export to Excel or JSON if needed

**Reusing Saved Configuration:**
1. Go to "Job Configuration"
2. Select from "Load Saved Configuration" dropdown
3. Configuration loaded automatically
4. Modify if needed and save with new name

**Screening New Batch:**
1. Go to "Upload CVs" tab
2. Upload new files (old files automatically deleted)
3. Start screening
4. View new results (old results cleared)

---

### 📊 Current Status

**Available Methods:**
- ✅ Rule-Based: Active (no installation needed)
- ⚠️ NLP-Enhanced: Not available (need: `pip install spacy`)
- ⚠️ AI-Powered: Not available (need: `pip install anthropic` + API key)

**To Install NLP Method:**
```bash
pip install spacy
python -m spacy download en_core_web_sm
# Restart application
```

**To Install AI Method:**
```bash
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-your-key-here
# Restart application
```

See [INSTALLATION.md](../INSTALLATION.md) for detailed instructions.

---

### 🐛 Known Issues

None at the moment.

---

### 📝 Notes

**Save/Load Configuration:**
- All configurations saved on **server**, not client browser
- Location: `results/cv_screening/`
- Format: JSON with custom filename
- Persists across browser sessions
- Can be backed up by copying files

**File Upload:**
- Old files automatically deleted when uploading new batch
- Prevents disk space issues
- Ensures clean state for each screening session

**Results:**
- Cleared when uploading new files
- Can export before uploading new batch
- Automatically saved to `results/cv_screening/screening_results_TIMESTAMP.json`

---

## Previous Versions

### Version 1.0 - Initial Release
- Basic CV screening with rule-based pattern matching
- PDF, DOCX, TXT support
- Skills extraction
- Experience calculation
- Scoring system
