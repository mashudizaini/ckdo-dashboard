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
# The code in this instance is CKDO_PMAC, not the generic PMAC — found by
# etl_mart_item_cost's diagnostic on its first run (53,325 component rows
# under CKDO_PMAC for org 121, none under PMAC).
OPM_COST_METHOD = "CKDO_PMAC"
# How many months of costing periods to keep in core.fact_item_cost.
OPM_COST_HISTORY_MONTHS = 24

# Requisitions raised by these users are test/dummy data, excluded the same
# way etl_open_pr (the Dashboard's Open PR report) excludes them, so the two
# agree. SHERLIN's split PRs whose supplier is literally "ELLVIN" are dummy too.
PR_DUMMY_USERS = ("ELLVIN", "AFNI")

# Sales order types the Dashboard's sales ETL counts (etl_sales,
# etl_sales_orders): export orders are Export, SO-LOCAL lines of the toll-in
# line type are CMO, other SO-LOCAL lines are Local. Other order types
# (internal, returns) are not sales and are left out of the OM marts.
SO_ORDER_TYPES = ("SO-LOCAL", "SO-EXPORT")
SO_EXPORT_TYPE = "SO-EXPORT"
SO_CMO_LINE_TYPE = "SO-TOLL IN-LOCAL"

# GL: balances from this fiscal year on (the Financial Statement report goes
# back to 2015 for its annual columns, but chat questions are about recent
# years and gl_balances grows by one row per account combination per period).
GL_BALANCE_FROM_YEAR = 2020
# Journal lines kept in the mart: the current month plus this many before.
# GL_JE_LINES is the largest GL table and every subledger line carries an XLA
# lookup, so the window is what keeps the extract gentle on production EBS.
GL_JOURNAL_MONTHS = 13

# Guardrails for run_sql and every intent tool (blueprint section 7).
MAX_ROWS = 500
STATEMENT_TIMEOUT = "15s"

