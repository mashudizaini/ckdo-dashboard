const BASE = "/api";

async function parseError(res) {
  const text = await res.text();
  try {
    const json = JSON.parse(text);
    const detail = json.detail;
    if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
      return detail.errors.join("\n");
    }
    if (typeof detail === "string") return detail;
    return json.message || `Error ${res.status}`;
  } catch {
    return `Server error (${res.status}): ${text.substring(0, 300)}`;
  }
}

// Step 1: Upload & Extract PDF
export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/upload/`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Staging CRUD
export async function listInvoices() {
  const res = await fetch(`${BASE}/invoices/`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function getInvoice(stgId) {
  const res = await fetch(`${BASE}/invoices/${stgId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateInvoice(stgId, payload) {
  const res = await fetch(`${BASE}/invoices/${stgId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Step 2: Validate vendor/PO di Oracle
export async function validateInvoice(stgId) {
  const res = await fetch(`${BASE}/process/validate/${stgId}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Step 3: Preview interface mapping
export async function previewInterface(stgId) {
  const res = await fetch(`${BASE}/process/preview/${stgId}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Step 4: Insert ke Oracle AP Interface tables (with edited data)
export async function insertInterface(stgId, payload) {
  const res = await fetch(`${BASE}/process/insert-interface/${stgId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Step 5: Run APXIIMPT concurrent
export async function runImport(stgId) {
  const res = await fetch(`${BASE}/process/run-import/${stgId}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Step 6: Attach PDF ke AP Invoice
export async function attachPdf(stgId) {
  const res = await fetch(`${BASE}/process/attach/${stgId}`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

// Tracker: cek status concurrent request
export async function getRequestStatus(stgId) {
  const res = await fetch(`${BASE}/invoices/${stgId}/request-status`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
