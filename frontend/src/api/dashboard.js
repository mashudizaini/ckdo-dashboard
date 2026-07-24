/**
 * Dashboard API calls
 * ─────────────────────────────────────────
 * Untuk menambahkan modul baru:
 *   1. Tambahkan object baru di sini
 *   2. Buat page di src/pages/dashboard/NamaModul.jsx
 *   3. Daftarkan route di App.jsx
 */
import api from "./client";

export const itApi = {
  getSummary:       () => api.get("/dashboard/it/summary"),
  getServers:       () => api.get("/dashboard/it/servers"),
  getTickets:       () => api.get("/dashboard/it/tickets"),
  getWeeklyReport:  () => api.get("/dashboard/it/weekly-report"),

  // Server Monitoring
  getServerConfig:  () => api.get("/dashboard/it/server-monitoring/config"),
  saveServerConfig: (cfg) => api.post("/dashboard/it/server-monitoring/config", cfg),
  testConnection:   () => api.get("/dashboard/it/server-monitoring/test"),
  getServerMetrics:  () => api.get("/dashboard/it/server-monitoring/metrics"),
  getTopProcesses:   () => api.get("/dashboard/it/server-monitoring/top-processes"),

  // Other sections
  getOracleSessions:       () => api.get("/dashboard/it/oracle-sessions"),
  killOracleSession:       (body) => api.post("/dashboard/it/oracle-kill-session", body),

  getTablespace:           () => api.get("/dashboard/it/tablespace-usage"),
  getTablespaceDatafiles:  (ts) => api.get("/dashboard/it/tablespace-datafiles", { params: { tablespace_name: ts } }),
  addTablespaceDatafile:   (body) => api.post("/dashboard/it/tablespace-add-datafile", body),
  resizeTablespaceDatafile:(body) => api.post("/dashboard/it/tablespace-resize-datafile", body),
  getDiskUsage:     () => api.get("/dashboard/it/disk-usage"),
  getPendingJobs:   () => api.get("/dashboard/it/pending-jobs"),
  getWorkflowError: () => api.get("/dashboard/it/workflow-error"),

  // Database Browser (PostgreSQL — ckdo_dashboard)
  getDbObjects:   ()                     => api.get("/dashboard/it/db-browser/objects"),
  getDbStructure: (schema, table)        => api.get(`/dashboard/it/db-browser/objects/${schema}/${table}/structure`),
  getDbData:      (schema, table, params) => api.get(`/dashboard/it/db-browser/objects/${schema}/${table}/data`, { params }),
  deleteDbRow:    (schema, table, pk)    => api.delete(`/dashboard/it/db-browser/objects/${schema}/${table}/rows`, { data: { pk } }),
  runDbQuery:     (body)                 => api.post("/dashboard/it/db-browser/query", body),
  getDbAuditLog:  (limit)                => api.get("/dashboard/it/db-browser/audit-log", { params: { limit } }),
};

