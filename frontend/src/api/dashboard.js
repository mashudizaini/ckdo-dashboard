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
};

export const hrApi = {
  getSummary: () => api.get("/dashboard/hr/summary"),
  getEmployees: (params) => api.get("/dashboard/hr/employees", { params }),
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
  createTodoTask:  (d)     => api.post("/dashboard/hr/todo/tasks", d),
  updateTodoTask:  (id, d) => api.put(`/dashboard/hr/todo/tasks/${id}`, d),
  deleteTodoTask:  (id)    => api.delete(`/dashboard/hr/todo/tasks/${id}`),
  getCvJobs:       ()       => api.get("/dashboard/hr/cv-screening/jobs"),
  createCvJob:     (d)      => api.post("/dashboard/hr/cv-screening/jobs", d),
  deleteCvJob:     (id)     => api.delete(`/dashboard/hr/cv-screening/jobs/${id}`),
  getCvCandidates: (id, p)  => api.get(`/dashboard/hr/cv-screening/jobs/${id}/candidates`, { params: p }),
  deleteCvCandidate: (id)   => api.delete(`/dashboard/hr/cv-screening/candidates/${id}`),
  getCvStats:      (id)     => api.get(`/dashboard/hr/cv-screening/jobs/${id}/stats`),
  exportCvExcel:   (id)     => `/api/v1/dashboard/hr/cv-screening/jobs/${id}/export`,
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

  // Exchange Rates
  getExchangeRates:    (refresh = false) => api.get("/dashboard/pac/exchange-rates", { params: { refresh } }),
  pushExchangeRatesToEBS: (body) => api.post("/dashboard/pac/exchange-rates/push-to-ebs", body),
};

export const accountingApi = {
  getSummary:              () => api.get("/dashboard/accounting/summary"),
  getApOutstanding:        (p) => api.get("/dashboard/accounting/ap-outstanding", { params: p }),
  getArOutstanding:        (p) => api.get("/dashboard/accounting/ar-outstanding", { params: p }),
  getInventoryRmPm:        (p) => api.get("/dashboard/accounting/inventory-rm-pm", { params: p }),
  getItemCostComponents:   (period) => api.get("/dashboard/accounting/item-cost-components", { params: { period } }),
  getMaterialTransactions: (p) => api.get("/dashboard/accounting/material-transactions", { params: p }),
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
  getOrganizations: () => api.get("/dashboard/purchasing/lov/organizations"),
  getItems:         (orgId, search) => api.get("/dashboard/purchasing/lov/items", { params: { org_id: orgId, search } }),
  getCategories:    () => api.get("/dashboard/purchasing/lov/categories"),
  getCurrencies:    () => api.get("/dashboard/purchasing/lov/currencies"),

  // Price Analysis
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
