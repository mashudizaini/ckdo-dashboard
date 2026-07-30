# CKDO Dashboard — Module & Feature Inventory (for UAT Script Preparation)

This document inventories every module/screen in the dashboard so it can be turned into a
User Acceptance Test (UAT) script. For each screen it lists: what data/charts it shows, the
filters/parameters a user can set, the actions available (Create/Edit/Delete/Upload/Export/etc.),
sub-tabs, and any validation, confirmation dialogs, or state-machine behavior worth writing a
specific test case for. Backend endpoints are noted briefly for traceability, not as the main
content — UAT cases should be written against the user-facing behavior.

**How to use this doc:** each `###` heading is a candidate for one or more UAT test-case groups
(happy path, filter combinations, empty states, validation/error states, destructive-action
confirmation, role/permission checks). The "Cross-cutting" section at the end lists concerns
that repeat across many modules so you don't have to write them out per-screen.

**Roles:** every module below is gated by a role (see the "Roles & Permissions" section for the
full matrix) — `admin` bypasses all role checks.

---

## Table of Contents

1. [IT](#1-it--dashboardit--role-it_staff) — role `it_staff`
2. [HRGA](#2-hrga--dashboardhr--role-hr_staff) — role `hr_staff`
3. [PAC](#3-pac--dashboardpac--role-pac_staff) — role `pac_staff`
4. [Accounting & Tax](#4-accounting--tax--dashboardaccounting--role-accounting_staff) — role `accounting_staff`
5. [Purchasing](#5-purchasing--dashboardpurchasing--role-purchasing_staff) — role `purchasing_staff`
6. [EIS](#6-eis--dashboardeis--role-management) — role `management` (ETL Admin sub-tab: `it_staff`)
7. [AI Tools](#7-ai-tools--ai--any-authenticated-user) — any authenticated user (KB management further role-gated)
8. [Cross-cutting UAT considerations](#8-cross-cutting-uat-considerations)
9. [Roles & Permissions matrix](#9-roles--permissions-matrix)

---

## 1. IT (`/dashboard/it`) — role `it_staff`

File: `frontend/src/pages/dashboard/IT.jsx` (single file, all 5 tabs) + `it_db_browser.py` router.

### 1.1 Oracle Server Monitoring
- **Data:** CPU/Memory/Swap % KPI cards, Server Status (Online/Error/Waiting + uptime), 3 rolling history charts (CPU/Memory/Load Average, last 30 samples), "Analysis & Recommendations" cards (Critical/Warning/Elevated/Normal per metric with narrative + recommended action), Top Processes table (CPU/Memory toggle), Oracle Sessions table (`v$session`).
- **Filters:** Auto-refresh interval (Off/30s/1m/2m); Top Processes CPU/Memory toggle.
- **Actions:**
  - **Refresh** (metrics + processes).
  - **Configure** → SSH credentials modal (Server IP, Port, Username, Password — blank password = keep existing) with **Test Connection** and **Save**.
  - **Load/Refresh Sessions**.
  - **Kill** session (per row) → confirmation modal shows SID/Serial#/User/Machine/Program/Event/Idle Time + the exact DDL to be run + red warning, Cancel / **Kill Session**. Disabled (with tooltip) for ACTIVE sessions with wait_class "User I/O".
  - Analysis cards may deep-link ("→ View Oracle Sessions") into the sessions panel.
- **Validation/notes:** Banner shown if SSH not configured; no client-side required-field check on the config form (blank IP/username silently accepted — worth a UAT case).

### 1.2 Oracle Tablespace Monitoring
- **Data:** Top-5 tablespaces bar chart (color-coded Normal/Warning/Critical) + detail table (Usage %, Used/Total GB, Status).
- **Actions:**
  - **Refresh**.
  - **Add File** (per tablespace) → modal: existing datafiles list, New File Location (path), Size + unit (MB/GB), AUTOEXTEND checkbox, live DDL preview, 2-step Form → Confirm ("cannot be undone" warning) → **Yes, Run DDL**.
  - **Resize File** (per tablespace) → modal: select existing datafile, Add Size + unit, live Current/+Added/New Size summary, DDL preview, same 2-step flow ("size cannot be reduced once resized" warning) → **Yes, Run DDL**.
- **Validation:** "Continue to Confirmation" disabled until required fields are filled/valid (file path non-empty & size>0 / datafile selected & add amount>0). DDL errors shown inline, return to form step.

### 1.3 Oracle Storage Monitoring
- **Data:** Server tabs (DB Server / App Server), stacked bar chart of top-8 mount points (used vs free), detail table with Usage % + Status.
- **Actions:** **Refresh** only (fetches both servers via SSH `df -P`). No create/edit/delete/export.
- **Validation/notes:** Per-server SSH error panel if one server fails while the other succeeds; guidance text before first load.

### 1.4 Postgre DB Browser — 3 sub-tabs
- **Objects** (default): browse Tables/Views/Sequences/Functions; per-table **Data** tab (paginated 50/row, per-row **Delete** with `confirm()`, PK-aware — delete hidden if no PK) and **Structure** tab (columns, PK, FKs, indexes). Search box + schema filter.
- **SQL Console**: free-form SQL textarea, **Run** button. Destructive statements (DROP/TRUNCATE, or DELETE/UPDATE without WHERE) are rejected by the API (400) and the UI reveals a red/amber **Run Anyway** (confirm=true) button. Result table truncated at 500 rows with a notice. Empty SQL blocked client-side.
- **Audit Log**: read-only table of every SQL Console execution + row deletion (Time, User, Type, SQL, Result OK/Failed, Rows affected, Duration), last 150 records, **Refresh** only.

### 1.5 Workflow Error
- **Data:** 3 KPI cards (Error/Suspended/Notified counts) + top-10 Oracle Workflow error/pending items table.
- **Actions:** **Refresh** only — read-only, no export.

---

## 2. HRGA (`/dashboard/hr`) — role `hr_staff`

Files: `HR.jsx` (main, 5 tabs) + `HRTodoList.jsx`, `HRCvScreening.jsx`, `EmployeeUpload.jsx`, `AttendanceUpload.jsx`, `LeaveUpload.jsx`.

### 2.1 Employee Data — 5 sub-tabs
- **Employee Summary**: Yearly Summary table (headcount by Dept × Year) → click a year to drill into Monthly Summary (Dept/Division/Team hierarchy, collapsible, one column/month) → click a monthly cell opens an **Employee List modal** filtered to that dept/division/team/month/year (with its own Department/Team/Education/Level/Status/Marital/Sex/As-of-Month-Year filters, row click → Employee Detail modal, **Download Excel**).
- **Employee List**: full employee master table (36+ columns). Clickable summary cards (Total/Active/Resign/Permanent/Contract/Probation) toggle as filters. Search + Filters popup (Department/Team/Status/Employment State/Joined-up-to Month&Year). Actions: **Add Employee** (modal, Full Name + NIK required), **Upload Employee** (inline panel, `.xls/.xlsx/.xlsm`, shows Total Read/Loaded/Replaced counts + Batch ID, sortable Upload History), **Refresh**, **Download Excel** (field-picker popup, checkboxes per column), row click → Employee Detail modal (edit, photo upload/remove, supervisor autocomplete, field-change History toggle, Submit requires Full Name), per-row **Resign** (modal: Resign Date required, optional Reason).
- **Employee Graph**: read-only charts (Headcount Trend 36mo, New Hires 24mo, Status/Gender/Marital pie charts). No filters/actions.
- **Organization Chart** — 2 views:
  - **Chart**: expandable org tree, search by name, Zoom In/Out, Expand/Collapse All, Refresh, **Download Image** (PNG), click node → Add/Edit/Delete modal (Full Name required; Delete has `confirm()` warning that direct reports get reassigned).
  - **Manage Structure**: flat sortable table, search + Department filter, **Import from Excel** (`.xlsx/.xlsm`, replaces the *entire* structure — flag for a "does it truly wipe existing data" UAT case), **Add Position** (same modal), row click → edit, per-row **Delete** with `confirm()`.
- **Turnover Report**: KPI cards + Resign/Turnover trend chart + 3 breakdown lists (by Dept/Job Level/Employee Status). Filters: Year, Month, Department, Team. Read-only (no export/upload).

### 2.2 Attendance Rate — 6 sub-tabs
- **Summary**: dept attendance chart, "Who's Off Today", gender/work-location widgets, monthly overall-rate bars, Target vs Achievement table. Filters: Department/Month/Year + **Reset**. **Refresh**.
- **Attendance Today**: date-specific summary cards (Total/Present/Absent, clickable → employee list with Check-In/Out/Notes), per-department table, date picker (+ "Reset to latest"). Sub-view **Team Summary**: Dept×Team table with per-dept and grand totals.
- **Detail**: type-ahead employee search (min 2 chars) → ID/Dept/Team/Location cards + Absence Records table + monthly mini chart. Read-only.
- **Attendance Leave**: Leave Distribution chart (by code: SL/AL/ALAB/EM/UL/ULBB/ML/BT, click a bar to filter), leave-records table. Filters: Year/Month/Leave Code/Organization/Search. Read-only (data only comes in via Upload sub-tab).
- **Working Calendar**: 12-month calendar grid (color-coded weekend/National/Collective/Company holiday), summary table (Calendar/Weekend/Holiday/Working days per month), holiday list. Year dropdown. **+ Add Holiday** (Date + Name required, Type dropdown), delete a holiday by clicking its calendar cell or list ✕ (**no confirmation dialog** — flag as a UAT case: accidental-delete risk), **Print Calendar** (`window.print()`).
- **Upload**: 3 independent upload widgets — Intercom attendance, Talenta attendance, Leave — all `.xlsx/.xlsm` only, drag/drop or click, optional notes, result panel (Total Read/New/Updated + Batch ID), sortable Upload History per source. Client-side extension check before upload.

### 2.3 To Do List (standalone module)
- **Data:** summary cards (Total/Not Started/In Progress/Completed/Overdue/Vendor Alert). **List View** (sortable table with "Xd left"/"Overdue" badges) or **e-Calendar View** (month grid with task-count badges, red for vendor alerts, side panel for selected day).
- **Filters:** Status, Role, Category, "Vendor Alert Only" checkbox, Search.
- **Actions:** **+ Add New Activity** (Title required; Assigned To is a type-ahead multi-select against Employee master; "Vendor/TOP related" checkbox auto-fills a 7-day alert), per-row **Mark complete**, **Edit**, **Delete** (`confirm()`), **Refresh**.

### 2.4 E-Recruitment (standalone module) — 4 sub-tabs
- **CV Screening**: job-requirement selector, summary cards, candidate table (expandable rows reveal Skills/Score Breakdown/AI Reasoning/Strengths/Red Flags/Interview Focus). Filters: Qualification, Recommendation, Search, AI provider (Standard on-prem / Premium Anthropic). Actions: **Upload CVs** (multi-file, `.pdf/.docx/.doc/.txt`), **Export** (`.xlsx`), row expand → **Mark as Hired** (Application Date + Offer Accept Date), per-row **Delete** (`confirm()`).
- **Detail**: Time-to-Hire/Time-to-Fill report per candidate. Filter: Position. Read-only.
- **Candidate Database**: all CVs ever processed, across all positions. Search only. Read-only.
- **Database Qualification**: position-requirements CRUD table. **+ New Position** (Title + Skills required), **Generate from JD** (paste text or upload `.pdf/.docx/.doc/.txt`, AI method: Standard/Premium/Template-no-AI → **Use as New Position** pre-fills the form), per-row **Delete** (`confirm()`, explicitly warns it also deletes all screened candidates for that position).

### 2.5 Budget Monitoring (locked to HR dept code "14")
- **Data:** summary cards (Budget/Actual/Remaining from Oracle GL), accounts table expandable into a per-month "kertas kerja" breakdown (Budget/Actual line items/Available/Reclass/Remain/Note).
- **Filters:** Year, Month.
- **Actions:** **Refresh from Oracle** (live query — not an upload), **Export Excel**, expand/collapse account rows (lazy-loaded + cached, **Retry** link on per-account load error).

### 2.6 e-Magazine
- **Data:** upload form + edition list table (sortable).
- **Actions:** **Upload New e-Magazine** (Edition Title + PDF required, PDF only, optional repeatable QR Code Label+URL rows), per-row **QR** (edit QR links inline), per-row **Delete** (`confirm()`), **Refresh**.

---

## 3. PAC (`/dashboard/pac`) — role `pac_staff`

File: `frontend/src/pages/dashboard/PAC.jsx`. Top-level tabs: **Business Plan**, **Budget Usage Report**, **BCA MT940 Upload**, **Exchange Rate**.

### 3.1 Business Plan — 5 sub-tabs
- **Managerial Objective**: per-year single document — Mission/Vision textareas, numbered Managerial Objectives list, Department × Objective strategy-mapping grid. **Save**, status toggle **Mark Draft/Mark Final**, **Print** (browser print, styled print-only view).
- **Strategy & Action Plan**: list of documents per year (scoped Department/Team/Role); **New**/select-to-edit; hierarchical Objective → Strategy (a,b,c) → Action (i,ii,iii) with add/remove at each level, collapsible sections. **Save**, **Delete** (`confirm()`), **Print** (landscape, merged-cell layout), **Upload Excel** (`.xlsx`, template "Strategy_Action Plan - Mashudi.xlsx").
- **Document List**: flat table of *all* Business Plan docs (Managerial Obj + Strategy Plan) for the year — Type/Year/Dept/Team/Role/Status/Updated. **Refresh**, per-row **Delete** (`confirm()`). Read-only otherwise (edit happens in the source tab).
- **Setup** — 3 sub-sub-tabs:
  - **Schedule**: per-year editable activity×department date grid, auto-computed "Actual Date" from prior year. **Save**, **Export Excel** (server-rendered).
  - **Guideline**: structured content editor (current vs previous year columns). **Save**, **Export PPT**.
  - **Outlook**: 3-section AI-assisted Markdown document (Global Economic/Indonesia Economic/Pharmaceutical Industry). Reference Materials + Report Format upload panels (multi-file, per-file **Convert** → AI-summarized "brief" with status badge pending/done/error, **Convert All**, per-file Download/Delete). **Generate with AI** (builds sections from converted briefs, warns if none converted yet). **Save**, **Export PPT**.
- **Simulation Data** — 6 independent per-year planning datasets (Purchase/Sales/Personnel/Manufacture/Investment/OPEX Plan), each with its own list, **New/Edit/Delete**, **Upload Excel** (specific template per type — see file names in code), and for Sales Plan additionally: per-plan **Export Excel** (Value/Unit) plus year-wide **Gross Sales Report** and **Sales Summary** exports; for Manufacture Plan additionally a year-wide **Detail Report** export.

### 3.2 Budget Usage Report
- **Filters:** Year* (number), Month (all/specific), Cost Center (partial text), Account Type (E/A/L/R/O), Ledger.
- **Actions:** **Search**/**Reset**, chart toggle **Bar Chart**/**Trend Line**, paginated table, client-side **Download Excel**.
- **Data:** KPI cards (Total Actual/Budget/Absorption %/Remaining Budget), live from Oracle GL_BALANCES vs Business Plan.

### 3.3 BCA MT940 Upload
- **Not a functional in-app screen** — a stub card linking out to an external app (`/apps/MT940_upload`, "Open App" button). Metric cards and file table are always empty placeholders. **Confirm with the user whether this belongs in UAT scope at all** — there's nothing to test inside the dashboard itself.

### 3.4 Exchange Rate
- **Source toggle:** Auto / Bank Indonesia (scrape) / ExchangeRate-API / Frankfurter-ECB (auto fallback chain in "Auto" mode).
- Featured currency cards + full table (code/name/denomination/Jual/Beli).
- **Refresh** (forces re-fetch, bypasses 4h cache — cache badge/timestamp shown otherwise).
- **Push ke Oracle EBS**: dialog to push selected currencies into `GL_DAILY_RATES_API` (Rate Date, Rate Type, Rate Source Jual/Beli/Tengah), per-currency success/error results.
- Error banner + "last known cache" fallback if all sources fail.

---

## 4. Accounting & Tax (`/dashboard/accounting`) — role `accounting_staff`

Files: `Accounting.jsx` (COGS/AP/AR tabs), `APAutoInvoice.jsx`, `FinancialStatement.jsx`.

### 4.1 AP Autoinvoice
End-to-end **state machine**: Upload PDF → OCR/AI extraction → Review/Edit → Validate → Insert to Oracle AP Interface → Run Import (APXIIMPT) → Attach PDF → Check Status. Staged in Postgres (`ap_invoice_stg`).
- **Layout:** left = invoice list (status pill, vendor, date, amount); right = detail panel.
- **Filters:** none (full list only) besides an OCR Provider selector (Standard On-Premise vs Premium Anthropic Claude) applied at upload time.
- **Actions (conditionally shown per status — the state machine itself is the main UAT surface here):**
  - **Upload PDF** (`.pdf` only, rejected otherwise) → auto-selects the new invoice.
  - **Edit** (status NEW/VALIDATED/ERROR) → inline header + line-item edit, per-line delete, **Save**/Cancel.
  - **Delete** (status NEW/VALIDATED/ERROR) → `confirm()`, also deletes the source PDF file.
  - **Validate/Re-validate** (status NEW/ERROR).
  - **Insert to Interface/Retry Interface** (status VALIDATED/PROCESSING/ERROR).
  - **Run APXIIMPT/Retry Import** (status INTERFACED/SUBMITTED/ERROR).
  - **Check Status** (status SUBMITTED/INTERFACED).
  - **Attach PDF** (status SUBMITTED/IMPORTED).
- **Status badges:** New(blue)/Validated(green)/Processing(yellow)/Interfaced(indigo)/Submitted(pink)/Imported(green)/Error(red), with a step-indicator (Upload→Validate→Interface→Import→Done).
- **UAT priority:** verify the correct action buttons appear/disappear per status, and that out-of-sequence actions correctly 409 rather than silently succeeding.

### 4.2 COGS Report — 3 sub-tabs
- **Material Transaction**: raw material-movement export (`MTL_MATERIAL_TRANSACTIONS`). Filters: Date From/To (default last 7 days), Organization, Item Number, Transaction Type, Max Rows (500/1000/2000/5000). **Load**, **Export CSV**. Warning banner if row count hits the limit.
- **Item Cost Component**: item cost breakdown (`CM_CMPT_DTL`, fixed org/cost-type). Filter: Period (month). **Load**, **Export CSV**.
- **Inventory RM PM**: monthly RM/PM inventory movement (begin balance + 14 qty-movement + 10 amount-movement columns + ending balance), grouped by Material Type with subtotals, per-row expandable movement detail. Filters: Period, "Include beginning balance" checkbox (noted as slower). **Load**, **Export CSV**, **Export Excel (Template)** (server-rendered, matches a specific reference layout).

### 4.3 AP Outstanding
- **Filters:** As of Date, Supplier, Operating Unit, Pay Status (All Outstanding/Not Paid/Partially Paid), Limit (200/500/1000/2000) + a client-side-only free-text filter on already-loaded rows.
- **Actions:** **Load**, **Export CSV**.
- **Data:** 5 KPI cards + table with payment-status-tinted rows (amber=Partially Paid, red=Not Paid).

### 4.4 AR Outstanding
- **Filters:** Customer, Invoice No, Invoice Date From/To, Status (Open/Closed/All), Limit + client-side free-text filter.
- **Actions:** **Load**, **Export CSV**.
- **Data:** 4 KPI cards + table with overdue-severity-tinted rows, Days Overdue shown as "+Nd"/"Today"/"Nd left".

### 4.5 Financial Statement — 4 sub-tabs (see also the more detailed spec already built this session)
- **Balance Sheet**: **Oracle/Excel source toggle** + **Upload Excel** button (parses the "Balance sheet" sheet). Period params: Single Period (Month+Year, Oracle-only; Year-only in Excel mode), Period From/Period To (Year-only, label "Dec YYYY", up to ~10-year range). **Growth column**: 1 prior period → delta+%; >1 → CAGR. Bold TOTAL rows + Assets=Liabilities+Equity check. **Refresh**, **Download Excel** (Oracle-source only).
- **Balance Sheet Detail**: same period controls, **Oracle-only** (no toggle/upload), drills to natural-account level.
- **Profit or Loss**: source toggle + upload (parses "Profit or loss" sheet). Period params: Period (current FY, Year-only) + Period From/Period To (range). **Chart** above the table: Gross Profit / Profit (Loss) Before Tax / Total Comprehensive Income (Loss) grouped bar, zero reference line. *Note: in Excel mode, NET SALES/COGS/EXPENSES line labels are whatever the uploaded file contains (verified to differ from Oracle's channel-based labels) — only section TOTALs are guaranteed comparable between sources.*
- **Profit or Loss Monthly**: source toggle + upload (parses "PL_monthly" sheet). Oracle mode: Period dropdown (MTD/YTD vs same month last year). Excel mode: no period picker — shows the single last-uploaded MTD/YTD snapshot with its own embedded date labels. 3-row grouped header (ACCOUNT/AMOUNT/dates/MTD-YTD), black bg + white grid.
- **UAT notes:** CAGR is "n/a" when the beginning value is 0 or sign flips; re-uploading a report type fully replaces the prior snapshot (no merge); Export to Excel is Oracle-source-only on all 4 tabs (deliberate scope cut, not a bug).

---

## 5. Purchasing (`/dashboard/purchasing`) — role `purchasing_staff`

File: `frontend/src/pages/dashboard/Purchasing.jsx` (single file, 6 tabs).

### 5.1 Open PR
- **Filters:** PR Status, Material Type, Currency, Exchange Rate Type, PR Number, Item Code, Item Description, Requestor, Date From/To (default Jan 1 CY → today).
- **Actions:** **Reset**, **Search**, sortable columns, paginated (8/page), **Download Excel**.
- **Data:** PR Status badges (Approved/In Process/Incomplete/Rejected), Aging badge (0 plain, 1–7d yellow, >7d red).

### 5.2 Purchase History — 6 sub-tabs, one shared filter panel
Shared filters: Organization, Year From*/To* (required, inline error if empty), Exchange Rate Type, Item Code, Item Description, Vendor Name, Manufacturer, Country of Origin, Category, Currency, Material Type, PO Number, Buyer.
- **Detail View** — flat PO-line table, sortable/paginated, **Download Excel**.
- **Detail View (Qty)** — currency-merged per-item Qty view (derived client-side, no extra call), **Download Excel**.
- **Summary** — KPI cards + By Year/Material Type/Category/Top-15 Supplier breakdowns.
- **Graph** — 5 Recharts (Yearly Spend, By Material Type, Top 10 Categories, Top 10 Suppliers, Yearly Spend Trend).
- **By Item (Pivot)** — item × year pivot (Value IDR / Qty), sortable/paginated, **Download Excel**.
- **By Supplier (Pivot)** — supplier × year pivot + Item/PO Count, sortable/paginated, **Download Excel**.
- **Actions:** **Reset**, **Search** (fires 3 parallel calls via `Promise.allSettled`), per-view **Download Excel**.

### 5.3 PO Price Analysis
- **Filters:** Item Code, Item Description, Supplier, Year From/To, Material Type, Max Data (1–500, default 10).
- **Actions:** **Search**, **Download Excel**.
- **Data:** live commodity reference panel (Platinum/Palladium/Gold/Silver via metals.dev, cached 1h — shows a config error if `METALS_API_KEY` unset), Average Purchase Price Trend line chart (explicit UI disclaimer: not IDR-normalized, cross-supplier currency comparison invalid), Price Detail table with up/down trend icon (last two years).

### 5.4 Monthly Spend
- **Filters:** Organization, Year From/To (default CY-2→CY), Currency, Material Type, Exchange Rate.
- **Actions:** **Reset**, **Search**, **Download Excel**, chart-mode toggle "Stacked by Type" vs "Year-over-Year".
- **Data:** 4 KPI cards + stacked/YoY chart + summary table.

### 5.5 Active Suppliers
- **Filters:** Organization, Year From/To (default CY-1→CY), Supplier Name, Material Type, Exchange Rate.
- **Actions:** **Reset**, **Search**, **Download Excel**.
- **Data:** 4 KPI cards, Top-10 stacked bar chart, ranked table with Share % bar.

### 5.6 Manufacturer Master
CRUD master-data screen (Item Code → Manufacturer/Country of Origin).
- **Actions:** **Refresh**, **Add** (modal: Organization*, Item Code* with type-ahead LOV search debounced 200ms/max 50 results, Manufacturer Name*, Country optional — client validates required fields), per-row **Delete** (`confirm("Delete this record?")`).
- **Validation:** inline red error banner on save/delete failure; empty state guidance text.

---

## 6. EIS (`/dashboard/eis`) — role `management`

File: `frontend/src/pages/dashboard/EIS.jsx` (single file, 9 tabs). Separate `eis` DB schema. Global controls: **Year**, **Period (month)**, and (Performance tab only) **Segment** (All/Local/Export/CMO).

### 6.1 Summary
KPI cards (Sales/Production Yield/Net Profit/Cashflow Achievement %), Sales closing estimation bar chart (BP vs Actual), Net Working Capital panel (+ DSO/DIO/DPO). Read-only.

### 6.2 Performance
Radial YTD achievement gauge, Monthly BP-vs-Actual bar chart, Cumulative achievement trend (100% reference line), EBIT-by-Product chart, Area sales performance bars. Filter: + Segment dropdown. Read-only.

### 6.3 Production
4 stat tiles (Yield/DIO/FG release time/Overtime ratio vs targets), Yield trend (95% target line), Overtime ratio chart (15% line), COGS ratio by product, DIO trend (150-day line). Read-only.

### 6.4 Expansion
5 stage-count tiles (pipeline stage funnel), Business Development Progress matrix (product × month, color-coded stage badge 1–5, current period column highlighted). Read-only.

### 6.5 Administration — 4 in-page sub-tabs
**Personnel** (headcount stacked bar, turnover line w/ 15%/20% reference lines) / **Financial** (net profit bar w/ red-if-negative, cashflow plan-vs-actual) / **Ratios** (DSO/DPO trend, NWC trend) / **Budget** (monthly plan-vs-actual). Filter: Year only (no period filter on this tab). Read-only.

### 6.6 Business Plan
CRUD for BP (budget/target) line items. Table: Type/Category/Sub-category/Jan–Dec/Total. Filters: Year + Plan Type dropdown.
- **Actions:** **Add entry** (inline form: Plan Type* + Category* required, Sub-category optional, 12 monthly numeric inputs with live Total, **Save** disabled until required fields filled), per-row **Delete** (`confirm()`).
- **Validation:** save failure shown as a browser `alert()`.

### 6.7 Daily Sales
Excel-upload-driven (no live ETL — parsed & cached as JSON, no DB). KPI cards (BP/Expectation Closing/Achievement %), Accumulated Sales per Working Day combo chart, large WD × Month pivot table (over-target green, negative red).
- **Filter:** Month selector (chart only; table always shows all 12).
- **Actions:** **Upload** (`.xlsx/.xls` only, expects a sheet named containing "Chart" + optionally a "daily sales"/"performance" sheet — 422 if missing/invalid) — replaces the entire cached dataset.

### 6.8 Data Upload
3 independent Excel uploaders feeding EIS fact tables not covered by automated ETL — **flag for extra scrutiny, this is one of the two "pipeline-feeding" admin sections**:
1. **Overtime** — expects specific label rows (422 if "Overtime Hour"/"Working Hour" rows missing), upserts `fact_overtime`.
2. **Business Plan Sales** — expects month-header + segment rows (Total/Local/CMO/Export); auto-detects year from cell values (warns if mismatched with selected Year dropdown); upserts `business_plan` + `fact_sales.bp_amount`.
3. **COGS** — complex multi-column parser (Market/Customer/Product/Price/Qty/Amount per month), auto-groups products, computes weighted-avg price, upserts `dim_product`+`fact_cogs`; response lists any skipped/unmatched product codes.
- Each has an independent Year selector, immediate upload (no confirm dialog), and its own success/error banner with backend-provided detail text.
- **UAT note:** no admin-only gate beyond the standard `management` role — any management user can overwrite these facts; worth a permission-scope discussion.

### 6.9 ETL Admin — role `it_staff` (stricter than the rest of EIS)
Operational control panel for 8 nightly ETL jobs pulling Oracle → `eis` schema.
- **Data:** ETL Schedule grid (frequency/time/source per job), Recent Job History (last 10 runs: Status badge, Started, Duration, Records, Parameter, Error message), click a row to expand an inline **data preview** (up to 50 rows of the imported fact table).
- **Actions:** **Run** (modal: Year* + optional Month, blank=all months → **Jalankan**/**Batal**), **Stop** (only on "running" rows, `confirm()` before revoking the Celery task), **Refresh**.
- **UAT priority:** confirm a `management`-only user (no `it_staff`) can see the nav item but is blocked (403) on every ETL Admin API call — this is the one place in EIS with a stricter role than the module-level gate. Also note: the running-task tracker is in-process memory only, so **Stop** may not work for jobs started before a backend restart.

---

## 7. AI Tools (`/ai/*`) — any authenticated user

Top-level (not nested under a dashboard module). KB-management actions are further restricted (see §9).

### 7.1 AI Chatbot (`/ai/chatbot`)
3 independent, concurrently-persisted chat threads (mode tabs): **Company Policy** (RAG over an internal Knowledge Base, department-scoped), **Oracle ERP** (tool-calling over predefined parameterized queries, not free-form SQL), **General** (plain LLM, no RAG/tools).
- **Inputs:** Provider selector (Standard On-Premise / Gemini) per active tab; "API Key Saya" modal to manage a personal Gemini key (validated live on save, masked hint only); message input + clickable suggestion chips (prefill, don't auto-send).
- **Knowledge Base management** (Company Policy tab, role-gated — see §9): add document (Source/Title/Department required + text-paste or file `.pdf/.docx/.doc/.txt`), document list with FILE/TEXT + department badges, per-doc **Delete** (`confirm()`), bulk **Delete text-paste entries** (`confirm()`, only shown if any exist), **Refresh**. Shows a distinct "RAG not configured" banner if `OLLAMA_API_URL` is unset.
- **Streaming/errors:** SSE response streaming with a distinct error bubble on failure (excluded from history sent back to the backend); source citations shown as badges in RAG mode.

### 7.2 Document Converter (`/ai/document-converter`)
Upload PDF/DOCX/image → structured Markdown (docling OCR + table recognition) → edit → download and/or send to Chatbot's Knowledge Base.
- **Inputs:** file dropzone (`.pdf/.docx/.doc/.png/.jpg/.jpeg`) OR pick an existing KB document to re-open/edit; metadata form (Source/Title auto-prefilled from filename/Department) for sending to KB.
- **Actions:** **Konversi ke Markdown** (disabled until file chosen), **Download .md**, **Kirim ke KB Chatbot**/**Simpan Perubahan** (label changes when editing an existing doc — save flow deletes old chunks then re-posts, so a failed delete aborts the save), Cancel-edit.
- **Streaming:** SSE `progress`/`page_result`/`done`/`error` events — markdown builds incrementally per page; can take minutes for scanned docs.

### 7.3 Meeting Notes (`/ai/meeting-notes`) — 2 tabs
- **New Recording**: Meeting Info form (all free text, no date/time validation) + Live Recording (mic Start/Stop, elapsed timer, handles HTTPS-required/permission-denied errors with a redirect-to-HTTPS button) OR Upload Audio (`audio/*`, max 100MB client-checked) → **1. Transcribe** (Whisper, on-prem only, no provider choice) → **2. Generate MOM** (provider: Standard On-Premise or Claude) → fully editable structured MOM (Department → Topic → Discussion Points/Action Plans, add/remove at every level) → **Save** / **Download .docx**. Transcript panel has "Open in tab" (bare read-only viewer at `/ai/meeting-notes/view/{id}`) and **Copy**.
- **History**: list of all recordings (Recorded/Uploaded badge, Error badge, MOM-ready badge), per-row **Transcript**/**Audio download**/**MOM download**/**Delete** (`confirm()`, deletes recording+audio+transcript+MOM together).
- **Validation/errors:** distinct HTTP statuses surfaced for GPU-service failures (504 timeout / 502 Whisper error / 503 connect error); Generate-MOM requires a non-empty transcript (400 otherwise).

---

## 8. Cross-cutting UAT considerations

- **Filter → Search/Load → sortable/paginated table → client-side Excel/CSV export** is the dominant pattern across Purchasing, Accounting (non-FS), and most report screens. A shared UAT checklist (empty filters, invalid date ranges, no-results state, export-button only-appears-after-load) covers most of these screens at once rather than needing bespoke cases per screen.
- **Confirmation dialogs are inconsistent** — most destructive actions use a browser `confirm()`/`window.confirm()`, but a few notably **don't**: deleting a holiday in HR's Working Calendar (click-to-delete, no dialog). Worth an explicit "accidental click" UAT case there.
- **Client-generated vs server-generated exports**: most "Download Excel/CSV" buttons build the file in the browser from already-loaded data (`xlsx` library) — a few are server-rendered against a specific template (Inventory RM PM's "Export Excel (Template)", all of PAC's Setup/Simulation exports, Financial Statement's Oracle-mode exports). Server-rendered exports are worth checking against the actual reference template layout, not just "a file downloads."
- **Upload file-type/structure validation** varies in strictness — some uploaders do rich structural validation with specific Indonesian error messages (EIS Data Upload, EIS Daily Sales, Financial Statement Excel parsers), others just check the file extension. Test both a well-formed template and a garbage file for each uploader.
- **State-machine screens** (AP Autoinvoice; ETL Admin's running/stopped jobs) are best tested by walking every legal transition once and attempting at least one illegal transition (expect a 409, not silent success or a crash).
- **Stub/placeholder screens**: PAC's BCA MT940 Upload is not implemented in-app (external link-out only) — confirm with the user whether it's in UAT scope.
- **Live external dependencies**: several screens depend on live systems that may be down/slow during UAT — Oracle EBS (most report screens), SSH to app/DB servers (IT module), GPU transcription/AI services (Meeting Notes), metals.dev (PO Price Analysis), Bank Indonesia/exchange-rate APIs (PAC Exchange Rate), Ollama/Gemini (AI Chatbot). Each of these should have an explicit "service unavailable" UAT case, not just the happy path.
- **Excel-upload "replace, not merge" behavior**: Financial Statement's Excel-source uploads, HR Org Structure's "Import from Excel", and EIS's Daily Sales upload all **fully replace** prior data on every upload — worth a specific "upload twice, confirm old data is gone" test per screen rather than assuming it's additive.

---

## 9. Roles & Permissions matrix

| Module | Sidebar/module-level role | Notable exceptions |
|---|---|---|
| IT | `it_staff` | — |
| HRGA | `hr_staff` | — |
| PAC | `pac_staff` | — |
| Accounting & Tax | `accounting_staff` | — |
| Purchasing | `purchasing_staff` | — |
| EIS | `management` | **ETL Admin** sub-tab requires `it_staff` on every API call, despite being reachable from the `management`-gated nav — a `management`-only user should see the tab but get 403s on all its actions |
| AI Tools | none (any authenticated user) | Knowledge Base management (add/delete documents, in both Chatbot and Document Converter) restricted to `it_staff, hr_staff, accounting_staff, pac_staff, purchasing_staff, admin`; bulk KB cleanup endpoints further restricted to `it_staff, admin` |

`admin` bypasses every role check above. Suggested UAT pass: for each module, test with (a) a user holding exactly the required role, (b) a user with no roles / a different module's role (expect redirect or 403), and (c) `admin`.