export const hrApi = {
  getSummary: () => api.get("/dashboard/hr/summary"),
  getEmployees: (params) => api.get("/dashboard/hr/employees", { params }),
  getEmployee:  (userId) => api.get(`/dashboard/hr/employees/${userId}`),
  createEmployee: (data)         => api.post("/dashboard/hr/employees", data),
  updateEmployee: (userId, data) => api.put(`/dashboard/hr/employees/${userId}`, data),
  resignEmployee: (userId, data) => api.post(`/dashboard/hr/employees/${userId}/resign`, data),
  getAttendance: (params) => api.get("/dashboard/hr/attendance", { params }),
  uploadLeave:     (form) => api.post("/dashboard/hr/leave/upload", form, { headers: { "Content-Type": undefined } }),
  getLeaveHistory: ()     => api.get("/dashboard/hr/leave/history"),
  getLeaveData:    (p)    => api.get("/dashboard/hr/leave/data", { params: p }),
  getLeaveSummary: (p)    => api.get("/dashboard/hr/leave/summary", { params: p }),
  getLeaveOrgs:    ()     => api.get("/dashboard/hr/leave/organizations"),
  getLeaveEmployeeDetail: (id, year) => api.get(`/dashboard/hr/leave/employee/${id}/detail`, { params: { year } }),
  getCalendarHolidays: (y) => api.get("/dashboard/hr/calendar/holidays", { params: { year: y } }),
  addCalendarHoliday:  (d) => api.post("/dashboard/hr/calendar/holidays", d),
  deleteCalendarHoliday: (id) => api.delete(`/dashboard/hr/calendar/holidays/${id}`),
  getCalendarSummary:  (y) => api.get("/dashboard/hr/calendar/summary", { params: { year: y } }),
  getTodoTasks:    (p)     => api.get("/dashboard/hr/todo/tasks", { params: p }),
  getTodoSummary:  ()      => api.get("/dashboard/hr/todo/summary"),
  getTodoActiveAlerts: ()  => api.get("/dashboard/hr/todo/active-alerts"),
  createTodoTask:  (d)     => api.post("/dashboard/hr/todo/tasks", d),
  updateTodoTask:  (id, d) => api.put(`/dashboard/hr/todo/tasks/${id}`, d),
  deleteTodoTask:  (id)    => api.delete(`/dashboard/hr/todo/tasks/${id}`),
  getEmployeeNames: ()     => api.get("/dashboard/hr/employees/names"),
  getOrgChart:     ()      => api.get("/dashboard/hr/employees/org-chart"),
  setSupervisor:   (userId, supervisorId) => api.patch(`/dashboard/hr/employees/${userId}/supervisor`, { supervisor_id: supervisorId }),
  getCvJobs:       ()       => api.get("/dashboard/hr/cv-screening/jobs"),
  createCvJob:     (d)      => api.post("/dashboard/hr/cv-screening/jobs", d),
  deleteCvJob:     (id)     => api.delete(`/dashboard/hr/cv-screening/jobs/${id}`),
  getCvCandidates: (id, p)  => api.get(`/dashboard/hr/cv-screening/jobs/${id}/candidates`, { params: p }),
  deleteCvCandidate: (id)   => api.delete(`/dashboard/hr/cv-screening/candidates/${id}`),
  getCvStats:      (id)     => api.get(`/dashboard/hr/cv-screening/jobs/${id}/stats`),
  exportCvExcel:   (id)     => `/api/v1/dashboard/hr/cv-screening/jobs/${id}/export`,
  uploadCvJd:      (form)   => api.post("/dashboard/hr/cv-screening/jd/upload", form, { headers: { "Content-Type": undefined } }),
  generateCvJd:    (d)      => api.post("/dashboard/hr/cv-screening/jd/generate", d),
  hireCvCandidate: (id, d)  => api.put(`/dashboard/hr/cv-screening/candidates/${id}/hire`, d),
  getCvDetail:     (p)      => api.get("/dashboard/hr/cv-screening/detail", { params: p }),
  getAllCvCandidates: (p)   => api.get("/dashboard/hr/cv-screening/candidates", { params: p }),

  // E-Magazine
  eMagazineList:       ()              => api.get("/dashboard/hr/e-magazine/files"),
  eMagazineUpload:     (form)          => api.post("/dashboard/hr/e-magazine/upload", form, { headers: { "Content-Type": "multipart/form-data" } }),
  eMagazineDelete:     (filename)      => api.delete(`/dashboard/hr/e-magazine/files/${encodeURIComponent(filename)}`),
  eMagazineUpdateQR:   (filename, qrs) => api.patch(`/dashboard/hr/e-magazine/files/${encodeURIComponent(filename)}/qr-links`, qrs),

  // Organization Structure (manual add/edit/delete org chart)
  getOrgStructureTree:    ()          => api.get("/dashboard/hr/org-structure/tree"),
  getOrgStructureList:    (p)         => api.get("/dashboard/hr/org-structure/list", { params: p }),
  getOrgStructureLov:     ()          => api.get("/dashboard/hr/org-structure/lov"),
  getOrgStructureDepts:   ()          => api.get("/dashboard/hr/org-structure/departments"),
  createOrgStructureNode: (d)         => api.post("/dashboard/hr/org-structure", d),
  updateOrgStructureNode: (id, d)     => api.put(`/dashboard/hr/org-structure/${id}`, d),
  deleteOrgStructureNode: (id)        => api.delete(`/dashboard/hr/org-structure/${id}`),
  importOrgStructure:     (form)      => api.post("/dashboard/hr/org-structure/import", form, { headers: { "Content-Type": "multipart/form-data" } }),
  getOrgStructureUploadLogs: ()       => api.get("/dashboard/hr/org-structure/upload-logs"),
};

