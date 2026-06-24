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
  getServerMetrics: () => api.get("/dashboard/it/server-monitoring/metrics"),

  // Other sections
  getTablespace:    () => api.get("/dashboard/it/tablespace-usage"),
  getDiskUsage:     () => api.get("/dashboard/it/disk-usage"),
  getPendingJobs:   () => api.get("/dashboard/it/pending-jobs"),
  getWorkflowError: () => api.get("/dashboard/it/workflow-error"),
};

export const hrApi = {
  getSummary: () => api.get("/dashboard/hr/summary"),
  getEmployees: (params) => api.get("/dashboard/hr/employees", { params }),
  getAttendance: (params) => api.get("/dashboard/hr/attendance", { params }),
};

export const pacApi = {
  getSummary:      ()  => api.get("/dashboard/pac/summary"),
  getBudgetUsage:  (p) => api.get("/dashboard/pac/budget-usage", { params: p }),
  getLedgers:      ()  => api.get("/dashboard/pac/lov/ledgers"),
};

export const accountingApi = {
  getSummary: () => api.get("/dashboard/accounting/summary"),
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
