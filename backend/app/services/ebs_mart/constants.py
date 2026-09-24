"""EBS environment constants, the mart registry, and the group -> domain map."""

# Blueprint section 1: constants used throughout. org_id 81 is also
# ap_invoice_service.EBS_ORG_ID; organization_id 121 is the process
# (OPM) org that accounting_service already filters mtl_material_transactions by.
EBS_OPERATING_UNIT_ID = 81
EBS_LEDGER_ID = 2022
EBS_PROCESS_ORG_ID = 121
EBS_COA_ID = 50388
EBS_GL_CALENDAR = "CKDO_GL_CAL"
EBS_FUNCTIONAL_CURRENCY = "IDR"

# Same rules as the Dashboard's AP Outstanding report
# (accounting_service.AccountingService), so a chat answer and the report
# agree by construction — blueprint principle 1, "angka chat = angka
# dashboard". Liability accounts only (segment4), and invoices dated on or
# before the legacy cutoff are treated as settled: their payment
# applications were never fully recorded in Oracle, so Oracle still shows
# them open although they were paid.
AP_COA_WHITELIST = (
    "212111", "212112", "212121", "212122",
    "212211", "212212", "212221", "212222",
)
AP_LEGACY_PAID_CUTOFF = "2021-12-31"

# Inventory category set used everywhere else in this app (purchasing_service,
# etl_po_lines) to classify items.
INVENTORY_CATEGORY_SET = "CKDO Inventory"

# OPM cost method whose component costs value org 121's stock (blueprint 4.3:
# "Biaya OPM ada di CM_CMPT_DTL per item, periode, dan cost type (PMAC)").
OPM_COST_METHOD = "PMAC"
# How many months of costing periods to keep in core.fact_item_cost.
OPM_COST_HISTORY_MONTHS = 24

# Requisitions raised by these users are test/dummy data, excluded the same
# way etl_open_pr (the Dashboard's Open PR report) excludes them, so the two
# agree. SHERLIN's split PRs whose supplier is literally "ELLVIN" are dummy too.
PR_DUMMY_USERS = ("ELLVIN", "AFNI")

# Guardrails for run_sql and every intent tool (blueprint section 7).
MAX_ROWS = 500
STATEMENT_TIMEOUT = "15s"