# One entry per mart in the blueprint's catalog (section 5). All eight
# phases are built; later phases are listed so the admin overview shows the whole
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
    "so_backlog": {
        "domain": "OM", "phase": 3, "built": True,
        "grain": "Baris SO yang masih open (belum closed / cancelled)",
        "description": "Order penjualan yang belum selesai: sisa qty & nilai belum dikirim, jadwal kirim, keterlambatan.",
        "sources": "OE_ORDER_HEADERS_ALL, OE_ORDER_LINES_ALL, OE_TRANSACTION_TYPES_TL",
        "source_jobs": ["etl_mart_om"],
        "unique_key": ["line_id"],
    },
    "so_shipment_status": {
        "domain": "OM", "phase": 3, "built": True,
        "grain": "Baris SO dengan status pengiriman (WSH delivery details)",
        "description": "Status kirim per baris SO: terkirim, staged/pick, backorder, siap rilis; nomor delivery dan tanggal ship confirm.",
        "sources": "WSH_DELIVERY_DETAILS, WSH_DELIVERY_ASSIGNMENTS, WSH_NEW_DELIVERIES",
        "source_jobs": ["etl_mart_om"],
        "unique_key": ["line_id"],
    },
    "sales_by_customer_item_month": {
        "domain": "OM", "phase": 3, "built": True,
        "grain": "Customer × item × bulan GL × mata uang × tipe bisnis (penjualan yang sudah diinvoice)",
        "description": "Penjualan terinvoice (RA) per customer, item, bulan: qty dan nilai IDR (kurs invoice), termasuk credit memo sebagai pengurang.",
        "sources": "RA_CUSTOMER_TRX_ALL, RA_CUSTOMER_TRX_LINES_ALL, RA_CUST_TRX_LINE_GL_DIST_ALL",
        "source_jobs": ["etl_mart_ar", "etl_mart_om"],
        "unique_key": ["row_key"],
    },
    "ar_aging": {
        "domain": "AR", "phase": 3, "built": True,
        "grain": "Payment schedule piutang yang masih open (INV, DM, CM)",
        "description": "Piutang usaha terbuka per jadwal, dengan aging dari jatuh tempo — sama dengan laporan AR Outstanding dashboard (kurs Corporate terbaru).",
        "sources": "AR_PAYMENT_SCHEDULES_ALL, RA_CUSTOMER_TRX_ALL, HZ_PARTIES, GL_DAILY_RATES",
        "source_jobs": ["etl_mart_ar"],
        "unique_key": ["payment_schedule_id"],
    },
    "ar_receipt": {
        "domain": "AR", "phase": 3, "built": True,
        "grain": "Penerimaan kas × status aplikasi × invoice yang dilunasi",
        "description": "Penerimaan kas dari customer dan ke invoice mana diaplikasikan, termasuk sisa unapplied / on-account / unidentified.",
        "sources": "AR_CASH_RECEIPTS_ALL, AR_RECEIVABLE_APPLICATIONS_ALL, AR_RECEIPT_METHODS",
        "source_jobs": ["etl_mart_ar"],
        "unique_key": ["row_key"],
    },
    "batch_status": {
        "domain": "OPM", "phase": 4, "built": True,
        "grain": "Batch produksi OPM (org 121)",
        "description": "Status batch, formula, produk, qty rencana vs aktual, jadwal rencana vs aktual, keterlambatan dan yield.",
        "sources": "GME_BATCH_HEADER, GME_MATERIAL_DETAILS, FM_FORM_MST_B",
        "source_jobs": ["etl_mart_opm"],
        "unique_key": ["batch_id"],
    },
    "batch_yield_variance": {
        "domain": "OPM", "phase": 4, "built": True,
        "grain": "Batch × baris produk / by-product",
        "description": "Qty rencana, standar formula, dan aktual per produk batch, selisih dan yield %.",
        "sources": "GME_MATERIAL_DETAILS",
        "source_jobs": ["etl_mart_opm"],
        "unique_key": ["material_detail_id"],
    },
    "batch_material_usage": {
        "domain": "OPM", "phase": 4, "built": True,
        "grain": "Batch × bahan (ingredient) × lot yang dikonsumsi",
        "description": "Pemakaian bahan standar formula vs aktual per batch, dan lot bahan yang dipakai (penelusuran lot → batch).",
        "sources": "GME_MATERIAL_DETAILS, MTL_MATERIAL_TRANSACTIONS, MTL_TRANSACTION_LOT_NUMBERS",
        "source_jobs": ["etl_mart_opm"],
        "unique_key": ["row_key"],
    },
    "gl_trial_balance": {
        "domain": "GL", "phase": 5, "built": True,
        "grain": "Akun × departemen × periode GL (ledger 2022, IDR)",
        "description": "Trial balance: saldo awal, mutasi debit/kredit, saldo akhir per akun dan departemen, dengan pos neraca / laba rugi.",
        "sources": "GL_BALANCES, GL_CODE_COMBINATIONS, FND_FLEX_VALUES",
        "source_jobs": ["etl_mart_gl"],
        "unique_key": ["row_key"],
    },
    "gl_journal_detail": {
        "domain": "GL", "phase": 5, "built": True,
        "grain": "Baris jurnal posted (13 bulan terakhir) + transaksi subledger asal",
        "description": "Detail jurnal GL: source, category, akun, departemen, debit/kredit IDR, dan transaksi subledger (invoice/receipt) di balik baris jurnal.",
        "sources": "GL_JE_HEADERS, GL_JE_LINES, XLA_AE_LINES, XLA_TRANSACTION_ENTITIES",
        "source_jobs": ["etl_mart_gl"],
        "unique_key": ["row_key"],
    },
    "pl_monthly": {
        "domain": "GL", "phase": 5, "built": True,
        "grain": "Pos laba rugi × departemen × periode GL",
        "description": "Laba rugi bulanan dengan mapping akun yang sama persis dengan laporan Financial Statement dashboard.",
        "sources": "GL_BALANCES + mapping akun Financial Statement (meta.gl_account_map)",
        "source_jobs": ["etl_mart_gl"],
        "unique_key": ["row_key"],
    },
    # ── Phase 7: finance close, Cash Management, Fixed Assets (library v2 12-13) ──
    "gl_period_status": {
        "domain": "GL", "phase": 7, "built": True,
        "grain": "Aplikasi × periode (GL, AP, AR, PO, INV org 121, OPM costing, FA)",
        "description": "Status periode tiap aplikasi (Open/Closed/Future/Frozen) dan apakah penyusutan FA sudah dijalankan.",
        "sources": "GL_PERIOD_STATUSES, ORG_ACCT_PERIODS, GMF_PERIOD_STATUSES, FA_DEPRN_PERIODS",
        "source_jobs": ["etl_mart_close", "etl_mart_fa"],
        "unique_key": ["row_key"],
    },
    "sla_gl_gap": {
        "domain": "GL", "phase": 7, "built": True,
        "grain": "Event / entry / jurnal yang belum sampai ke GL",
        "description": "Selisih subledger vs GL: event belum di-account, accounting error, entry draft, final belum transfer ke GL, jurnal GL belum posting.",
        "sources": "XLA_EVENTS, XLA_AE_HEADERS, XLA_AE_LINES, XLA_TRANSACTION_ENTITIES, GL_JE_HEADERS",
        "source_jobs": ["etl_mart_close"],
        "unique_key": ["row_key"],
    },
    "ar_autoinvoice_error": {
        "domain": "AR", "phase": 7, "built": True,
        "grain": "Baris interface AutoInvoice (× pesan error)",
        "description": "Baris RA_INTERFACE yang menunggu AutoInvoice atau ditolak, dengan pesan error dan nomor SO.",
        "sources": "RA_INTERFACE_LINES_ALL, RA_INTERFACE_ERRORS_ALL",
        "source_jobs": ["etl_mart_close"],
        "unique_key": ["row_key"],
    },
    "so_shipped_not_invoiced": {
        "domain": "OM", "phase": 7, "built": True,
        "grain": "Baris SO yang sudah dikirim tetapi belum ada invoice AR",
        "description": "SO terkirim belum jadi invoice: qty & nilai, tanggal kirim, umur, dan error AutoInvoice jika ada.",
        "sources": "OE_ORDER_LINES_ALL + RA_CUSTOMER_TRX_LINES_ALL + RA_INTERFACE_*",
        "source_jobs": ["etl_mart_om", "etl_mart_ar", "etl_mart_close"],
        "unique_key": ["line_id"],
    },
    "ce_unreconciled": {
        "domain": "CE", "phase": 7, "built": True,
        "grain": "Baris rekening koran atau transaksi sistem yang belum rekon",
        "description": "Rekonsiliasi bank: baris statement belum rekon, dan pembayaran AP / penerimaan AR / transfer bank yang belum muncul di statement (24 bulan). Tanpa nomor rekening.",
        "sources": "CE_STATEMENT_HEADERS, CE_STATEMENT_LINES, AP_CHECKS_ALL, AR_CASH_RECEIPTS_ALL, CE_CASHFLOWS",
        "source_jobs": ["etl_mart_close"],
        "unique_key": ["row_key"],
    },
    "fa_asset_register": {
        "domain": "FA", "phase": 7, "built": True,
        "grain": "Aset tetap × buku corporate",
        "description": "Daftar aset tetap: kategori, lokasi, tanggal mulai dipakai, harga perolehan, akumulasi penyusutan, nilai buku (NBV), status (aktif/CIP/retired/fully reserved).",
        "sources": "FA_ADDITIONS, FA_BOOKS, FA_CATEGORIES, FA_DISTRIBUTION_HISTORY, FA_LOCATIONS, FA_DEPRN_SUMMARY",
        "source_jobs": ["etl_mart_fa"],
        "unique_key": ["row_key"],
    },
    "fa_depreciation": {
        "domain": "FA", "phase": 7, "built": True,
        "grain": "Aset × periode FA (24 bulan terakhir)",
        "description": "Penyusutan per aset per periode: beban periode, YTD, akumulasi.",
        "sources": "FA_DEPRN_SUMMARY, FA_DEPRN_PERIODS",
        "source_jobs": ["etl_mart_fa"],
        "unique_key": ["row_key"],
    },
    # ── Phase 8: rest of the library v2 catalog (ext_sql.py) ──
    "master_lookup": {
        "domain": "MASTER", "phase": 8, "built": True,
        "grain": "Kode × nama (item, supplier, customer, akun, departemen)",
        "description": "Daftar kode dan nama untuk mencari kode dari nama sebagian (lookup_master).",
        "sources": "core.dim_item, AP/PO/AR/OM core, meta.gl_account_map, FND flex values",
        "source_jobs": ["etl_mart_ap", "etl_mart_ext"],
        "unique_key": ["row_key"],
    },
    "ap_invoice": {
        "domain": "AP", "phase": 8, "built": True,
        "grain": "Satu invoice AP (lunas, terbuka, cancelled)",
        "description": "Semua invoice supplier dengan status bayar, sisa, jatuh tempo berikutnya, pembayaran dan hold aktif.",
        "sources": "AP_INVOICES_ALL, AP_PAYMENT_SCHEDULES_ALL, AP_INVOICE_PAYMENTS_ALL, AP_HOLDS_ALL",
        "source_jobs": ["etl_mart_ap"],
        "unique_key": ["invoice_id"],
    },
    "po_shipment": {
        "domain": "PO", "phase": 8, "built": True,
        "grain": "Shipment PO (semua status)",
        "description": "Semua baris/shipment PO termasuk yang sudah closed: qty pesan, terima, tagih, batal, nilai IDR.",
        "sources": "PO_HEADERS_ALL, PO_LINES_ALL, PO_LINE_LOCATIONS_ALL",
        "source_jobs": ["etl_mart_po"],
        "unique_key": ["line_location_id"],
    },
    "po_approval_pending": {
        "domain": "PO", "phase": 8, "built": True,
        "grain": "PO / PR yang menunggu approval",
        "description": "Dokumen PO dan requisition berstatus In Process / Requires Reapproval / Incomplete, approver yang ditunggu dan lama menunggu.",
        "sources": "PO_HEADERS_ALL, PO_REQUISITION_HEADERS_ALL, PO_ACTION_HISTORY",
        "source_jobs": ["etl_mart_ext"],
        "unique_key": ["row_key"],
    },
    "ap_withholding": {
        "domain": "AP", "phase": 8, "built": True,
        "grain": "Distribusi withholding (PPh) invoice AP, 24 bulan",
        "description": "Potongan pajak (withholding) per invoice: kode pajak, tarif, nilai IDR, periode.",
        "sources": "AP_INVOICE_DISTRIBUTIONS_ALL (AWT), AP_AWT_TAX_RATES_ALL",
        "source_jobs": ["etl_mart_ext"],
        "unique_key": ["invoice_distribution_id"],
    },
    "so_order_line": {
        "domain": "OM", "phase": 8, "built": True,
        "grain": "Baris SO (semua status)",
        "description": "Semua baris sales order termasuk closed: qty pesan/kirim/invoice, delivery, lot, nomor invoice AR.",
        "sources": "OE_ORDER_LINES_ALL, WSH_DELIVERY_DETAILS, RA_CUSTOMER_TRX_LINES_ALL",
        "source_jobs": ["etl_mart_om"],
        "unique_key": ["line_id"],
    },
    "so_hold": {
        "domain": "OM", "phase": 8, "built": True,
        "grain": "Hold aktif pada SO (order atau line)",
        "description": "Sales order yang di-hold (credit hold, hold manual): nama hold, sejak kapan, komentar, nilai order.",
        "sources": "OE_ORDER_HOLDS_ALL, OE_HOLD_SOURCES_ALL, OE_HOLD_DEFINITIONS",
        "source_jobs": ["etl_mart_ext"],
        "unique_key": ["order_hold_id"],
    },
    "opm_item_cost": {
        "domain": "OPM", "phase": 8, "built": True,
        "grain": "Item × periode costing OPM (CKDO_PMAC)",
        "description": "Biaya aktual PMAC per item per periode costing, per komponen biaya.",
        "sources": "CM_CMPT_DTL, GMF_PERIOD_STATUSES",
        "source_jobs": ["etl_mart_item_cost"],
        "unique_key": ["row_key"],
    },
    "gl_budget_vs_actual": {
        "domain": "GL", "phase": 8, "built": True,
        "grain": "Jenis (budget/encumbrance/actual) × akun × departemen × periode",
        "description": "Budget, encumbrance dan realisasi per akun dan departemen (ledger 2022), tanda sesuai laporan (biaya dan pendapatan positif).",
        "sources": "GL_BALANCES (actual_flag B, E, A), GL_BUDGET_VERSIONS",
        "source_jobs": ["etl_mart_ext", "etl_mart_gl"],
        "unique_key": ["row_key"],
    },
    "sa_interface_error": {
        "domain": "SA", "phase": 8, "built": True,
        "grain": "Baris interface yang error / menunggu (AP, AR, GL, INV, RCV)",
        "description": "Error dan antrean open interface: invoice AP, AutoInvoice AR, GL interface, transaksi inventory, receiving. Hanya tim IT allowlist.",
        "sources": "AP_INVOICES_INTERFACE, AP_INTERFACE_REJECTIONS, GL_INTERFACE, MTL_TRANSACTIONS_INTERFACE, MTL_MATERIAL_TRANSACTIONS_TEMP, RCV_TRANSACTIONS_INTERFACE, PO_INTERFACE_ERRORS, RA_INTERFACE_*",
        "source_jobs": ["etl_mart_ext", "etl_mart_close"],
        "unique_key": ["row_key"],
    },
    # ── Phase 6: System Administration (blueprint v2 4.7) — restricted ──
    # Not reachable through any ebs-* group, ebs-management included: only
    # the SYSADMIN_ALLOWLIST emails below, through the sa_* tools, over the
    # llm_sa_ro role (see access.py and query.run(sa=True)).
    "sa_user": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "User EBS (FND_USER)",
        "description": "User EBS: status aktif, last login, karyawan terkait dan status karyawannya, flag user seeded, jumlah responsibility aktif.",
        "sources": "FND_USER, PER_ALL_PEOPLE_F, PER_PERIODS_OF_SERVICE",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["user_id"],
    },
    "sa_user_resp": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "User × responsibility (direct + indirect)",
        "description": "Responsibility yang dimiliki user, grant direct atau indirect (role UMX), tanggal mulai/akhir dan status aktif.",
        "sources": "FND_USER_RESP_GROUPS_DIRECT, FND_USER_RESP_GROUPS_INDIRECT, FND_RESPONSIBILITY_TL",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_resp_function": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Responsibility × fungsi efektif (setelah exclusion)",
        "description": "Fungsi (menu/form/halaman) yang bisa diakses sebuah responsibility, setelah exclusion fungsi dan menu. Hanya responsibility yang pernah di-assign ke user.",
        "sources": "FND_RESPONSIBILITY, FND_COMPILED_MENU_FUNCTIONS, FND_FORM_FUNCTIONS_VL, FND_RESP_FUNCTIONS",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_resp_request_group": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Responsibility × program / request set yang boleh dijalankan",
        "description": "Isi request group tiap responsibility: program concurrent, request set, atau semua program satu aplikasi.",
        "sources": "FND_REQUEST_GROUPS, FND_REQUEST_GROUP_UNITS, FND_CONCURRENT_PROGRAMS_VL, FND_REQUEST_SETS_VL",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_profile_value": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Profile option × level × nilai",
        "description": "Nilai profile option per level (Site, Application, Responsibility, User, ...). Profile berisi password/kredensial tidak pernah ditarik.",
        "sources": "FND_PROFILE_OPTIONS_VL, FND_PROFILE_OPTION_VALUES",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_login_audit": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Sesi login × responsibility × form (90 hari terakhir)",
        "description": "Riwayat login user: waktu masuk/keluar, responsibility dan form yang dibuka (detail hanya ada jika Sign-On:Audit Level di-set).",
        "sources": "FND_LOGINS, FND_LOGIN_RESPONSIBILITIES, FND_LOGIN_RESP_FORMS",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_concurrent_request": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Concurrent request (30 hari terakhir)",
        "description": "Concurrent request: program, user, responsibility, fase/status, waktu mulai/selesai, durasi, pesan penyelesaian, manager.",
        "sources": "FND_CONCURRENT_REQUESTS, FND_CONCURRENT_PROGRAMS_VL, FND_CONCURRENT_PROCESSES",
        "source_jobs": ["etl_mart_sa_ops", "etl_mart_sa"],
        "unique_key": ["request_id"],
    },
    "sa_concurrent_manager": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Concurrent manager (queue)",
        "description": "Status concurrent manager: proses target vs aktual, status kontrol, node, request yang sedang berjalan.",
        "sources": "FND_CONCURRENT_QUEUES_VL",
        "source_jobs": ["etl_mart_sa_ops"],
        "unique_key": ["queue_key"],
    },
    "sa_wf_open_notification": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Notifikasi workflow berstatus OPEN × penerima",
        "description": "Notifikasi workflow yang masih terbuka (approval tertahan): tipe, dokumen, penerima, lama menunggu, perlu respons atau FYI.",
        "sources": "WF_NOTIFICATIONS, WF_ITEMS, WF_MESSAGE_ATTRIBUTES",
        "source_jobs": ["etl_mart_sa_ops"],
        "unique_key": ["notification_id"],
    },
    "sa_sod_violation": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "User × aturan SoD yang dilanggar",
        "description": "Konflik segregation of duties: user aktif yang punya akses ke dua fungsi yang bentrok menurut meta.sod_rules, lewat responsibility apa.",
        "sources": "mart.sa_user_resp, mart.sa_resp_function, meta.sod_rules",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_patch": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Patch / bug fix yang diterapkan",
        "description": "Patch (nomor bug) yang sudah diterapkan ke instance EBS dan tanggalnya.",
        "sources": "AD_BUGS",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["row_key"],
    },
    "sa_form_personalization": {
        "domain": "SA", "phase": 6, "built": True,
        "grain": "Rule Forms Personalization aktif",
        "description": "Rule Forms Personalization yang aktif per form/fungsi, dengan event pemicu, kondisi dan jumlah action aktif.",
        "sources": "FND_FORM_CUSTOM_RULES, FND_FORM_CUSTOM_ACTIONS",
        "source_jobs": ["etl_mart_sa"],
        "unique_key": ["rule_id"],
    },
}

