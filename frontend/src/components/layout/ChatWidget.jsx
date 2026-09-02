import { useState, useRef, useEffect, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { X, Send, User, Loader2, Trash2, KeyRound } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";
import RobotIcon from "@/components/icons/RobotIcon";
import { CHAT_MODES, CHAT_MODE_ORDER } from "@/config/chatModes";
import GeminiApiKeyModal from "@/components/ai/GeminiApiKeyModal";

/* Inline-style color themes per mode — this widget uses inline styles
   throughout (not Tailwind classes), so it needs its own hex palette rather
   than the Tailwind gradient classes the full /ai/chatbot page uses. */
const MODE_STYLE = {
  policy:  { grad: "linear-gradient(135deg, #2563eb 0%, #1e40af 100%)", bubble: "linear-gradient(135deg,#2563eb,#1e40af)", botBg: "#eff6ff", botIcon: "#1d4ed8" },
  oracle:  { grad: "linear-gradient(135deg, #059669 0%, #065f46 100%)", bubble: "linear-gradient(135deg,#059669,#065f46)", botBg: "#ecfdf5", botIcon: "#047857" },
  general: { grad: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 60%, #9333ea 100%)", bubble: "linear-gradient(135deg,#4f46e5,#7c3aed)", botBg: "#ede9fe", botIcon: "#6d28d9" },
};

function renderWidgetSource(modeKey, s, j) {
  if (modeKey === "oracle") {
    const argsText = Object.entries(s.arguments || {}).map(([k, v]) => `${k}=${v}`).join(", ");
    return (
      <span key={j} title={s.error || `${s.row_count} row${s.row_count !== 1 ? "s" : ""} returned`}
        style={{ fontSize: 9, borderRadius: 8, padding: "1px 6px", background: s.error ? "#fee2e2" : "#ecfdf5", color: s.error ? "#dc2626" : "#047857" }}>
        🛠️ {s.tool}{argsText ? `(${argsText})` : ""}
      </span>
    );
  }
  if (modeKey === "policy") {
    return (
      <span key={j} title={`${s.department} · similarity ${s.similarity}`}
        style={{ fontSize: 9, borderRadius: 8, padding: "1px 6px", background: "#ede9fe", color: "#6d28d9" }}>
        📄 {s.title}
      </span>
    );
  }
  return null;
}

const NEU = {
  bg: "#f1f5f9",
  shadowOut: "0 4px 12px rgba(15,23,42,0.10), 0 2px 4px rgba(15,23,42,0.05)",
  shadowBtn: "0 2px 4px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.04)",
};

/* ── Lightweight markdown renderer ── */
function mdToHtml(raw) {
  if (!raw) return "";

  const esc    = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>");

  const lines = raw.split("\n");
  const out   = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Heading
    const hm = line.match(/^(#{1,3})\s+(.+)/);
    if (hm) {
      out.push(`<h${hm[1].length}>${inline(hm[2])}</h${hm[1].length}>`);
      i++; continue;
    }

    // Table
    if (line.startsWith("|")) {
      const tLines = [];
      while (i < lines.length && lines[i].startsWith("|")) { tLines.push(lines[i]); i++; }
      const isSep = (l) => l.split("|").slice(1, -1).every((c) => /^[\s\-:]+$/.test(c));
      const rows  = tLines.filter((l) => !isSep(l));
      if (rows.length) {
        const cells    = (l) => l.split("|").slice(1, -1).map((c) => c.trim());
        const [hdr, ...body] = rows;
        const th = cells(hdr).map((c) => `<th>${inline(c)}</th>`).join("");
        const tr = body.map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("");
        out.push(`<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`);
      }
      continue;
    }

    // Unordered list
    if (/^[-*]\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^[-*]\s/.test(lines[i]))
        items.push(`<li>${inline(lines[i++].replace(/^[-*]\s/, ""))}</li>`);
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    // Ordered list
    if (/^\d+\.\s/.test(line)) {
      const items = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i]))
        items.push(`<li>${inline(lines[i++].replace(/^\d+\.\s/, ""))}</li>`);
      out.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    // Blockquote
    if (line.startsWith("> ")) {
      const qLines = [];
      while (i < lines.length && lines[i].startsWith("> ")) qLines.push(lines[i++].slice(2));
      out.push(`<blockquote>${inline(qLines.join(" "))}</blockquote>`);
      continue;
    }

    // Empty line
    if (!line.trim()) { i++; continue; }

    // Paragraph
    const pLines = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].startsWith("|") &&
      !/^[-*]\s/.test(lines[i]) &&
      !/^\d+\.\s/.test(lines[i]) &&
      !lines[i].startsWith("> ") &&
      !/^#{1,3}\s/.test(lines[i])
    ) pLines.push(lines[i++]);
    if (pLines.length) out.push(`<p>${inline(pLines.join("<br>"))}</p>`);
  }

  return out.join("");
}