# One entry per mart in the blueprint's catalog (section 5). Phases 1 and 2
# are built; later phases are listed so the admin overview shows the whole
# roadmap and find_marts can say "not available yet" instead of nothing.
#
#   source_jobs: eis.etl_job_log job names whose last successful run is the
#                mart's as_of. A mart is only as fresh as its oldest input.
MARTS: dict[str, dict] = {
    "ap_open_invoice": {
        "domain": "AP", "phase": 1, "built": True,
        "grain": "Payment schedule invoice supplier yang masih outstanding",
        "description": "Hutang usaha terbuka per jadwal pembayaran, dengan umur hutang (aging) dan hari lewat jatuh tempo.",
        "sources": "AP_INVOICES_ALL, AP_PAYMENT_SCHEDULES_ALL, AP_SUPPLIERS",
        "source_jobs": ["etl_mart_ap"],
        "unique_key": ["invoice_id", "payment_num"],
    },
    "ap_payment_history": {
        "domain": "AP", "phase": 1, "built": True,
        "grain": "Satu pembayaran yang diaplikasikan ke satu invoice",
        "description": "Riwayat pembayaran invoice supplier: nomor dokumen bayar, tanggal, metode, nilai.",
        "sources": "AP_INVOICE_PAYMENTS_ALL, AP_CHECKS_ALL",
        "source_jobs": ["etl_mart_ap"],
        "unique_key": ["invoice_payment_id"],
    },
    "ap_invoice_hold": {
        "domain": "AP", "phase": 1, "built": True,
        "grain": "Hold aktif pada satu invoice",
        "description": "Invoice supplier yang sedang di-hold (belum di-release) beserta alasan hold.",
        "sources": "AP_HOLDS_ALL",
        "source_jobs": ["etl_mart_ap"],
        "unique_key": ["hold_id"],
    },
    "inv_onhand_lot": {
        "domain": "INV", "phase": 1, "built": True,
        "grain": "Item × subinventory × locator × lot (org 121)",
        "description": "Stok on-hand per lot dengan tanggal kedaluwarsa, sisa hari ke ED, dan klasifikasi subinventory (GOOD/REJECT/QUARANTINE).",
        "sources": "MTL_ONHAND_QUANTITIES_DETAIL, MTL_LOT_NUMBERS, MTL_SECONDARY_INVENTORIES",
        "source_jobs": ["etl_mart_inventory"],
        "unique_key": ["row_key"],
    },
    "inv_movement_daily": {
        "domain": "INV", "phase": 1, "built": True,
        "grain": "Item × tanggal × tipe transaksi × subinventory",
        "description": "Mutasi stok harian (masuk/keluar) per item dan tipe transaksi.",
        "sources": "MTL_MATERIAL_TRANSACTIONS (via eis.fact_inventory_txn)",
        "source_jobs": ["etl_inventory_txn"],
        "unique_key": ["row_key"],
    },
    "inv_valuation": {
        "domain": "INV", "phase": 2, "built": True,
        "grain": "Item × klasifikasi subinventory (stok saat ini × biaya PMAC periode costing terakhir)",
        "description": "Nilai persediaan org 121 dengan biaya OPM PMAC (CM_CMPT_DTL), bukan standard cost. Qty = stok on-hand saat ini.",
        "sources": "CM_CMPT_DTL, GMF_PERIOD_STATUSES, CM_MTHD_MST + mart.inv_onhand_lot",
        "source_jobs": ["etl_mart_inventory", "etl_mart_item_cost"],
        "unique_key": ["row_key"],
    },
    "po_outstanding": {
        "domain": "PO", "phase": 2, "built": True,
        "grain": "Shipment PO approved yang belum diterima penuh",
        "description": "Sisa PO yang belum diterima (qty & nilai), tanggal janji kirim, dan status keterlambatan.",
        "sources": "PO_HEADERS_ALL, PO_LINES_ALL, PO_LINE_LOCATIONS_ALL",
        "source_jobs": ["etl_mart_po"],
        "unique_key": ["line_location_id"],
    },
    "po_receipt_vs_invoice": {
        "domain": "PO", "phase": 2, "built": True,
        "grain": "Distribution PO dengan qty order / terima / tagih (status 3-way match)",
        "description": "Apakah PO sudah diterima dan sudah ditagih, invoice yang dicocokkan, dan penerimaan yang belum ditagih (uninvoiced receipts).",
        "sources": "PO_DISTRIBUTIONS_ALL, PO_LINE_LOCATIONS_ALL, AP_INVOICE_DISTRIBUTIONS_ALL",
        "source_jobs": ["etl_mart_po"],
        "unique_key": ["po_distribution_id"],
    },
    "pr_pending": {
        "domain": "PO", "phase": 2, "built": True,
        "grain": "Baris PR approved yang belum dibuatkan PO",
        "description": "Purchase requisition yang sudah approved tetapi belum menjadi PO, dengan lama menunggu.",
        "sources": "PO_REQUISITION_HEADERS_ALL, PO_REQUISITION_LINES_ALL",
        "source_jobs": ["etl_mart_po"],
        "unique_key": ["requisition_line_id"],
    },
    "so_backlog": {"domain": "OM", "phase": 3, "built": False, "grain": "SO line yang masih open",
                   "description": "Backlog sales order.", "sources": "OE_ORDER_LINES_ALL", "source_jobs": []},
    "so_shipment_status": {"domain": "OM", "phase": 3, "built": False, "grain": "SO line + status delivery",
                           "description": "Status pengiriman SO.", "sources": "WSH_DELIVERY_DETAILS", "source_jobs": []},
    "sales_by_customer_item_month": {"domain": "OM", "phase": 3, "built": False, "grain": "Customer × item × bulan",
                                     "description": "Penjualan per customer, item, bulan.", "sources": "RA_CUSTOMER_TRX_LINES_ALL", "source_jobs": []},
    "ar_aging": {"domain": "AR", "phase": 3, "built": False, "grain": "Payment schedule AR outstanding + bucket",
                 "description": "Aging piutang.", "sources": "AR_PAYMENT_SCHEDULES_ALL", "source_jobs": []},
    "ar_receipt": {"domain": "AR", "phase": 3, "built": False, "grain": "Penerimaan kas + aplikasi",
                   "description": "Penerimaan kas customer.", "sources": "AR_CASH_RECEIPTS_ALL, AR_RECEIVABLE_APPLICATIONS_ALL", "source_jobs": []},
    "batch_status": {"domain": "OPM", "phase": 4, "built": False, "grain": "Batch produksi",
                     "description": "Status batch produksi.", "sources": "GME_BATCH_HEADER", "source_jobs": []},
    "batch_yield_variance": {"domain": "OPM", "phase": 4, "built": False, "grain": "Batch × produk",
                             "description": "Plan vs actual, yield %.", "sources": "GME_MATERIAL_DETAILS", "source_jobs": []},
    "batch_material_usage": {"domain": "OPM", "phase": 4, "built": False, "grain": "Batch × ingredient × lot",
                             "description": "Pemakaian bahan standar vs aktual.", "sources": "GME_MATERIAL_DETAILS, FM_MATL_DTL", "source_jobs": []},
    "gl_trial_balance": {"domain": "GL", "phase": 5, "built": False, "grain": "Akun × periode",
                         "description": "Trial balance ledger 2022.", "sources": "GL_BALANCES, GL_CODE_COMBINATIONS", "source_jobs": []},
    "gl_journal_detail": {"domain": "GL", "phase": 5, "built": False, "grain": "Baris jurnal posted",
                          "description": "Detail jurnal GL.", "sources": "GL_JE_HEADERS, GL_JE_LINES", "source_jobs": []},
    "pl_monthly": {"domain": "GL", "phase": 5, "built": False, "grain": "Pos laba rugi × bulan",
                   "description": "Laba rugi bulanan.", "sources": "gl_trial_balance + mapping", "source_jobs": []},
}

