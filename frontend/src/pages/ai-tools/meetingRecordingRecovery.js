/**
 * meetingRecordingRecovery.js
 * ─────────────────────────────────────────
 * Incremental IndexedDB backup for the live in-browser meeting recorder.
 *
 * Without this, MediaRecorder only ever hands back audio once — when
 * `.stop()` is called — so a 1-2h recording sits entirely in a JS Blob
 * array in memory the whole time. Any interruption before the user clicks
 * Stop (crash, accidental tab close, forced logout, laptop sleep glitch)
 * loses the entire meeting with nothing to recover.
 *
 * Fix: MeetingNotes.jsx starts the recorder with a timeslice (so
 * `ondataavailable` fires periodically, not just once at the end) and
 * writes each chunk here as it arrives. On next visit, `findRecoverableSession`
 * lets the page offer to reassemble whatever was captured before the
 * interruption, instead of losing it outright.
 */
const DB_NAME = "ckdo_meeting_recovery";
const DB_VERSION = 1;
const SESSIONS_STORE = "sessions";
const CHUNKS_STORE = "chunks";

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(SESSIONS_STORE)) {
        db.createObjectStore(SESSIONS_STORE, { keyPath: "sessionId" });
      }
      if (!db.objectStoreNames.contains(CHUNKS_STORE)) {
        const store = db.createObjectStore(CHUNKS_STORE, { keyPath: "id", autoIncrement: true });
        store.createIndex("sessionId", "sessionId", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// All operations degrade to a silent no-op if IndexedDB isn't available
// (older browser, private-browsing restrictions) — this is a resilience
// nice-to-have, not something that should ever block recording itself.
async function safe(fn, fallback) {
  try {
    if (!window.indexedDB) return fallback;
    return await fn();
  } catch (_) {
    return fallback;
  }
}

export function startSession(sessionId, meta) {
  return safe(async () => {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(SESSIONS_STORE, "readwrite");
      tx.objectStore(SESSIONS_STORE).put({ sessionId, startedAt: Date.now(), ...meta });
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  });
}

export function saveChunk(sessionId, blob) {
  return safe(async () => {
    const db = await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction(CHUNKS_STORE, "readwrite");
      tx.objectStore(CHUNKS_STORE).add({ sessionId, at: Date.now(), blob });
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
    db.close();
  });
}

// Most recent session that still has chunks on file (i.e. was never
// cleared by a clean stop+transcribe or an explicit discard) — that's the
// one worth offering to recover. Older leftover sessions are swept away
// at the same time so IndexedDB doesn't grow unbounded across many
// interrupted attempts.
export function findRecoverableSession() {
  return safe(async () => {
    const db = await openDb();
    const sessions = await new Promise((resolve, reject) => {
      const tx = db.transaction(SESSIONS_STORE, "readonly");
      const req = tx.objectStore(SESSIONS_STORE).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
    if (!sessions.length) { db.close(); return null; }

    sessions.sort((a, b) => b.startedAt - a.startedAt);
    const [latest, ...stale] = sessions;

    const chunkCount = await new Promise((resolve, reject) => {
      const tx = db.transaction(CHUNKS_STORE, "readonly");
      const req = tx.objectStore(CHUNKS_STORE).index("sessionId").count(IDBKeyRange.only(latest.sessionId));
      req.onsuccess = () => resolve(req.result || 0);
      req.onerror = () => reject(req.error);
    });

    for (const s of stale) await clearSession(s.sessionId, db);
    if (chunkCount === 0) { await clearSession(latest.sessionId, db); db.close(); return null; }

    db.close();
    return { sessionId: latest.sessionId, startedAt: latest.startedAt, meta: latest, chunkCount };
  }, null);
}

export function getChunks(sessionId) {
  return safe(async () => {
    const db = await openDb();
    const rows = await new Promise((resolve, reject) => {
      const tx = db.transaction(CHUNKS_STORE, "readonly");
      const req = tx.objectStore(CHUNKS_STORE).index("sessionId").getAll(IDBKeyRange.only(sessionId));
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
    db.close();
    rows.sort((a, b) => a.at - b.at);
    return rows.map((r) => r.blob);
  }, []);
}

export async function clearSession(sessionId, existingDb) {
  return safe(async () => {
    const db = existingDb || await openDb();
    await new Promise((resolve, reject) => {
      const tx = db.transaction([SESSIONS_STORE, CHUNKS_STORE], "readwrite");
      tx.objectStore(SESSIONS_STORE).delete(sessionId);
      const chunkStore = tx.objectStore(CHUNKS_STORE);
      const idx = chunkStore.index("sessionId");
      const cursorReq = idx.openCursor(IDBKeyRange.only(sessionId));
      cursorReq.onsuccess = () => {
        const cursor = cursorReq.result;
        if (cursor) { cursor.delete(); cursor.continue(); }
      };
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
    if (!existingDb) db.close();
  });
}