BUILT_MARTS = [name for name, m in MARTS.items() if m.get("built")]

# Blueprint section 7, "Pemetaan grup ke domain". Values are mart-name
# prefixes; "" matches every mart. Explicit names are used where a prefix
# would over-grant: warehouse gets the two stock marts but not inv_valuation
# (a Finance number), purchasing gets ap_open_invoice but not payment detail.
DOMAIN_BY_GROUP: dict[str, set[str]] = {
    "ebs-finance":    {"ap_", "ar_", "gl_", "pl_", "inv_valuation", "po_", "pr_", "sla_", "ce_", "fa_",
                       "so_shipped_not_invoiced", "batch_status", "opm_item_cost", "master_"},
    "ebs-purchasing": {"po_", "pr_", "ap_open_invoice", "master_"},
    "ebs-warehouse":  {"inv_onhand_lot", "inv_movement_daily", "master_"},
    "ebs-production": {"batch_", "inv_onhand_lot", "master_"},
    "ebs-sales":      {"so_", "sales_", "ar_aging", "ar_autoinvoice_error", "master_"},
    "ebs-management": {""},
}

EBS_GROUPS = list(DOMAIN_BY_GROUP)

# System Administration (blueprint v2 section 7, "Pengecualian domain System
# Administration"). The sa_* marts ignore DOMAIN_BY_GROUP — even
# ebs-management's "" prefix does not reach them — and open only to these
# emails. Kept in code on purpose: adding someone to a Keycloak group or to
# Setup > AI > EBS Chat Access must not be enough to read user, login and
# access data; changing this list takes a reviewed commit.
SA_PREFIX = "sa_"
SYSADMIN_ALLOWLIST = frozenset({
    "mashudi@ckd-otto.com",
    "utomo@ckd-otto.com",
    "itsupport@ckd-otto.com",
})
# The PostgreSQL role the sa_* tools read as. Only it is granted mart.sa_*;
# llm_ro / chat_readonly are not, so run_sql cannot read them even if every
# check above it failed (third layer).
SA_READER_ROLE = "llm_sa_ro"

# Rows the concurrent-request and login extracts keep.
SA_REQUEST_DAYS = 30
SA_LOGIN_DAYS = 90

GROUP_LABELS = {
    "ebs-finance": "Finance — AP, AR, GL, closing, bank, aset tetap, valuasi persediaan, PO",
    "ebs-purchasing": "Purchasing — PO, PR, hutang terbuka (tanpa detail pembayaran)",
    "ebs-warehouse": "Gudang — stok per lot & mutasi (tanpa valuasi)",
    "ebs-production": "Produksi — batch & stok per lot",
    "ebs-sales": "Sales — SO, penjualan, aging piutang",
    "ebs-management": "Manajemen — semua mart",
}
