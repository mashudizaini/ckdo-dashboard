// src/services/api.js
const BASE = "http://localhost:8000";

export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload/`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Upload gagal");
  }
  return res.json();
}

export async function listInvoices() {
  const res = await fetch(`${BASE}/invoices/`);
  if (!res.ok) throw new Error("Gagal ambil data");
  return res.json();
}

export async function getInvoice(stgId) {
  const res = await fetch(`${BASE}/invoices/${stgId}`);
  if (!res.ok) throw new Error("Invoice tidak ditemukan");
  return res.json();
}

export async function updateInvoice(stgId, payload) {
  const res = await fetch(`${BASE}/invoices/${stgId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Update gagal");
  }
  return res.json();
}

export async function validateInvoice(stgId) {
  const res = await fetch(`${BASE}/process/validate/${stgId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(JSON.stringify(err.detail) || "Validasi gagal");
  }
  return res.json();
}

export async function submitInvoice(stgId) {
  const res = await fetch(`${BASE}/process/submit/${stgId}`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || "Submit gagal");
  }
  return res.json();
}

export async function getRequestStatus(stgId) {
  const res = await fetch(`${BASE}/invoices/${stgId}/request-status`);
  if (!res.ok) throw new Error("Gagal cek status");
  return res.json();
}
