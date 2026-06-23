"""
pdf_extractor.py
Ekstrak data invoice dari PDF supplier menggunakan Claude Vision API.
Mendukung multi-page PDF: invoice, faktur pajak, DO, PO dalam satu file.
"""

import os
import base64
import json
import re
import fitz                          # PyMuPDF — PDF → image
import anthropic
from models.schemas import InvoiceHeaderSchema, InvoiceLineSchema


PROMPT = """This PDF contains multiple pages from a supplier document package.
Pages may include: Invoice, Faktur Pajak (tax invoice), Delivery Order (DO/Surat Jalan), Purchase Order (PO), or receipt stamps.

Extract all relevant data and return ONLY a valid JSON object, no explanation.

Required JSON structure:
{
  "invoice_num": "invoice number string",
  "invoice_date": "DD/MM/YYYY - printed date on the invoice page",
  "received_date": "DD/MM/YYYY - handwritten date on RECEIVED stamp/cap, or null",
  "vendor_name": "supplier company name issuing the invoice",
  "payment_terms": "payment terms from PURCHASE ORDER page (e.g. IMMEDIATE, 30 Days, Net 30, COD) or null",
  "terms_date": "payment due date DD/MM/YYYY or null",
  "po_number": "PO/Purchase Order number or null",
  "so_number": "SO/Sales Order number or null",
  "tax_serial_number": "nomor seri faktur pajak from FAKTUR PAJAK page or null",
  "currency": "IDR",
  "subtotal": 0.0,
  "tax": 0.0,
  "total": 0.0,
  "lines": [
    {
      "line_num": 1,
      "item_code": "item code or null",
      "description": "item description",
      "qty": 1.0,
      "unit_price": 0.0,
      "amount": 0.0,
      "batch": "batch number or null"
    }
  ]
}

IMPORTANT extraction rules:
- vendor_name: the company ISSUING the invoice (usually top-left header), NOT PT. CKD OTTO Pharmaceuticals (the buyer)
- received_date: PRIORITY - look carefully for handwritten date (written with pen/pulpen) near a rubber stamp that says "RECEIVED BY" or "DITERIMA". It may be written as DD/MM/YY or DD-MM-YYYY. This is critical. If not found, set null.
- payment_terms: look for "Payment Terms", "Terms", "Syarat Pembayaran" on the PURCHASE ORDER page. Common values: IMMEDIATE, 30 Days, Net 30, Net 60, COD. If no PO page or no terms found, set null.
- tax_serial_number: from FAKTUR PAJAK page, look for "Kode dan Nomor Seri Faktur Pajak" (format like 0400260017218722​8). If no Faktur Pajak page, set null.
- invoice_date: the printed/typed date on the invoice document itself
- All numeric values as plain numbers without thousand separators
- Return ONLY the JSON, no markdown, no explanation"""


def _pdf_to_images_base64(pdf_path: str) -> list[str]:
    """Convert ALL pages of PDF to base64 PNG images."""
    doc = fitz.open(pdf_path)
    images = []
    mat = fitz.Matrix(2.0, 2.0)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        images.append(base64.standard_b64encode(img_bytes).decode("utf-8"))
    doc.close()
    return images


def _call_claude_vision(images: list[str]) -> dict:
    """Kirim semua page images ke Claude Vision API, return parsed dict."""
    client = anthropic.Anthropic(
        api_key=os.getenv("ANTHROPIC_API_KEY")
    )

    content = []
    for i, img in enumerate(images):
        content.append({
            "type": "text",
            "text": f"--- Page {i+1} of {len(images)} ---",
        })
        content.append({
            "type": "image",
            "source": {
                "type":       "base64",
                "media_type": "image/png",
                "data":       img,
            },
        })
    content.append({"type": "text", "text": PROMPT})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    return json.loads(raw)


def extract_invoice(pdf_path: str, source_file: str) -> InvoiceHeaderSchema:
    """
    Entry point: baca semua page PDF → Claude Vision → return InvoiceHeaderSchema.
    """
    images = _pdf_to_images_base64(pdf_path)

    data = _call_claude_vision(images)

    invoice_num = data.get("invoice_num", "").strip()
    if not invoice_num:
        raise ValueError("Invoice Number tidak ditemukan")

    vendor_name = data.get("vendor_name", "").strip()
    if not vendor_name:
        raise ValueError("Vendor Name tidak ditemukan")

    from datetime import datetime
    # Priority: received_date (handwritten on stamp) > invoice_date > current date
    invoice_date = data.get("received_date") or data.get("invoice_date") or datetime.today().strftime("%d/%m/%Y")

    lines = []
    for i, ln in enumerate(data.get("lines", []), start=1):
        qty    = float(ln.get("qty", 1) or 1)
        price  = float(ln.get("unit_price", 0) or 0)
        amount = float(ln.get("amount", 0) or 0) or (qty * price)

        lines.append(InvoiceLineSchema(
            line_num    = ln.get("line_num", i),
            line_type   = "ITEM",
            item_code   = ln.get("item_code") or None,
            description = ln.get("description", ""),
            qty         = qty,
            unit_price  = price,
            line_amount = amount,
            batch_no    = ln.get("batch") or None,
            paking      = None,
        ))

    if not lines:
        raise ValueError("Line items tidak ditemukan")

    subtotal       = float(data.get("subtotal", 0) or 0)
    tax_amount     = float(data.get("tax", 0) or 0)
    invoice_amount = float(data.get("total", 0) or 0) or (subtotal + tax_amount)

    return InvoiceHeaderSchema(
        invoice_num      = invoice_num,
        invoice_date     = invoice_date,
        vendor_name      = vendor_name,
        payment_terms    = data.get("payment_terms") or "30 Days",
        terms_date       = data.get("terms_date"),
        po_number        = data.get("po_number"),
        so_number        = data.get("so_number"),
        currency_code    = data.get("currency", "IDR"),
        subtotal         = subtotal,
        tax_amount       = tax_amount,
        invoice_amount   = invoice_amount,
        source_file      = source_file,
        tax_serial_number = data.get("tax_serial_number"),
        lines            = lines,
    )
