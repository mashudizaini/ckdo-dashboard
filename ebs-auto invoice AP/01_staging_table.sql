-- ============================================================
-- XXCKD_AP_INVOICE_STG — Staging table AP Invoice Import
-- Oracle EBS 12.2.8 | CKDO | ORG_ID=81
-- ============================================================

-- Sequence untuk STG_ID
CREATE SEQUENCE XXCKD_AP_INVOICE_STG_S
    START WITH 1
    INCREMENT BY 1
    NOCACHE
    NOCYCLE;

-- Main staging table
CREATE TABLE XXCKD_AP_INVOICE_STG (

    -- ── Control columns ──────────────────────────────────────────
    STG_ID              NUMBER          NOT NULL,
    STATUS              VARCHAR2(20)    DEFAULT 'NEW' NOT NULL,
    -- Status values:
    --   NEW         : baru di-extract dari PDF
    --   VALIDATED   : vendor & PO ditemukan di EBS
    --   PROCESSING  : sedang insert ke AP interface tables
    --   INTERFACED  : APXIIMPT sudah di-submit
    --   IMPORTED    : invoice terbentuk di ap_invoices_all
    --   ERROR       : gagal, lihat ERROR_MSG
    ERROR_MSG           VARCHAR2(4000),
    SOURCE_FILE         VARCHAR2(500)   NOT NULL,       -- nama file PDF
    CREATED_DATE        DATE            DEFAULT SYSDATE,
    PROCESSED_DATE      DATE,

    -- ── Header ───────────────────────────────────────────────────
    INVOICE_NUM         VARCHAR2(50)    NOT NULL,
    INVOICE_DATE        VARCHAR2(20),                   -- DD/MM/YYYY dari PDF
    INVOICE_TYPE        VARCHAR2(20)    DEFAULT 'STANDARD',
    VENDOR_NAME         VARCHAR2(240),
    VENDOR_ID           NUMBER,                         -- diisi setelah lookup AP_SUPPLIERS
    VENDOR_SITE_ID      NUMBER,                         -- diisi setelah lookup AP_SUPPLIER_SITES_ALL
    VENDOR_SITE_CODE    VARCHAR2(50),
    PAYMENT_TERMS       VARCHAR2(50),
    TERMS_DATE          VARCHAR2(20),                   -- dari kolom Payment Terms di PDF
    PO_NUMBER           VARCHAR2(50),
    SO_NUMBER           VARCHAR2(50),
    CURRENCY_CODE       VARCHAR2(15)    DEFAULT 'IDR',
    INVOICE_AMOUNT      NUMBER,                         -- TOTAL incl tax → ke AP_INVOICES_INTERFACE
    SUBTOTAL            NUMBER,
    TAX_AMOUNT          NUMBER,

    -- ── Line items (JSON string) ──────────────────────────────────
    -- Disimpan sebagai JSON untuk simplisitas staging
    -- Format: [{"line_num":1,"line_type":"ITEM","item_code":"C40200-5G",...}]
    LINES_JSON          CLOB,

    -- ── AP Interface reference ───────────────────────────────────
    INTERFACE_INVOICE_ID    NUMBER,                     -- PK di AP_INVOICES_INTERFACE
    AP_INVOICE_ID           NUMBER,                     -- INVOICE_ID di ap_invoices_all setelah APXIIMPT
    CONC_REQUEST_ID         NUMBER,                     -- request ID dari FND_REQUEST

    CONSTRAINT XXCKD_AP_INV_STG_PK PRIMARY KEY (STG_ID),
    CONSTRAINT XXCKD_AP_INV_STG_STATUS_CK
        CHECK (STATUS IN ('NEW','VALIDATED','PROCESSING','INTERFACED','IMPORTED','ERROR'))
);

-- Index untuk status monitoring (tracker query)
CREATE INDEX XXCKD_AP_INV_STG_STATUS_IX
    ON XXCKD_AP_INVOICE_STG (STATUS, CREATED_DATE DESC);

CREATE INDEX XXCKD_AP_INV_STG_INVNUM_IX
    ON XXCKD_AP_INVOICE_STG (INVOICE_NUM);

-- ── Grants (jika schema terpisah dari APPS) ──────────────────────
-- GRANT SELECT, INSERT, UPDATE ON XXCKD_AP_INVOICE_STG TO APPS;
-- GRANT SELECT ON XXCKD_AP_INVOICE_STG_S TO APPS;

-- ── Verify ───────────────────────────────────────────────────────
SELECT table_name, num_rows
FROM   user_tables
WHERE  table_name = 'XXCKD_AP_INVOICE_STG';
