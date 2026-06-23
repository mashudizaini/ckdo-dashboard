"""
debug.py — POST /debug/extract
Upload PDF dan lihat raw extraction dari pdfplumber.
Gunakan untuk diagnosa masalah parsing saja.
"""

import os
import shutil
import pdfplumber
from fastapi import APIRouter, UploadFile, File
from config import UPLOAD_DIR

router = APIRouter(prefix="/debug", tags=["Debug"])


@router.post("/extract")
async def debug_extract(file: UploadFile = File(...)):
    """Return raw pdfplumber extraction — tables + text."""
    file_path = os.path.join(UPLOAD_DIR, f"debug_{file.filename}")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    result = {"tables": [], "raw_text": ""}
    try:
        with pdfplumber.open(file_path) as pdf:
            page = pdf.pages[0]
            result["raw_text"] = page.extract_text() or ""
            tables = page.extract_tables()
            for i, table in enumerate(tables):
                result["tables"].append({
                    "table_index": i,
                    "rows": table
                })
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

    return result