// EIS Dashboard — ported from the standalone eis-dashboard-v2 app.
const EIS = "/dashboard/eis";
export const eisApi = {
  // Summary
  getKpiCards:          (year, period) => api.get(`${EIS}/summary/kpi-cards`, { params: { year, period } }),
  getPortfolio:         (params)       => api.get(`${EIS}/summary/portfolio`, { params }),
  getClosingEstimation: (year, period) => api.get(`${EIS}/summary/closing-estimation`, { params: { year, period } }),
  getNwc:               (year, period) => api.get(`${EIS}/summary/nwc`, { params: { year, period } }),

  // Performance
  getSalesAchievement: (year, segment)      => api.get(`${EIS}/performance/sales-achievement`, { params: { year, segment } }),
  getMonthlySales:     (year, segment)      => api.get(`${EIS}/performance/monthly-sales`, { params: { year, segment } }),
  getSalesGrowth:      (year, segment)      => api.get(`${EIS}/performance/growth`, { params: { year, segment } }),
  getEbitProduct:      (year, period)       => api.get(`${EIS}/performance/ebit-product`, { params: { year, period } }),
  getAreaSales:        (year, period)       => api.get(`${EIS}/performance/area-sales`, { params: { year, period } }),
  getMarketing:        (year)               => api.get(`${EIS}/performance/marketing`, { params: { year } }),
  getForecast:         (year, period, segment) => api.get(`${EIS}/performance/forecast`, { params: { year, period, segment } }),

  // Production
  getBatchProduction: (year)         => api.get(`${EIS}/production/batch`, { params: { year } }),
  getYieldProduction: (year)         => api.get(`${EIS}/production/yield`, { params: { year } }),
  getDio:             (year)         => api.get(`${EIS}/production/dio`, { params: { year } }),
  getCogsRatio:       (year, period) => api.get(`${EIS}/production/cogs-ratio`, { params: { year, period } }),
  getOvertime:        (year)         => api.get(`${EIS}/production/overtime`, { params: { year } }),
  getReleaseTime:     (year)         => api.get(`${EIS}/production/release-time`, { params: { year } }),

  // Expansion
  getPipeline:        (year)         => api.get(`${EIS}/expansion/pipeline`, { params: { year } }),
  getPipelineSummary: (year, period) => api.get(`${EIS}/expansion/pipeline-summary`, { params: { year, period } }),

  // Administration
  getHeadcount: (year) => api.get(`${EIS}/admin/headcount`, { params: { year } }),
  getTurnover:  (year) => api.get(`${EIS}/admin/turnover`, { params: { year } }),
  getProfit:    (year) => api.get(`${EIS}/admin/profit`, { params: { year } }),
  getCashflow:  (year) => api.get(`${EIS}/admin/cashflow`, { params: { year } }),
  getRatios:    (year) => api.get(`${EIS}/admin/ratios`, { params: { year } }),
  getBudget:    (year) => api.get(`${EIS}/admin/budget`, { params: { year } }),

  // Business Plan
  getBpList: (year, planType) => api.get(`${EIS}/bp/list`, { params: { year, plan_type: planType } }),
  saveBp:    (data)           => api.post(`${EIS}/bp/save`, data),
  deleteBp:  (id)             => api.delete(`${EIS}/bp/${id}`),
  getBpTypes: ()              => api.get(`${EIS}/bp/types`),

  // ETL
  getEtlStatus:   ()               => api.get(`${EIS}/etl/status`),
  triggerEtl:     (jobName, params) => api.post(`${EIS}/etl/trigger/${jobName}`, params),
  stopEtl:        (jobName)        => api.post(`${EIS}/etl/stop/${jobName}`),
  getEtlSchedule: ()               => api.get(`${EIS}/etl/schedule`),
  getEtlJobData:  (jobName, year, month) => api.get(`${EIS}/etl/job-data/${jobName}`, { params: { year, month: month || undefined } }),

  // Daily Sales
  getDailySales:    ()         => api.get(`${EIS}/daily-sales/data`),
  uploadDailySales: (formData) => api.post(`${EIS}/daily-sales/upload`, formData, { headers: { "Content-Type": "multipart/form-data" } }),

  // Data Upload
  getOvertimeData:   (year)         => api.get(`${EIS}/data-upload/overtime`, { params: { year } }),
  uploadOvertimeData:(year, formData) => api.post(`${EIS}/data-upload/overtime/upload`, formData, { params: { year }, headers: { "Content-Type": "multipart/form-data" } }),
  getCogsUploadData: (year, period) => api.get(`${EIS}/data-upload/cogs`, { params: { year, period } }),
  uploadCogsData:    (year, formData) => api.post(`${EIS}/data-upload/cogs/upload`, formData, { params: { year }, headers: { "Content-Type": "multipart/form-data" } }),
  getSalesBP:        (year)         => api.get(`${EIS}/data-upload/sales-bp`, { params: { year } }),
  uploadSalesBP:     (year, formData) => api.post(`${EIS}/data-upload/sales-bp/upload`, formData, { params: { year }, headers: { "Content-Type": "multipart/form-data" } }),
};