function MdBlock({ text, isUser }) {
  const html = useMemo(() => mdToHtml(text), [text]);
  return (
    <div
      className={`md-msg${isUser ? " md-user" : " md-bot"}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

const FAB_W     = 168;
const FAB_H     = 48;
const POPUP_W   = 380;
const POPUP_H   = 540;

export default function ChatWidget() {
  const location = useLocation();
  const [open, setOpen]               = useState(false);
  const [pos, setPos]                 = useState({ right: 20, bottom: 20 });
  const [confirmClear, setConfirmClear] = useState(false);
  const [activeTab, setActiveTab]     = useState("policy");
  const [provider, setProvider]       = useState("onprem");
  const [showApiKey, setShowApiKey]   = useState(false);

  // Claude isn't wired into Oracle EBS Data Chat's tool-calling pipeline
  // yet (see chatbot.py) — mirrors the same fallback in Chatbot.jsx (the
  // full /ai/chatbot page).
  useEffect(() => {
    if (activeTab === "oracle" && provider === "anthropic") setProvider("gemini");
  }, [activeTab, provider]);

  // Same localStorage keys/endpoints as the full /ai/chatbot page (see
  // config/chatModes.js) — so a conversation started in the widget
  // continues seamlessly if the user later opens the full page, and vice versa.
  const policyChat  = useChatStream(CHAT_MODES.policy.greeting,  CHAT_MODES.policy.storageKey,  CHAT_MODES.policy.endpoint,  provider);
  const oracleChat  = useChatStream(CHAT_MODES.oracle.greeting,  CHAT_MODES.oracle.storageKey,  CHAT_MODES.oracle.endpoint,  provider);
  const generalChat = useChatStream(CHAT_MODES.general.greeting, CHAT_MODES.general.storageKey, CHAT_MODES.general.endpoint, provider);
  const chats = { policy: policyChat, oracle: oracleChat, general: generalChat };
  const { messages, input, setInput, streaming, sendMessage, clearHistory } = chats[activeTab];
  const style = MODE_STYLE[activeTab];

  const bottomRef = useRef(null);
  const drag      = useRef({ active: false, moved: false, sx: 0, sy: 0, sr: 0, sb: 0 });

  /* ── drag ── */
  useEffect(() => {
    const onMove = (e) => {
      if (!drag.current.active) return;
      const dx = e.clientX - drag.current.sx;
      const dy = e.clientY - drag.current.sy;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) drag.current.moved = true;
      setPos({
        right:  Math.max(8, Math.min(window.innerWidth  - FAB_W - 8, drag.current.sr - dx)),
        bottom: Math.max(8, Math.min(window.innerHeight - FAB_H - 8, drag.current.sb - dy)),
      });
    };
    const onUp = () => { drag.current.active = false; };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup",   onUp);
    return () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup",   onUp);
    };
  }, []);

  const onFabDown = (e) => {
    if (e.button !== 0) return;
    drag.current = { active: true, moved: false, sx: e.clientX, sy: e.clientY, sr: pos.right, sb: pos.bottom };
    e.preventDefault();
  };
  const onFabClick = () => {
    if (drag.current.moved) { drag.current.moved = false; return; }
    setOpen((v) => !v);
    setConfirmClear(false);
  };

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open, activeTab]);

  if (location.pathname === "/ai/chatbot") return null;

  const popupRight  = pos.right;
  const popupBottom = pos.bottom + FAB_H + 10;

  const handleClearClick = () => {
    if (confirmClear) { clearHistory(); setConfirmClear(false); }
    else setConfirmClear(true);
  };

  return (
    <>
      <style>{`
        @keyframes ai-ring {
          0%   { box-shadow: 0 0 0 0 rgba(139,92,246,0.65); }
          70%  { box-shadow: 0 0 0 12px rgba(139,92,246,0); }
          100% { box-shadow: 0 0 0 0 rgba(139,92,246,0); }
        }
        .ai-fab-idle { animation: ai-ring 2.6s ease-out infinite; }
        .ai-fab-idle:hover { filter: brightness(1.12); }

        /* ── Markdown styles ── */
        .md-msg { font-size: 12px; line-height: 1.55; }
        .md-msg p { margin: 0 0 6px; }
        .md-msg p:last-child { margin-bottom: 0; }
        .md-msg ul, .md-msg ol { margin: 3px 0; padding-left: 16px; }
        .md-msg li { margin: 2px 0; }
        .md-msg strong { font-weight: 700; }
        .md-msg em { font-style: italic; }
        .md-msg h1 { font-size: 13px; font-weight: 700; margin: 6px 0 3px; }
        .md-msg h2 { font-size: 12.5px; font-weight: 700; margin: 5px 0 2px; }
        .md-msg h3 { font-size: 12px; font-weight: 700; margin: 4px 0 2px; }
        .md-msg blockquote { border-left: 3px solid currentColor; margin: 4px 0; padding: 2px 8px; opacity: 0.75; font-style: italic; }
        .md-msg table { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 11px; }
        .md-msg th, .md-msg td { padding: 4px 8px; text-align: left; }
        .md-msg th { font-weight: 700; }
        /* bot */
        .md-bot th { background: rgba(79,70,229,0.1); border: 1px solid rgba(79,70,229,0.2); }
        .md-bot td { border: 1px solid rgba(79,70,229,0.12); }
        .md-bot tr:nth-child(even) td { background: rgba(79,70,229,0.04); }
        .md-bot code { background: rgba(79,70,229,0.1); color: #4338ca; padding: 1px 4px; border-radius: 3px; font-family: monospace; font-size: 11px; }
        /* user */
        .md-user th { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); }
        .md-user td { border: 1px solid rgba(255,255,255,0.15); }
        .md-user tr:nth-child(even) td { background: rgba(255,255,255,0.08); }
        .md-user code { background: rgba(255,255,255,0.2); padding: 1px 4px; border-radius: 3px; font-family: monospace; font-size: 11px; }
      `}</style>

      {/* Chat popup */}
      {open && (
        <div style={{
          position: "fixed",
          right: popupRight, bottom: popupBottom,
          width: POPUP_W, height: POPUP_H,
          borderRadius: 18, zIndex: 59,
          background: NEU.bg, boxShadow: NEU.shadowOut,
          display: "flex", flexDirection: "column", overflow: "hidden",
        }}>
          {/* Header */}
          <div style={{
            display: "flex", alignItems: "center", gap: 10, padding: "12px 14px",
            background: style.grad, transition: "background 0.2s",
            flexShrink: 0,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: "50%",
              background: "rgba(255,255,255,0.18)",
              display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0,
            }}>
              <RobotIcon size={22} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 12, fontWeight: 700, color: "#fff", margin: 0 }}>{CHAT_MODES[activeTab].label}</p>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.75)", margin: 0 }}>
                {streaming ? "Typing…" : "Online · AI Assistant"}
              </p>
            </div>
            {/* Clear history */}
            <button
              onClick={handleClearClick}
              title={confirmClear ? "Click again to confirm" : "Clear conversation history"}
              style={{
                color: confirmClear ? "#fca5a5" : "rgba(255,255,255,0.65)",
                background: confirmClear ? "rgba(239,68,68,0.2)" : "none",
                border: "none", cursor: "pointer",
                padding: confirmClear ? "3px 7px" : "4px 5px",
                borderRadius: 6, transition: "all 0.15s",
                fontSize: 10, fontWeight: 600, whiteSpace: "nowrap",
                display: "flex", alignItems: "center", gap: 3,
              }}
            >
              <Trash2 size={12} />
              {confirmClear && "Delete?"}
            </button>
            <button
              onClick={() => { setOpen(false); setConfirmClear(false); }}
              style={{ color: "rgba(255,255,255,0.85)", background: "none", border: "none", cursor: "pointer", padding: 4 }}
            >
              <X size={16} />
            </button>
          </div>

          {/* Mode tabs + provider */}
          <div style={{
            display: "flex", alignItems: "center", gap: 6, padding: "8px 10px",
            borderBottom: "1px solid rgba(0,0,0,0.06)", background: "#fff", flexShrink: 0,
          }}>
            {CHAT_MODE_ORDER.map((key) => {
              const m = CHAT_MODES[key];
              const Icon = m.icon;
              const active = activeTab === key;
              return (
                <button
                  key={key}
                  onClick={() => { setActiveTab(key); setConfirmClear(false); }}
                  title={m.label}
                  style={{
                    display: "flex", alignItems: "center", gap: 3, fontSize: 10, fontWeight: 600,
                    padding: "4px 8px", borderRadius: 8, border: "none", cursor: "pointer",
                    background: active ? MODE_STYLE[key].grad : "#f1f5f9",
                    color: active ? "#fff" : "#64748b",
                    transition: "background 0.15s, color 0.15s",
                  }}
                >
                  <Icon size={11} /> {m.shortLabel}
                </button>
              );
            })}
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              title="AI provider"
              style={{
                marginLeft: "auto", fontSize: 10, fontWeight: 600, padding: "4px 6px",
                borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff",
                color: "#475569", cursor: "pointer",
              }}
            >
              <option value="onprem">Standard</option>
              <option value="gemini">Gemini</option>
              <option value="anthropic" disabled={activeTab === "oracle"}>Claude</option>
            </select>
            <button
              onClick={() => setShowApiKey(true)}
              title="API Key Gemini pribadi"
              style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                width: 22, height: 22, borderRadius: 6, border: "1px solid #e2e8f0",
                background: "#fff", color: "#64748b", cursor: "pointer", flexShrink: 0,
              }}
            >
              <KeyRound size={11} />
            </button>
          </div>

          {showApiKey && <GeminiApiKeyModal onClose={() => setShowApiKey(false)} />}

          {/* Messages */}
          <div style={{
            flex: 1, overflowY: "auto", padding: "12px 12px 4px",
            display: "flex", flexDirection: "column", gap: 10,
            background: "#fff",
          }}>
            {messages.map((msg, i) => (
              <div key={i} style={{ display: "flex", gap: 6, flexDirection: msg.role === "user" ? "row-reverse" : "row", alignItems: "flex-start" }}>
                {/* Avatar */}
                <div style={{
                  width: 26, height: 26, borderRadius: "50%", flexShrink: 0, marginTop: 2,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: msg.role === "user" ? style.bubble : style.botBg,
                }}>
                  {msg.role === "user"
                    ? <User size={12} color="#fff" />
                    : <RobotIcon size={15} color={style.botIcon} />}
                </div>
                {/* Bubble */}
                <div style={{
                  maxWidth: "80%",
                  borderRadius: msg.role === "user" ? "14px 4px 14px 14px" : "4px 14px 14px 14px",
                  padding: "8px 11px",
                  background: msg.error
                    ? "#fee2e2"
                    : msg.role === "user"
                    ? style.bubble
                    : style.botBg,
                  color: msg.error ? "#dc2626" : msg.role === "user" ? "#fff" : "#1e1b4b",
                }}>
                  {streaming && i === messages.length - 1 && !msg.text
                    ? <Loader2 size={12} className="animate-spin" />
                    : <MdBlock text={msg.text} isUser={msg.role === "user"} />
                  }
                  {msg.sources?.length > 0 && (
                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid rgba(0,0,0,0.08)", display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {msg.sources.map((s, j) => renderWidgetSource(activeTab, s, j))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} style={{ height: 4 }} />
          </div>

          {/* Input */}
          <div style={{
            display: "flex", gap: 8, padding: 10,
            borderTop: "1px solid rgba(0,0,0,0.06)",
            background: NEU.bg, flexShrink: 0,
          }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMessage()}
              disabled={streaming}
              placeholder="Type your question…"
              style={{
                flex: 1, fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none",
                background: "#fff", color: "#1e293b", outline: "none",
                boxShadow: "inset 0 1px 3px rgba(15,23,42,0.07)",
              }}
            />
            <button
              onClick={() => sendMessage()}
              disabled={streaming || !input.trim()}
              style={{
                width: 34, height: 34, borderRadius: "50%", border: "none",
                background: style.bubble,
                color: "#fff", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                opacity: (streaming || !input.trim()) ? 0.45 : 1, flexShrink: 0,
                transition: "opacity 0.15s, background 0.2s",
              }}
            >
              {streaming ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            </button>
          </div>
        </div>
      )}

      {/* FAB — draggable pill */}
      <button
        onMouseDown={onFabDown}
        onClick={onFabClick}
        title="AI Assistant — drag to move"
        className={open ? "" : "ai-fab-idle"}
        style={{
          position: "fixed",
          right: pos.right, bottom: pos.bottom,
          zIndex: 60,
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: open ? 7 : 10,
          height: FAB_H,
          padding: open ? "0 18px" : "0 20px 0 14px",
          borderRadius: 24, border: "none",
          cursor: drag.current.active ? "grabbing" : "grab",
          background: open
            ? NEU.bg
            : "linear-gradient(135deg, #4f46e5 0%, #7c3aed 55%, #9333ea 100%)",
          boxShadow: open
            ? NEU.shadowBtn
            : "0 8px 28px rgba(124,58,237,0.5), 0 2px 8px rgba(0,0,0,0.15)",
          transition: "background 0.22s, box-shadow 0.22s, padding 0.18s",
          whiteSpace: "nowrap",
          userSelect: "none",
        }}
      >
        {open ? (
          <>
            <X size={17} color="#6d28d9" />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#6d28d9", letterSpacing: 0.2 }}>Tutup</span>
          </>
        ) : (
          <>
            <RobotIcon size={25} color="#fff" />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#fff", letterSpacing: 0.4 }}>AI Assistant</span>
          </>
        )}
      </button>
    </>
  );
}
