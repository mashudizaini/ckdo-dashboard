/**
 * Server Control — interactive SSH shell in a modal.
 *
 * A web page cannot launch PuTTY, cmd or PowerShell; browsers do not let a site
 * start a local program. So the shell comes to the page instead.
 *
 * It is also the safer of the two workflows. Reveal-and-paste puts the server
 * password in the browser and on the system clipboard; here the password is
 * decrypted in the backend and handed straight to SSH — this component never
 * receives it and never could, because the socket only ever carries terminal
 * bytes.
 *
 * Handshake (see routers/dashboard/it_server_registry.py for the server side):
 *   1. POST .../credentials/{id}/terminal-ticket  — on the IT-gated router
 *   2. open the WebSocket
 *   3. first frame sends { ticket, token, cols, rows } — the token is sent in
 *      the frame rather than a header because the WebSocket API cannot set one,
 *      and in the frame rather than the URL because nginx logs URLs.
 */
import { useEffect, useRef, useState } from "react";
import { Loader2, X, TerminalSquare } from "lucide-react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import api from "@/api/client";
import { useAuthStore } from "@/store/authStore";

// Matches the dashboard's own dark surfaces rather than xterm's default black,
// so the modal does not look like a foreign window pasted onto the page.
const THEME = {
  background: "#0b1220", foreground: "#e2e8f0", cursor: "#38bdf8",
  black: "#0b1220", red: "#f87171", green: "#4ade80", yellow: "#fbbf24",
  blue: "#60a5fa", magenta: "#c084fc", cyan: "#22d3ee", white: "#e2e8f0",
  brightBlack: "#475569", brightRed: "#fca5a5", brightGreen: "#86efac",
  brightYellow: "#fcd34d", brightBlue: "#93c5fd", brightMagenta: "#d8b4fe",
  brightCyan: "#67e8f9", brightWhite: "#f8fafc",
};

export default function ServerTerminal({ credential, serverName, onClose }) {
  const hostRef = useRef(null);
  const termRef = useRef(null);
  const wsRef = useRef(null);
  const [status, setStatus] = useState("connecting"); // connecting | ready | closed | error
  const [message, setMessage] = useState("");

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

    const start = async () => {
      let ticket;
      try {
        const res = await api.post(
          `/dashboard/it/server-registry/credentials/${credential.id}/terminal-ticket`, {},
        );
        ticket = res.ticket;
      } catch (e) {
        if (cancelled) return;
        setStatus("error");
        setMessage(e?.detail || e?.message || "Gagal meminta tiket sesi");
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

      ws.onopen = () => {
        ws.send(JSON.stringify({
          ticket,
          token: useAuthStore.getState().token,
          cols: term.cols, rows: term.rows,
        }));
      };

      ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        if (msg.type === "ready") {
          setStatus("ready");
          setMessage(`${msg.user}@${msg.host}`);
          term.focus();
        } else if (msg.type === "output") {
          term.write(msg.data);
        } else if (msg.type === "error") {
          setStatus("error");
          setMessage(msg.message);
          term.write(`\r\n\x1b[31m${msg.message}\x1b[0m\r\n`);
        }
      };

      ws.onclose = () => {
        // Only downgrade the status — an error already shown is more
        // informative than "sesi ditutup" replacing it.
        setStatus((s) => (s === "error" ? s : "closed"));
      };

      term.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "input", data }));
        }
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
  }, [credential.id]);

  const dot = { connecting: "#f59e0b", ready: "#22c55e", closed: "#94a3b8", error: "#ef4444" }[status];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(2,6,23,0.72)" }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="flex flex-col w-full" style={{
        maxWidth: 1100, height: "min(80vh, 680px)", background: "#0b1220",
        borderRadius: 12, border: "1px solid rgba(148,163,184,0.25)", overflow: "hidden",
      }}>
        <div className="flex items-center justify-between gap-3 px-3.5 py-2.5"
          style={{ borderBottom: "1px solid rgba(148,163,184,0.18)" }}>
          <div className="flex items-center gap-2 min-w-0">
            <TerminalSquare size={15} color="#38bdf8" />
            <span style={{ fontSize: 12.5, fontWeight: 700, color: "#e2e8f0" }}>{serverName}</span>
            {credential.label && (
              <span style={{ fontSize: 11, color: "#64748b" }}>· {credential.label}</span>
            )}
            <span className="flex items-center gap-1.5" style={{ fontSize: 11, color: "#94a3b8" }}>
              <span style={{ width: 7, height: 7, borderRadius: 99, background: dot, display: "inline-block" }} />
              {status === "connecting" ? "menyambung…" : message || status}
            </span>
          </div>
          <button onClick={onClose} title="Tutup sesi"
            style={{ background: "none", border: "none", cursor: "pointer", color: "#94a3b8", lineHeight: 0 }}>
            <X size={16} />
          </button>
        </div>

        <div className="relative flex-1 min-h-0">
          {status === "connecting" && (
            <div className="absolute inset-0 flex items-center justify-center gap-2"
              style={{ color: "#94a3b8", fontSize: 12, zIndex: 1, pointerEvents: "none" }}>
              <Loader2 size={14} className="animate-spin" /> membuka sesi SSH…
            </div>
          )}
          <div ref={hostRef} style={{ position: "absolute", inset: 0, padding: 8 }} />
        </div>
      </div>
    </div>
  );
}
