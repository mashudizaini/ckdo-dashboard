/**
 * Digital Overtime Management System — API calls
 * ─────────────────────────────────────────
 * Backend: app/routers/dashboard/hr_overtime.py (employee + approver)
 *          app/routers/dashboard/hr_overtime_admin.py (HRGA only)
 */
import api from "./client";

const BASE = "/dashboard/hr/overtime";

export const overtimeApi = {
  // ── Context & rules ──
  me:            ()      => api.get(`${BASE}/me`),
  getRules:      ()      => api.get(`${BASE}/rules`),

  // ── Dashboard (site map A) ──
  getSummary:    (month) => api.get(`${BASE}/dashboard/summary`, { params: month ? { month } : {} }),
  getUpcoming:   (limit) => api.get(`${BASE}/dashboard/upcoming`, { params: { limit: limit || 10 } }),

  // ── Overtime Order / Plan (site map B) ──
  listOrders:    (p)     => api.get(`${BASE}/orders`, { params: p }),
  getRequest:    (id)    => api.get(`${BASE}/requests/${id}`),
  createOrder:   (d)     => api.post(`${BASE}/orders`, d),
  updateOrder:   (id, d) => api.put(`${BASE}/orders/${id}`, d),
  submitOrder:   (id)    => api.post(`${BASE}/orders/${id}/submit`),
  cancelOrder:   (id, d) => api.post(`${BASE}/orders/${id}/cancel`, d),
  deleteOrder:   (id)    => api.delete(`${BASE}/orders/${id}`),

  // ── Realization (site map C) ──
  listRealizations: (p)     => api.get(`${BASE}/realizations`, { params: p }),
  saveRealization:  (id, d) => api.put(`${BASE}/realizations/${id}`, d),
  submitRealization:(id)    => api.post(`${BASE}/realizations/${id}/submit`),

  // ── Evidence / supporting documents ──
  uploadAttachment: (id, file) => {
    const fd = new FormData();
    fd.append("file", file);
    // Content-Type must be unset so the browser writes its own multipart
    // boundary — same trick as hrApi.uploadEmployeePhoto.
    return api.post(`${BASE}/requests/${id}/attachments`, fd, { headers: { "Content-Type": undefined } });
  },
  attachmentUrl:    (id) => `/api/v1${BASE}/attachments/${id}/download`,
  deleteAttachment: (id) => api.delete(`${BASE}/attachments/${id}`),

  // ── Approvals ──
  getApprovals:     (stage) => api.get(`${BASE}/approvals`, { params: stage ? { stage } : {} }),
  getApprovalHistory:()     => api.get(`${BASE}/approvals/history`),
  decide:           (id, d) => api.post(`${BASE}/approvals/${id}/decide`, d),

  // ── Notifications (site map E) ──
  getNotifications: (p)  => api.get(`${BASE}/notifications`, { params: p }),
  markRead:         (id) => api.post(`${BASE}/notifications/${id}/read`),
  markAllRead:      ()   => api.post(`${BASE}/notifications/read-all`),

  // ── HRGA admin — calculation & monitoring ──
  getPeriods:       ()   => api.get(`${BASE}/admin/periods`),
  getCalculation:   (p)  => api.get(`${BASE}/admin/calculation`, { params: p }),
  exportCalculationUrl: (p) => {
    const qs = new URLSearchParams(Object.entries(p || {}).filter(([, v]) => v)).toString();
    return `/api/v1${BASE}/admin/calculation/export${qs ? `?${qs}` : ""}`;
  },
  getMonitoring:    (p)  => api.get(`${BASE}/admin/monitoring`, { params: p }),
  getExceptions:    (p)  => api.get(`${BASE}/admin/monitoring/exceptions`, { params: p }),
  getAllRequests:   (p)  => api.get(`${BASE}/admin/requests`, { params: p }),
  getLov:           ()   => api.get(`${BASE}/admin/lov`),

  // ── HRGA admin — system setting (site map D) ──
  getMatrix:        (p)  => api.get(`${BASE}/admin/approval-matrix`, { params: p }),
  saveMatrix:       (d)  => api.post(`${BASE}/admin/approval-matrix`, d),
  bulkMatrix:       (d)  => api.post(`${BASE}/admin/approval-matrix/bulk`, d),
  deleteMatrix:     (id) => api.delete(`${BASE}/admin/approval-matrix/${id}`),
  getApproverOptions:()  => api.get(`${BASE}/admin/approver-options`),

  adminGetRules:    ()      => api.get(`${BASE}/admin/rules`),
  createRule:       (d)     => api.post(`${BASE}/admin/rules`, d),
  updateRule:       (id, d) => api.put(`${BASE}/admin/rules/${id}`, d),
  deleteRule:       (id)    => api.delete(`${BASE}/admin/rules/${id}`),

  getCutoff:        ()   => api.get(`${BASE}/admin/cutoff`),
  updateCutoff:     (d)  => api.put(`${BASE}/admin/cutoff`, d),

  getNotificationSettings:    ()  => api.get(`${BASE}/admin/notification-settings`),
  updateNotificationSettings: (d) => api.put(`${BASE}/admin/notification-settings`, d),

  getRates:         ()   => api.get(`${BASE}/admin/rates`),
  saveRate:         (d)  => api.post(`${BASE}/admin/rates`, d),
  deleteRate:       (id) => api.delete(`${BASE}/admin/rates/${id}`),
};

export default overtimeApi;
