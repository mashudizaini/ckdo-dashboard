import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { X, Send, User, Loader2 } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "8px 8px 18px #c5cad8, -8px -8px 18px #ffffff",
  shadowBtn: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
};

/* ── Robot icon — square LED eyes, screen-panel look ── */
function RobotIcon({ size = 26, color = "#fff" }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Antenna post */}
      <line x1="15" y1="1" x2="15" y2="5.5" stroke={color} strokeWidth="1.8" strokeLinecap="round" />
      {/* Antenna ball with inner glow ring */}
      <circle cx="15" cy="1.5" r="2" fill={color} />
      <circle cx="15" cy="1.5" r="1" fill="rgba(99,102,241,0.6)" />
      {/* Head */}
      <rect x="3.5" y="5.5" width="23" height="20" rx="5.5" fill="rgba(255,255,255,0.13)" stroke={color} strokeWidth="1.7" />
      {/* Left eye — square LED screen */}
      <rect x="7" y="10" width="6" height="6" rx="2" fill={color} />
      <rect x="8.2" y="11.2" width="3.6" height="3.6" rx="1" fill="#4f46e5" />
      <circle cx="9" cy="12" r="0.6" fill="rgba(255,255,255,0.9)" />
      {/* Right eye — square LED screen */}
      <rect x="17" y="10" width="6" height="6" rx="2" fill={color} />
      <rect x="18.2" y="11.2" width="3.6" height="3.6" rx="1" fill="#4f46e5" />
      <circle cx="19" cy="12" r="0.6" fill="rgba(255,255,255,0.9)" />
      {/* Mouth — pixel bar segments */}
      <rect x="8.5" y="19.5" width="2.5" height="2" rx="0.8" fill={color} />
      <rect x="12"   y="19.5" width="2.5" height="2" rx="0.8" fill={color} />
      <rect x="15.5" y="19.5" width="2.5" height="2" rx="0.8" fill={color} />
      <rect x="19"   y="19.5" width="2.5" height="2" rx="0.8" fill={color} opacity="0.55" />
      {/* Side ears */}
      <rect x="1.2" y="11" width="2.5" height="5.5" rx="1.2" fill={color} />
      <rect x="26.3" y="11" width="2.5" height="5.5" rx="1.2" fill={color} />
    </svg>
  );
}

const FAB_W = 168; // approx pill width (px)
const FAB_H = 48;  // pill height (px)
const POPUP_W = 360;
const POPUP_H = 480;

export default function ChatWidget() {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ right: 20, bottom: 20 });
  const { messages, input, setInput, streaming, sendMessage } = useChatStream(
    "Hi! Ask me anything about your team's data."
  );
  const bottomRef = useRef(null);

  /* ── drag state ── */
  const drag = useRef({ active: false, moved: false, sx: 0, sy: 0, sr: 0, sb: 0 });

  useEffect(() => {
    const onMove = (e) => {
      if (!drag.current.active) return;
      const dx = e.clientX - drag.current.sx;
      const dy = e.clientY - drag.current.sy;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) drag.current.moved = true;
      const newRight  = Math.max(8, Math.min(window.innerWidth  - FAB_W - 8, drag.current.sr - dx));
      const newBottom = Math.max(8, Math.min(window.innerHeight - FAB_H - 8, drag.current.sb - dy));
      setPos({ right: newRight, bottom: newBottom });
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
    setOpen(v => !v);
  };

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  if (location.pathname === "/ai/chatbot") return null;

  /* ── popup position: open above & left of FAB ── */
  const popupRight  = pos.right;
  const popupBottom = pos.bottom + FAB_H + 10;

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
            background: "linear-gradient(135deg, #4f46e5 0%, #7c3aed 60%, #9333ea 100%)",
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
              <p style={{ fontSize: 12, fontWeight: 700, color: "#fff", margin: 0 }}>AI Assistant</p>
              <p style={{ fontSize: 10, color: "rgba(255,255,255,0.75)", margin: 0 }}>
                {streaming ? "Thinking…" : "Online · CKDO Intelligence"}
              </p>
            </div>
            <button onClick={() => setOpen(false)}
              style={{ color: "rgba(255,255,255,0.85)", background: "none", border: "none", cursor: "pointer", padding: 4 }}>
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
                  background: msg.role === "user"
                    ? "linear-gradient(135deg,#4f46e5,#7c3aed)"
                    : "#ede9fe",
                }}>
                  {msg.role === "user"
                    ? <User size={11} color="#fff" />
                    : <RobotIcon size={15} color="#6d28d9" />}
                </div>
                <div style={{
                  maxWidth: "78%", borderRadius: 12, padding: "8px 11px", fontSize: 12, lineHeight: 1.45,
                  background: msg.error
                    ? "#fee2e2"
                    : msg.role === "user"
                    ? "linear-gradient(135deg,#4f46e5,#7c3aed)"
                    : "#f5f3ff",
                  color: msg.error ? "#dc2626" : msg.role === "user" ? "#fff" : "#1e1b4b",
                }}>
                  {msg.text || (streaming && i === messages.length - 1 ? <Loader2 size={12} className="animate-spin" /> : "")}
                  {msg.sources?.length > 0 && (
                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid rgba(0,0,0,0.08)", display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {msg.sources.map((s, j) => (
                        <span key={j} title={`${s.department} · ${s.similarity}`}
                          style={{ fontSize: 9, borderRadius: 8, padding: "1px 6px", background: "#ede9fe", color: "#6d28d9" }}>
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
          <div style={{ display: "flex", gap: 8, padding: 10, borderTop: "1px solid rgba(0,0,0,0.06)", background: NEU.bg, flexShrink: 0 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
              disabled={streaming}
              placeholder="Ask something…"
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
                background: "linear-gradient(135deg,#4f46e5,#7c3aed)",
                color: "#fff", cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                opacity: (streaming || !input.trim()) ? 0.45 : 1, flexShrink: 0,
                transition: "opacity 0.15s",
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
            : "0 8px 28px rgba(124,58,237,0.5), 0 2px 8px rgba(0,0,0,0.15), 4px 4px 12px #c5cad8, -4px -4px 12px #fff",
          transition: "background 0.22s, box-shadow 0.22s, padding 0.18s",
          whiteSpace: "nowrap",
          userSelect: "none",
        }}
      >
        {open ? (
          <>
            <X size={17} color="#6d28d9" />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#6d28d9", letterSpacing: 0.2 }}>Close</span>
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