export const pacApi = {
  getSummary:      ()  => api.get("/dashboard/pac/summary"),
  getBudgetUsage:  (p) => api.get("/dashboard/pac/budget-usage", { params: p }),
  getLedgers:      ()  => api.get("/dashboard/pac/lov/ledgers"),

  // Business Plan
  listBusinessPlans:   (p)    => api.get("/dashboard/pac/business-plans", { params: p }),
  getBusinessPlan:     (id)   => api.get(`/dashboard/pac/business-plans/${id}`),
  upsertBusinessPlan:  (body) => api.post("/dashboard/pac/business-plans", body),
  deleteBusinessPlan:  (id)   => api.delete(`/dashboard/pac/business-plans/${id}`),

  // Setup Modules (Schedule / Guideline / Outlook)
  listSetupModules:     (p)    => api.get("/dashboard/pac/setup-modules", { params: p }),
  getSetupModule:       (id)   => api.get(`/dashboard/pac/setup-modules/${id}`),
  upsertSetupModule:    (body) => api.post("/dashboard/pac/setup-modules", body),
  deleteSetupModule:    (id)   => api.delete(`/dashboard/pac/setup-modules/${id}`),
  generateOutlook:      (body) => api.post("/dashboard/pac/setup-modules/generate-outlook", body),

  // Sales Plan (Simulation)
  listSalesPlans:       (p)    => api.get("/dashboard/pac/sales-plans", { params: p }),
  getSalesPlan:         (id)   => api.get(`/dashboard/pac/sales-plans/${id}`),
  upsertSalesPlan:      (body) => api.post("/dashboard/pac/sales-plans", body),
  deleteSalesPlan:      (id)   => api.delete(`/dashboard/pac/sales-plans/${id}`),
  exportSalesPlanExcel: (id, type) => api.post(`/dashboard/pac/sales-plans/${id}/export`, null, { params: { plan_type: type }, responseType: "blob" }),
  uploadSalesPlanExcel: (file, planYear) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/dashboard/pac/sales-plans/upload", form, { params: { plan_year: planYear }, headers: { "Content-Type": "multipart/form-data" } });
  },
  exportGrossSalesReport: (planYear) => api.get("/dashboard/pac/sales-plans/gross-sales-report", { params: { plan_year: planYear }, responseType: "blob" }),
  exportSalesSummary: (planYear) => api.get("/dashboard/pac/sales-plans/sales-summary", { params: { plan_year: planYear }, responseType: "blob" }),

  // Purchase Plan Material (Simulation)
  listPurchasePlans:  (p)    => api.get("/dashboard/pac/purchase-plans", { params: p }),
  getPurchasePlan:    (id)   => api.get(`/dashboard/pac/purchase-plans/${id}`),
  upsertPurchasePlan: (body) => api.post("/dashboard/pac/purchase-plans", body),
  deletePurchasePlan: (id)   => api.delete(`/dashboard/pac/purchase-plans/${id}`),
  uploadPurchasePlanExcel: (file, planYear) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/dashboard/pac/purchase-plans/upload", form, { params: { plan_year: planYear }, headers: { "Content-Type": "multipart/form-data" } });
  },

  // Personnel Plan (Simulation)
  listPersonnelPlans:  (p)    => api.get("/dashboard/pac/personnel-plans", { params: p }),
  getPersonnelPlan:    (id)   => api.get(`/dashboard/pac/personnel-plans/${id}`),
  upsertPersonnelPlan: (body) => api.post("/dashboard/pac/personnel-plans", body),
  deletePersonnelPlan: (id)   => api.delete(`/dashboard/pac/personnel-plans/${id}`),
  uploadPersonnelPlanExcel: (file, planYear) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/dashboard/pac/personnel-plans/upload", form, { params: { plan_year: planYear }, headers: { "Content-Type": "multipart/form-data" } });
  },

  // Manufacture Plan (Simulation)
  listManufacturePlans:  (p)    => api.get("/dashboard/pac/manufacture-plans", { params: p }),
  getManufacturePlan:    (id)   => api.get(`/dashboard/pac/manufacture-plans/${id}`),
  upsertManufacturePlan: (body) => api.post("/dashboard/pac/manufacture-plans", body),
  deleteManufacturePlan: (id)   => api.delete(`/dashboard/pac/manufacture-plans/${id}`),
  uploadManufacturePlanExcel: (file, planYear) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/dashboard/pac/manufacture-plans/upload", form, { params: { plan_year: planYear }, headers: { "Content-Type": "multipart/form-data" } });
  },

  // Investment Plan (Simulation)
  listInvestmentPlans:  (p)    => api.get("/dashboard/pac/investment-plans", { params: p }),
  getInvestmentPlan:    (id)   => api.get(`/dashboard/pac/investment-plans/${id}`),
  upsertInvestmentPlan: (body) => api.post("/dashboard/pac/investment-plans", body),
  deleteInvestmentPlan: (id)   => api.delete(`/dashboard/pac/investment-plans/${id}`),
  uploadInvestmentPlanExcel: (file, planYear) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/dashboard/pac/investment-plans/upload", form, { params: { plan_year: planYear }, headers: { "Content-Type": "multipart/form-data" } });
  },

  // OPEX Plan (Simulation)
  listOpexPlans:  (p)    => api.get("/dashboard/pac/opex-plans", { params: p }),
  getOpexPlan:    (id)   => api.get(`/dashboard/pac/opex-plans/${id}`),
  upsertOpexPlan: (body) => api.post("/dashboard/pac/opex-plans", body),
  deleteOpexPlan: (id)   => api.delete(`/dashboard/pac/opex-plans/${id}`),
  uploadOpexPlanExcel: (file, planYear) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/dashboard/pac/opex-plans/upload", form, { params: { plan_year: planYear }, headers: { "Content-Type": "multipart/form-data" } });
  },

  // Exchange Rates
  getExchangeRates:    (refresh = false) => api.get("/dashboard/pac/exchange-rates", { params: { refresh } }),
  pushExchangeRatesToEBS: (body) => api.post("/dashboard/pac/exchange-rates/push-to-ebs", body),
};