BUILT_MARTS = [name for name, m in MARTS.items() if m.get("built")]

# Blueprint section 7, "Pemetaan grup ke domain". Values are mart-name
# prefixes; "" matches every mart. Explicit names are used where a prefix
# would over-grant: warehouse gets the two stock marts but not inv_valuation
# (a Finance number), purchasing gets ap_open_invoice but not payment detail.
DOMAIN_BY_GROUP: dict[str, set[str]] = {
    "ebs-finance":    {"ap_", "ar_", "gl_", "pl_", "inv_valuation", "po_", "pr_"},
    "ebs-purchasing": {"po_", "pr_", "ap_open_invoice"},
    "ebs-warehouse":  {"inv_onhand_lot", "inv_movement_daily"},
    "ebs-production": {"batch_", "inv_onhand_lot"},
    "ebs-sales":      {"so_", "sales_", "ar_aging"},
    "ebs-management": {""},
}

EBS_GROUPS = list(DOMAIN_BY_GROUP)

GROUP_LABELS = {
    "ebs-finance": "Finance — AP, AR, GL, valuasi persediaan, PO",
    "ebs-purchasing": "Purchasing — PO, PR, hutang terbuka (tanpa detail pembayaran)",
    "ebs-warehouse": "Gudang — stok per lot & mutasi (tanpa valuasi)",
    "ebs-production": "Produksi — batch & stok per lot",
    "ebs-sales": "Sales — SO, penjualan, aging piutang",
    "ebs-management": "Manajemen — semua mart",
}
