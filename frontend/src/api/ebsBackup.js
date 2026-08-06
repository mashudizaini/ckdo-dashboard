/**
 * Oracle EBS Backup Recovery API calls
 * ─────────────────────────────────────────
 * Ported from the standalone ebs-backup-dashboard app's lib/api.js, pointed
 * at its new home under Dashboard IT instead of a separate backend/port.
 */
import api from "./client";

const BASE = "/dashboard/it/ebs-backup";

export const ebsBackupApi = {
  // Overview
  getOverview:  () => api.get(`${BASE}/overview`),
  getDiskSpace: () => api.get(`${BASE}/disk-space`),

  // Servers & credentials
  listServers:   () => api.get(`${BASE}/servers`),
  upsertServer:  (body) => api.post(`${BASE}/servers`, body),
  deleteServer:  (id) => api.delete(`${BASE}/servers/${id}`),
  upsertCredential: (body) => api.post(`${BASE}/servers/credentials`, body),
  listCredentials:  (serverId) => api.get(`${BASE}/servers/${serverId}/credentials`),
  testConnection:   (serverId) => api.post(`${BASE}/servers/test-connection`, { server_id: serverId }),

  // Backup operations
  triggerOnlineBackup: (body) => api.post(`${BASE}/backup/online`, body),
  onlinePreflight:     (serverId) => api.get(`${BASE}/backup/online/preflight/${serverId}`),
  syncOnlineToMinio:    (body) => api.post(`${BASE}/backup/online/sync-minio`, body),
  syncOnlineToSynology: (body) => api.post(`${BASE}/backup/online/sync-synology`, body),
  triggerArchivelog:    (body) => api.post(`${BASE}/backup/archivelog`, body),
  triggerOffline:       (body) => api.post(`${BASE}/backup/offline`, body),
  triggerApp:           (body) => api.post(`${BASE}/backup/app`, body),
  triggerArchivelogSync: (body) => api.post(`${BASE}/backup/archivelog-sync`, body),

  // Jobs
  listJobs: (params) => api.get(`${BASE}/jobs`, { params }),
  getJob:   (id, params) => api.get(`${BASE}/jobs/${id}`, { params }),
  cancelJob: (id) => api.post(`${BASE}/jobs/${id}/cancel`),
  pauseJob:  (id) => api.post(`${BASE}/jobs/${id}/pause`),
  resumeJob: (id) => api.post(`${BASE}/jobs/${id}/resume`),
  deleteJobOutput: (id) => api.post(`${BASE}/jobs/${id}/delete-output`),

  // Schedules
  listSchedules:  () => api.get(`${BASE}/schedules`),
  upsertSchedule: (body) => api.post(`${BASE}/schedules`, body),
  deleteSchedule: (id) => api.delete(`${BASE}/schedules/${id}`),
  toggleSchedule: (id) => api.post(`${BASE}/schedules/${id}/toggle`),

  // SSH setup wizard
  sshGenerateKey: (body) => api.post(`${BASE}/ssh-setup/generate-key`, body),
  sshCopyId:      (body) => api.post(`${BASE}/ssh-setup/copy-id`, body),
  sshTest:        (body) => api.post(`${BASE}/ssh-setup/test`, body),

  // Storage browser
  minioUsage:  (id) => api.get(`${BASE}/storage/minio/${id}/usage`),
  minioList:   (id, prefix) => api.get(`${BASE}/storage/minio/${id}/list`, { params: { prefix } }),
  minioDelete: (id, keys) => api.post(`${BASE}/storage/minio/${id}/delete`, { keys }),
  synologyUsage:  (id) => api.get(`${BASE}/storage/synology/${id}/usage`),
  synologyList:   (id, path) => api.get(`${BASE}/storage/synology/${id}/list`, { params: { path } }),
  synologyDelete: (id, paths) => api.post(`${BASE}/storage/synology/${id}/delete`, { paths }),

  // Restore
  restorePreflight: () => api.get(`${BASE}/restore/preflight`),
  restoreToDev: (body) => api.post(`${BASE}/restore/dev-database`, body),

  // Reports
  getReportsSummary: (days) => api.get(`${BASE}/reports/summary`, { params: { days } }),

  // Inventory / recovery readiness
  scanInventory: () => api.get(`${BASE}/inventory/scan`),
  deleteInventoryItem: (body) => api.post(`${BASE}/inventory/delete`, body),
};