export const accountingApi = {
  getSummary:              () => api.get("/dashboard/accounting/summary"),
  getApOutstanding:        (p) => api.get("/dashboard/accounting/ap-outstanding", { params: p }),
  getArOutstanding:        (p) => api.get("/dashboard/accounting/ar-outstanding", { params: p }),
  getInventoryRmPm:        (p) => api.get("/dashboard/accounting/inventory-rm-pm", { params: p }),
  exportInventoryRmPm:     (p) => api.get("/dashboard/accounting/inventory-rm-pm/export", { params: p, responseType: "blob" }),
  getItemCostComponents:   (period) => api.get("/dashboard/accounting/item-cost-components", { params: { period } }),
  getMaterialTransactions: (p) => api.get("/dashboard/accounting/material-transactions", { params: p }),
};

export const financialStatementApi = {
  getPeriods:  () => api.get("/dashboard/accounting/financial-statement/periods"),
  getBalanceSheet:       (periods) => api.get("/dashboard/accounting/financial-statement/balance-sheet", { params: { periods: periods.join(",") } }),
  getBalanceSheetDetail: (periods) => api.get("/dashboard/accounting/financial-statement/balance-sheet-detail", { params: { periods: periods.join(",") } }),
  getProfitLoss:         (columns) => api.get("/dashboard/accounting/financial-statement/profit-loss", { params: { columns: JSON.stringify(columns) } }),
  getProfitLossMonthly:  ({ periodThis, ytdThis, periodLast, ytdLast }) =>
    api.get("/dashboard/accounting/financial-statement/profit-loss-monthly", {
      params: { period_this: periodThis, ytd_this: ytdThis.join(","), period_last: periodLast, ytd_last: ytdLast.join(",") },
    }),
  exportBalanceSheet:       (periods, asOfLabel) => api.get("/dashboard/accounting/financial-statement/balance-sheet/export", { params: { periods: periods.join(","), as_of_label: asOfLabel || "" }, responseType: "blob" }),
  exportBalanceSheetDetail: (periods, asOfLabel) => api.get("/dashboard/accounting/financial-statement/balance-sheet-detail/export", { params: { periods: periods.join(","), as_of_label: asOfLabel || "" }, responseType: "blob" }),
  exportProfitLoss:         (columns, dateLabel) => api.get("/dashboard/accounting/financial-statement/profit-loss/export", { params: { columns: JSON.stringify(columns), date_label: dateLabel || "" }, responseType: "blob" }),
  exportProfitLossMonthly:  ({ periodThis, ytdThis, periodLast, ytdLast, dateLabel }) =>
    api.get("/dashboard/accounting/financial-statement/profit-loss-monthly/export", {
      params: { period_this: periodThis, ytd_this: ytdThis.join(","), period_last: periodLast, ytd_last: ytdLast.join(","), date_label: dateLabel || "" },
      responseType: "blob",
    }),
};

