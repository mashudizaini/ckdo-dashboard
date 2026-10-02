/**
 * Server Control — interactive SSH shells in a tabbed panel.
 *
 * A web page cannot launch PuTTY, cmd or PowerShell; browsers do not let a site
 * start a local program. So the shell comes to the page instead.
 *
 * It is also the safer of the two workflows. Reveal-and-paste puts the server
 * password in the browser and on the system clipboard; here the password is
 * decrypted in the backend and handed straight to SSH — these components never
 * receive it and never could, because the socket only ever carries terminal
 * bytes.
 *
 * Several sessions can be open at once (one per tab). Every session stays
 * MOUNTED while another tab is in front, hidden with display:none rather than
 * unmounted — unmounting would tear down its WebSocket and kill the shell, so
 * switching tabs would silently drop whatever was running there.
 *
 * Handshake (see routers/dashboard/it_server_registry.py for the server side):
 *   1. POST .../credentials/{id}/terminal-ticket  — on the IT-gated router
 *   2. open the WebSocket
 *   3. first frame sends { ticket, token, cols, rows } — the token is sent in
 *      the frame rather than a header because the WebSocket API cannot set one,
 *      and in the frame rather than the URL because nginx logs URLs.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Loader2, X, TerminalSquare, Plus } from "lucide-react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import api from "@/api/client";
import { useAuthStore } from "@/store/authStore";

// Matches the dashboard's own dark surfaces rather than xterm's default black,
// so the panel does not look like a foreign window pasted onto the page.
const THEME = {
  background: "#0b1220", foreground: "#e2e8f0", cursor: "#38bdf8",
  black: "#0b1220", red: "#f87171", green: "#4ade80", yellow: "#fbbf24",
  blue: "#60a5fa", magenta: "#c084fc", cyan: "#22d3ee", white: "#e2e8f0",
  brightBlack: "#475569", brightRed: "#fca5a5", brightGreen: "#86efac",
  brightYellow: "#fcd34d", brightBlue: "#93c5fd", brightMagenta: "#d8b4fe",
  brightCyan: "#67e8f9", brightWhite: "#f8fafc",
};

const DOT = { connecting: "#f59e0b", ready: "#22c55e", closed: "#94a3b8", error: "#ef4444" };

/* ─── One session: xterm + WebSocket ──────────────────────────────────── */
function TerminalSession({ session, active, onStatus }) {
  const hostRef = useRef(null);
  const termRef = useRef(null);
  const fitRef = useRef(null);
  const wsRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const fit = new FitAddon();
    const term = new Terminal({
      theme: THEME, fontSize: 13, fontFamily: "Consolas, 'Courier New', monospace",
      cursorBlink: true, scrollback: 5000, convertEol: false,
    });
    term.loadAddon(fit);
    term.open(hostRef.current);
    fit.fit();
    termRef.current = term;
    fitRef.current = fit;

    const report = (status, message) => !cancelled && onStatus(session.id, status, message);

    const start = async () => {
      let ticket;
      try {
        const res = await api.post(
          `/dashboard/it/server-registry/credentials/${session.credential.id}/terminal-ticket`, {},
        );
        ticket = res.ticket;
      } catch (e) {
        report("error", e?.detail || e?.message || "Gagal meminta tiket sesi");
        return;
      }
      if (cancelled) return;

      // Same origin as the page, so the scheme follows it: wss:// when the
      // dashboard is served over https, ws:// otherwise. Hardcoding either one
      // breaks the other environment.
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/api/v1/dashboard/it/server-registry/terminal`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => ws.send(JSON.stringify({
        ticket, token: useAuthStore.getState().token, cols: term.cols, rows: term.rows,
      }));

      ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        if (msg.type === "ready") {
          report("ready", `${msg.user}@${msg.host}`);
          if (active) term.focus();
        } else if (msg.type === "output") {
          term.write(msg.data);
        } else if (msg.type === "error") {
          report("error", msg.message);
          term.write(`\r\n\x1b[31m${msg.message}\x1b[0m\r\n`);
        }
      };

      // Only downgrade — an error already reported is more informative than
      // "closed" replacing it.
      ws.onclose = () => report("closed", null);

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "input", data }));
      });

      const onResize = () => {
        fit.fit();
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
        }
      };
      window.addEventListener("resize", onResize);
      ws.addEventListener("close", () => window.removeEventListener("resize", onResize));
    };

    start();

    return () => {
      cancelled = true;
      try { wsRef.current?.close(); } catch { /* already gone */ }
      term.dispose();
    };
    // session.id is stable for the life of a tab; re-running this would open a
    // second shell for the same tab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]);

  // A hidden element has no size, so xterm measured 0 columns while this tab sat
  // in the background. Re-fit on the way back in, before paint, and tell the
  // remote pty the new size — otherwise output wraps at the wrong width until
  // the next window resize.
  useLayoutEffect(() => {
    if (!active || !fitRef.current || !termRef.current) return;
    fitRef.current.fit();
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "resize", cols: termRef.current.cols, rows: termRef.current.rows }));
    }
    termRef.current.focus();
  }, [active]);

  return (
    <div style={{ position: "absolute", inset: 0, padding: 8, display: active ? "block" : "none" }}>
      <div ref={hostRef} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}

/* ─── The panel: one tab per open session ─────────────────────────────── */
export default function TerminalDock({ sessions, activeId, onActivate, onCloseSession, onCloseAll }) {
  const [meta, setMeta] = useState({}); // id -> { status, message }

  const onStatus = (id, status, message) =>
    setMeta((m) => ({
      ...m,
      // "closed" must not overwrite an error already shown — the error says why.
      [id]: status === "closed" && m[id]?.status === "error"
        ? m[id]
        : { status, message: message ?? m[id]?.message },
    }));

  const activeMeta = meta[activeId] || { status: "connecting" };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(2,6,23,0.72)" }}
      onMouseDown={(e) => e.target === e.currentTarget && onCloseAll()}>
      <div className="flex flex-col w-full" style={{
        maxWidth: 1100, height: "min(80vh, 680px)", background: "#0b1220",
        borderRadius: 12, border: "1px solid rgba(148,163,184,0.25)", overflow: "hidden",
      }}>
        {/* Tab strip */}
        <div className="flex items-center gap-1 px-2 py-1.5 overflow-x-auto"
          style={{ borderBottom: "1px solid rgba(148,163,184,0.18)" }}>
          <TerminalSquare size={14} color="#38bdf8" style={{ flexShrink: 0, margin: "0 4px" }} />
          {sessions.map((s) => {
            const st = (meta[s.id] || {}).status || "connecting";
            const on = s.id === activeId;
            return (
              <div key={s.id} onClick={() => onActivate(s.id)}
                title={`${s.serverName}${s.credential.label ? " · " + s.credential.label : ""}`}
                className="flex items-center gap-1.5 shrink-0"
                style={{
                  cursor: "pointer", borderRadius: 7, padding: "4px 6px 4px 9px", fontSize: 11.5,
                  background: on ? "rgba(56,189,248,0.14)" : "transparent",
                  color: on ? "#e2e8f0" : "#94a3b8",
                  border: `1px solid ${on ? "rgba(56,189,248,0.35)" : "transparent"}`,
                }}>
                <span style={{ width: 6, height: 6, borderRadius: 99, background: DOT[st], flexShrink: 0 }} />
                <span style={{ fontWeight: on ? 700 : 500, whiteSpace: "nowrap" }}>{s.serverName}</span>
                {s.credential.username && (
                  <span style={{ color: "#64748b", whiteSpace: "nowrap" }}>{s.credential.username}</span>
                )}
                <button onClick={(e) => { e.stopPropagation(); onCloseSession(s.id); }}
                  title="Tutup sesi ini"
                  style={{ background: "none", border: "none", cursor: "pointer", color: "#64748b", lineHeight: 0, padding: 2 }}>
                  <X size={12} />
                </button>
              </div>
            );
          })}
          <span style={{ flex: 1 }} />
          <span className="flex items-center gap-1.5 shrink-0" style={{ fontSize: 11, color: "#94a3b8", paddingRight: 6 }}>
            {activeMeta.status === "connecting"
              ? "menyambung…"
              : activeMeta.message || activeMeta.status}
          </span>
          <button onClick={onCloseAll} title="Tutup semua sesi"
            style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", lineHeight: 0, padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <div className="relative flex-1 min-h-0">
          {activeMeta.status === "connecting" && (
            <div className="absolute inset-0 flex items-center justify-center gap-2"
              style={{ color: "#94a3b8", fontSize: 12, zIndex: 1, pointerEvents: "none" }}>
              <Loader2 size={14} className="animate-spin" /> membuka sesi SSH…
            </div>
          )}
          {sessions.map((s) => (
            <TerminalSession key={s.id} session={s} active={s.id === activeId} onStatus={onStatus} />
          ))}
        </div>

        <div className="px-3 py-1.5" style={{ borderTop: "1px solid rgba(148,163,184,0.18)", fontSize: 10.5, color: "#475569" }}>
          <Plus size={10} style={{ display: "inline", verticalAlign: -1 }} /> klik ikon terminal di baris lain untuk membuka sesi tambahan — sesi yang sedang berjalan tetap hidup di tab-nya
        </div>
      </div>
    </div>
  );
}
