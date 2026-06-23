-- Staging table for AP Invoice import (lives in PostgreSQL, NOT Oracle EBS)

CREATE TABLE IF NOT EXISTS ap_invoice_stg (
    stg_id              SERIAL PRIMARY KEY,
    status              VARCHAR(20)   NOT NULL DEFAULT 'NEW',
    error_msg           TEXT,
    source_file         VARCHAR(500),

    -- Header fields (extracted from PDF)
    invoice_num         VARCHAR(100)  NOT NULL,
    invoice_date        VARCHAR(20),
    vendor_name         VARCHAR(500),
    vendor_id           INTEGER,
    vendor_site_id      INTEGER,
    vendor_site_code    VARCHAR(100),
    payment_terms       VARCHAR(100),
    tax_serial_number   VARCHAR(50),
    terms_date          VARCHAR(20),
    po_number           VARCHAR(100),
    so_number           VARCHAR(100),
    currency_code       VARCHAR(10)   DEFAULT 'IDR',
    invoice_amount      NUMERIC(15,2) DEFAULT 0,
    subtotal            NUMERIC(15,2) DEFAULT 0,
    tax_amount          NUMERIC(15,2) DEFAULT 0,

    -- Line items as JSON array
    lines_json          TEXT,

    -- EBS interface tracking
    interface_invoice_id  BIGINT,
    ap_invoice_id         BIGINT,
    conc_request_id       BIGINT,

    created_date        TIMESTAMP     DEFAULT NOW(),
    processed_date      TIMESTAMP
);