export const apInvoiceApi = {
  upload:          (formData) => api.post("/dashboard/accounting/ap-invoice/upload", formData, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 }),
  list:            ()         => api.get("/dashboard/accounting/ap-invoice/invoices"),
  get:             (id)       => api.get(`/dashboard/accounting/ap-invoice/invoices/${id}`),
  update:          (id, data) => api.put(`/dashboard/accounting/ap-invoice/invoices/${id}`, data),
  delete:          (id)       => api.delete(`/dashboard/accounting/ap-invoice/invoices/${id}`),
  validate:        (id)       => api.post(`/dashboard/accounting/ap-invoice/validate/${id}`),
  insertInterface: (id, data) => api.post(`/dashboard/accounting/ap-invoice/insert-interface/${id}`, data),
  runImport:       (id)       => api.post(`/dashboard/accounting/ap-invoice/run-import/${id}`),
  checkStatus:     (id)       => api.get(`/dashboard/accounting/ap-invoice/check-status/${id}`),
  attachPdf:       (id)       => api.post(`/dashboard/accounting/ap-invoice/attach/${id}`),
};

export const purchasingApi = {
  getSummary:        () => api.get("/dashboard/purchasing/summary"),
  getOpenPR:         (p) => api.get("/dashboard/purchasing/open-pr", { params: p }),
  getMonthlySpend:   (p) => api.get("/dashboard/purchasing/monthly-spend", { params: p }),
  getActiveSuppliers:(p) => api.get("/dashboard/purchasing/active-suppliers", { params: p }),

  // Purchase History
  getPurchaseHistoryDetail:     (p) => api.get("/dashboard/purchasing/purchase-history/detail",      { params: p }),
  getPurchaseHistoryByItem:     (p) => api.get("/dashboard/purchasing/purchase-history/by-item",     { params: p }),
  getPurchaseHistoryBySupplier: (p) => api.get("/dashboard/purchasing/purchase-history/by-supplier", { params: p }),

  // LOV
  getOrganizations:  () => api.get("/dashboard/purchasing/lov/organizations"),
  getItems:          (orgId, search) => api.get("/dashboard/purchasing/lov/items", { params: { org_id: orgId, search } }),
  getCategories:     () => api.get("/dashboard/purchasing/lov/categories"),
  getCurrencies:     () => api.get("/dashboard/purchasing/lov/currencies"),
  getMaterialTypes:  () => api.get("/dashboard/purchasing/lov/material-types"),

  // PO Price Analysis
  getPriceAnalysis: (p) => api.get("/dashboard/purchasing/price-analysis", { params: p }),
  getMetalsLatest:  ()  => api.get("/dashboard/purchasing/metals/latest"),

  // Manufacturer Master
  getManufacturerList: () => api.get("/dashboard/purchasing/manufacturer-master"),
  createManufacturer:  (data) => api.post("/dashboard/purchasing/manufacturer-master", data),
  deleteManufacturer:  (id) => api.delete(`/dashboard/purchasing/manufacturer-master/${id}`),
};

export const chatbotApi = {
  chat: (message, history) =>
    api.post("/ai/chatbot/chat", { message, conversation_history: history }),
};

export const meetingNotesApi = {
  transcribe: (formData) =>
    api.post("/ai/meeting-notes/transcribe", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  generateMom: (transcript) =>
    api.post("/ai/meeting-notes/generate", { transcript }),
};
