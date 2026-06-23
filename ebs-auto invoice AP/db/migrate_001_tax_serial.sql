-- Run this if PostgreSQL container already exists (column not in original schema)
ALTER TABLE ap_invoice_stg ADD COLUMN IF NOT EXISTS tax_serial_number VARCHAR(50);
