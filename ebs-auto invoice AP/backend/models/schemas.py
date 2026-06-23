from pydantic import BaseModel
from typing import Optional, List
from datetime import date


class InvoiceLineSchema(BaseModel):
    line_num:         int
    line_type:        str = "ITEM"          # ITEM only; tax otomatis di EBS
    item_code:        Optional[str]
    description:      str
    qty:              float
    unit_price:       float
    line_amount:      float
    batch_no:         Optional[str]
    paking:           Optional[str]


class InvoiceHeaderSchema(BaseModel):
    invoice_num:       str
    invoice_date:      str
    vendor_name:       str
    payment_terms:     Optional[str]
    terms_date:        Optional[str]
    po_number:         Optional[str]
    so_number:         Optional[str]
    currency_code:     str = "IDR"
    subtotal:          float
    tax_amount:        float
    invoice_amount:    float
    source_file:       str
    tax_serial_number: Optional[str] = None
    lines:             List[InvoiceLineSchema]


class StagingStatusUpdate(BaseModel):
    stg_id:   int
    status:   str
    error_msg: Optional[str] = None


class InvoiceListResponse(BaseModel):
    stg_id:          int
    invoice_num:     str
    vendor_name:     str
    invoice_date:    Optional[str]
    invoice_amount:  Optional[float]
    status:          str
    error_msg:       Optional[str]
    source_file:     Optional[str]
    created_date:    Optional[str]
    processed_date:  Optional[str]
    ap_invoice_id:   Optional[int]
