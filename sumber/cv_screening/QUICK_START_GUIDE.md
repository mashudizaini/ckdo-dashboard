# 🚀 QUICK START GUIDE
## CV Screening System - Panduan Cepat untuk HR Team

---

## 📦 Instalasi (Cukup 1x Setup)

### Step 1: Install Python
1. Download Python dari: https://www.python.org/downloads/
2. Saat install, **CENTANG** "Add Python to PATH"
3. Install sampai selesai

### Step 2: Setup System
1. Extract folder `cv_screening_system` ke computer Anda
2. Buka **Command Prompt** / **Terminal**
3. Masuk ke folder project:
   ```
   cd C:\path\to\cv_screening_system
   ```
4. Jalankan setup otomatis:
   ```
   python setup.py
   ```
5. Tunggu sampai muncul "SETUP COMPLETED SUCCESSFULLY!"

---

## 🎯 Cara Pakai - Web Interface (Paling Mudah!)

### Step 1: Jalankan Aplikasi
```
python app.py
```

Tunggu sampai muncul pesan:
```
Running on http://localhost:5000
```

### Step 2: Buka Browser
Buka Chrome/Firefox, ketik di address bar:
```
http://localhost:5000
```

### Step 3: Configure Job (Tab Pertama)
1. Klik tab **"⚙️ Job Configuration"**
2. Isi form:
   - **Position Title**: Misal "Oracle EBS Consultant"
   - **Required Skills**: Klik "Add Skill" untuk tiap skill
     - Contoh: Oracle EBS, SQL, PL/SQL, Oracle Forms
   - **Min Experience**: Misal 3 (tahun)
   - **Education Keywords**: Misal "S1 Teknik Informatika, Bachelor Computer Science"
   - **Certification**: Misal "OCP, Oracle Certified"
3. Klik **"💾 Save Configuration"**

### Step 4: Upload CVs (Tab Kedua)
1. Klik tab **"📤 Upload CVs"**
2. Klik area upload atau drag & drop file
3. Pilih CV files (bisa multiple selection)
   - Support: PDF, DOCX, DOC, TXT
4. File akan muncul di list "Uploaded Files"
5. Klik **"🚀 Start Screening Process"**
6. Tunggu proses selesai (beberapa detik - beberapa menit tergantung jumlah CV)

### Step 5: Lihat Results (Tab Ketiga)
1. Otomatis pindah ke tab **"📊 Results"**
2. Lihat:
   - **Statistics**: Total CVs, Highly Recommended, dll
   - **Table**: Ranking candidates dengan score
3. Untuk export:
   - Klik **"📥 Export to Excel"** → Download file Excel
   - Klik **"📥 Export to JSON"** → Download file JSON

### Step 6: Stop Aplikasi
Kalau sudah selesai:
- Tekan **CTRL+C** di Command Prompt
- Close browser

---

## 📝 Cara Pakai - Command Line (Untuk Batch Processing)

Kalau ada ratusan CV dan mau process sekaligus tanpa web interface:

### Basic Command
```
python cli_screen.py -d C:\path\to\cv_folder
```

Ganti `C:\path\to\cv_folder` dengan folder yang berisi CV files.

### Export ke Excel
```
python cli_screen.py -d C:\path\to\cv_folder -e excel
```

Hasilnya akan tersimpan di folder `exports/`

### Show Top 20 Candidates
```
python cli_screen.py -d C:\path\to\cv_folder -t 20
```

---

## 📊 Memahami Results

### Score (0-100)
- **80-100**: Highly Recommended → Prioritas untuk interview
- **60-79**: Recommended → Good candidates
- **40-59**: Consider → Perlu review manual
- **0-39**: Not Recommended → Below requirements

### Breakdown Score
Setiap kandidat dapat score dari:
- **Skills** (40%): Berapa banyak required skills yang dimiliki
- **Experience** (30%): Tahun pengalaman vs minimum yang dibutuhkan
- **Education** (20%): Matching dengan education keywords
- **Certification** (10%): Professional certifications

---

## 🔧 Tips & Tricks

### Tip 1: Update Job Config Sebelum Screening
Setiap posisi berbeda, jangan lupa update configuration sesuai kebutuhan posisi yang sedang di-hire.

### Tip 2: Gunakan Specific Skills
Jangan terlalu general:
- ❌ Bad: "Programming", "Database", "Good communication"
- ✅ Good: "Python", "Oracle EBS", "PL/SQL", "SQL"

### Tip 3: Multiple Education Formats
Include berbagai format:
- "S1 Teknik Informatika"
- "Bachelor Computer Science"
- "Sarjana Komputer"
- "S1 TI"

### Tip 4: Review Top Candidates Manual
System memberikan ranking, tapi keputusan final tetap HR:
- Review top 10-20 candidates secara detail
- Baca CV lengkapnya untuk konteks
- Consider soft skills yang tidak terdeteksi system

### Tip 5: Export & Share
Export hasil ke Excel untuk:
- Share dengan hiring manager
- Diskusi dengan team
- Archive untuk dokumentasi

---

## ❓ Troubleshooting

### Problem: "Command not found: python"
**Solusi**: 
- Install Python dari python.org
- Pastikan centang "Add to PATH" saat install
- Restart Command Prompt

### Problem: "Port 5000 already in use"
**Solusi**:
- Ada aplikasi lain yang pakai port 5000
- Close aplikasi tersebut, atau
- Edit `app.py` line terakhir, ganti port:
  ```python
  app.run(debug=True, port=8080)  # Ganti 5000 ke 8080
  ```

### Problem: "Error parsing PDF"
**Solusi**:
- File PDF mungkin corrupt atau scanned image
- Try convert ke text-based PDF dulu
- Atau convert manual ke DOCX/TXT

### Problem: "No results to export"
**Solusi**:
- Pastikan sudah run screening process dulu
- Check ada error saat screening
- Refresh page dan try lagi

---

## 📞 Butuh Bantuan?

### Self-Help Resources
1. Baca **README.md** untuk dokumentasi lengkap
2. Check **troubleshooting section** di atas
3. Review sample CVs untuk understand format

### Technical Support
- Contact: IT Team CKD Otto Pharma
- Email: it-support@ckdottopharma.com
- Extension: 1234

---

## 📌 Checklist Sebelum Pakai

- [ ] Python sudah terinstall
- [ ] Run `python setup.py` berhasil
- [ ] File `job_config.json` sudah di-update
- [ ] CV files sudah siap (PDF/DOCX/TXT format)
- [ ] Web browser siap (Chrome/Firefox recommended)

---

## 🎉 Happy Screening!

System ini dibuat untuk **menghemat waktu HR** dalam screening CV.

**Before System:**
- Manual review 100 CVs: 2-3 hari
- Inconsistent evaluation
- Risk miss good candidates

**After System:**
- Auto screening 100 CVs: 5-10 menit
- Consistent scoring
- Ranked by relevance

**Result:** 
- ⏱️ Save 80% waktu screening
- 🎯 Focus interview pada top candidates
- 📊 Data-driven hiring decisions

---

**Version 1.0 | Last Updated: 2024**
**Developed for CKD Otto Pharma HR Team**
