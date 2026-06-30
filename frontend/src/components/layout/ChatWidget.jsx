import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { MessageSquare, X, Send, Bot, User, Loader2 } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "8px 8px 18px #c5cad8, -8px -8px 18px #ffffff",
  shadowBtn: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
};

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
            background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
          }}>
            <div style={{
              width: 30, height: 30, borderRadius: "50%", background: "rgba(255,255,255,0.2)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <Bot size={15} color="#fff" />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: 12, fontWeight: 700, color: "#fff" }}>AI Assistant</p>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.75)" }}>{streaming ? "Thinking..." : "Online"}</p>
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
                  width: 22, height: 22, borderRadius: "50%", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: msg.role === "user" ? "#2563eb" : "#e2e8f0",
                }}>
                  {msg.role === "user" ? <User size={11} color="#fff" /> : <Bot size={11} color="#475569" />}
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

      {/* FAB */}
      <button
        onClick={() => setOpen((v) => !v)}
        title="AI Assistant"
        style={{
          width: 54, height: 54, borderRadius: "50%", border: "none", cursor: "pointer",
          background: open ? NEU.bg : "linear-gradient(135deg, #2563eb, #1d4ed8)",
          boxShadow: NEU.shadowBtn,
          display: "flex", alignItems: "center", justifyContent: "center",
          marginLeft: "auto",
        }}
      >
        {open ? <X size={22} color="#475569" /> : <MessageSquare size={22} color="#fff" />}
      </button>
    </div>
  );
}
