import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { X, Send, User, Loader2 } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "8px 8px 18px #c5cad8, -8px -8px 18px #ffffff",
  shadowBtn: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
};

/* ── Custom robot-face SVG icon ──────────────────────── */
function RobotIcon({ size = 26, color = "#fff" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Antenna post */}
      <line x1="14" y1="1.5" x2="14" y2="5.5" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      {/* Antenna ball */}
      <circle cx="14" cy="1.5" r="1.6" fill={color} />
      {/* Head */}
      <rect x="3" y="5.5" width="22" height="18" rx="4.5" fill="rgba(255,255,255,0.12)" stroke={color} strokeWidth="1.6" />
      {/* Left eye */}
      <circle cx="10" cy="13" r="2.8" fill={color} />
      <circle cx="10" cy="13" r="1.3" fill="#1d4ed8" />
      <circle cx="10.7" cy="12.1" r="0.5" fill={color} />
      {/* Right eye */}
      <circle cx="18" cy="13" r="2.8" fill={color} />
      <circle cx="18" cy="13" r="1.3" fill="#1d4ed8" />
      <circle cx="18.7" cy="12.1" r="0.5" fill={color} />
      {/* Mouth — smile */}
      <path d="M10 18.5 Q14 21 18 18.5" stroke={color} strokeWidth="1.6" strokeLinecap="round" fill="none" />
      {/* Ear left */}
      <rect x="1" y="10" width="2.2" height="6" rx="1.1" fill={color} />
      {/* Ear right */}
      <rect x="24.8" y="10" width="2.2" height="6" rx="1.1" fill={color} />
    </svg>
  );
}

/**
 * Floating mini AI chatbot — attached to every dashboard/AI-tools page via
 * Layout.jsx. Same backend + department-scoped RAG as the full /ai/chatbot
 * page, just in a compact popover so users don't have to navigate away.
 */
export default function ChatWidget() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const { messages, input, setInput, streaming, sendMessage } = useChatStream(
    "Hi! Ask me anything about your team's data."
  );
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  // Hide on the full chatbot page itself — avoid a redundant floating button there
  if (location.pathname === "/ai/chatbot") return null;

  return (
    <>
      {/* pulse-ring keyframe */}
      <style>{`
        @keyframes ai-pulse {
          0%   { box-shadow: 0 0 0 0 rgba(59,130,246,0.55); }
          70%  { box-shadow: 0 0 0 10px rgba(59,130,246,0); }
          100% { box-shadow: 0 0 0 0 rgba(59,130,246,0); }
        }
        .ai-fab-pulse { animation: ai-pulse 2.4s ease-out infinite; }
      `}</style>

      <div style={{ position: "fixed", bottom: 20, right: 20, zIndex: 60 }}>
        {open && (
          <div style={{
            width: 360, height: 480, marginBottom: 12, borderRadius: 18,
            background: NEU.bg, boxShadow: NEU.shadowOut,
            display: "flex", flexDirection: "column", overflow: "hidden",
          }}>
            {/* Header */}
            <div style={{
              display: "flex", alignItems: "center", gap: 10, padding: "12px 14px",
              background: "linear-gradient(135deg, #3b82f6, #1d4ed8)",
            }}>
              <div style={{
                width: 34, height: 34, borderRadius: "50%", background: "rgba(255,255,255,0.15)",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}>
                <RobotIcon size={20} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 12, fontWeight: 700, color: "#fff", margin: 0 }}>AI Assistant</p>
                <p style={{ fontSize: 10, color: "rgba(255,255,255,0.75)", margin: 0 }}>
                  {streaming ? "Thinking…" : "Online"}
                </p>
              </div>
              <button onClick={() => setOpen(false)} style={{ color: "#fff", background: "none", border: "none", cursor: "pointer", padding: 4 }}>
                <X size={16} />
              </button>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 10, background: "#fff" }}>
              {messages.map((msg, i) => (
                <div key={i} style={{ display: "flex", gap: 6, flexDirection: msg.role === "user" ? "row-reverse" : "row" }}>
                  <div style={{
                    width: 24, height: 24, borderRadius: "50%", flexShrink: 0,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    background: msg.role === "user" ? "#2563eb" : "#dbeafe",
                  }}>
                    {msg.role === "user"
                      ? <User size={11} color="#fff" />
                      : <RobotIcon size={15} color="#1d4ed8" />}
                  </div>
                  <div style={{
                    maxWidth: "78%", borderRadius: 12, padding: "8px 11px", fontSize: 12, lineHeight: 1.45,
                    background: msg.error ? "#fee2e2" : msg.role === "user" ? "#2563eb" : "#f1f5f9",
                    color: msg.error ? "#dc2626" : msg.role === "user" ? "#fff" : "#1e293b",
                  }}>
                    {msg.text || (streaming && i === messages.length - 1 ? <Loader2 size={12} className="animate-spin" /> : "")}
                    {msg.sources?.length > 0 && (
                      <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid rgba(0,0,0,0.08)", display: "flex", flexWrap: "wrap", gap: 4 }}>
                        {msg.sources.map((s, j) => (
                          <span key={j} title={`${s.department} · similarity: ${s.similarity}`}
                            style={{ fontSize: 9, borderRadius: 8, padding: "1px 6px", background: "#e2e8f0", color: "#64748b" }}>
                            📄 {s.title}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div style={{ display: "flex", gap: 8, padding: 10, borderTop: "1px solid rgba(0,0,0,0.06)", background: NEU.bg }}>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                disabled={streaming}
                placeholder="Ask something..."
                style={{
                  flex: 1, fontSize: 12, padding: "8px 12px", borderRadius: 10, border: "none",
                  background: "#fff", color: "#1e293b", outline: "none",
                  boxShadow: "inset 2px 2px 5px #d6dbe3, inset -2px -2px 5px #ffffff",
                }}
              />
              <button
                onClick={() => sendMessage()}
                disabled={streaming || !input.trim()}
                style={{
                  width: 34, height: 34, borderRadius: "50%", border: "none",
                  background: "#2563eb", color: "#fff", cursor: "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  opacity: (streaming || !input.trim()) ? 0.5 : 1, flexShrink: 0,
                }}
              >
                {streaming ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              </button>
            </div>
          </div>
        )}

        {/* FAB — pill button */}
        <button
          onClick={() => setOpen((v) => !v)}
          title="AI Assistant"
          className={open ? "" : "ai-fab-pulse"}
          style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            gap: open ? 6 : 10,
            height: 48,
            padding: open ? "0 18px" : "0 20px 0 14px",
            borderRadius: 24, border: "none", cursor: "pointer",
            background: open
              ? NEU.bg
              : "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)",
            boxShadow: open
              ? NEU.shadowBtn
              : "0 6px 24px rgba(37,99,235,0.45), 4px 4px 12px #c5cad8, -4px -4px 12px #ffffff",
            marginLeft: "auto",
            transition: "all 0.22s cubic-bezier(.4,0,.2,1)",
            whiteSpace: "nowrap",
          }}
        >
          {open ? (
            <>
              <X size={17} color="#475569" />
              <span style={{ fontSize: 12, fontWeight: 700, color: "#475569", letterSpacing: 0.2 }}>Close</span>
            </>
          ) : (
            <>
              <RobotIcon size={24} color="#fff" />
              <span style={{ fontSize: 12, fontWeight: 700, color: "#fff", letterSpacing: 0.3 }}>AI Assistant</span>
            </>
          )}
        </button>
      </div>
    </>
  );
}
