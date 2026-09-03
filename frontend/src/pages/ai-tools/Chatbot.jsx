import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Loader2, KeyRound, RotateCcw, Copy, Check } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";
import { CHAT_MODES, CHAT_MODE_ORDER } from "@/config/chatModes";
import { renderSource } from "@/components/ai/ChatSourceBadges";
import { MdBlock } from "@/components/ai/MarkdownLite";
import ApiKeyModal from "@/components/ai/ApiKeyModal";

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch (_) {}
      }}
      title="Copy"
      className="shrink-0 self-start p-1 rounded text-gray-600 hover:text-gray-300 hover:bg-gray-700/50 transition-colors"
    >
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
    </button>
  );
}

export default function Chatbot() {
  const [activeTab, setActiveTab] = useState("policy");
  const [provider, setProvider] = useState("onprem");
  const [showApiKey, setShowApiKey] = useState(false);
  const bottomRef = useRef(null);

  // Claude isn't wired into Oracle EBS Data Chat's tool-calling pipeline
  // yet (see chatbot.py) — the dropdown below disables selecting it while
  // that tab is active, but if it was already selected on a different tab
  // before switching here, fall back automatically instead of letting the
  // next message hit the backend's 400.
  useEffect(() => {
    if (activeTab === "oracle" && provider === "anthropic") setProvider("gemini");
  }, [activeTab, provider]);

  // All 3 modes stay mounted (via their own hook instance) at all times, so
  // switching tabs preserves each conversation's history instead of
  // resetting it — each has its own localStorage key too.
  const policyChat  = useChatStream(CHAT_MODES.policy.greeting,  CHAT_MODES.policy.storageKey,  CHAT_MODES.policy.endpoint,  provider);
  const oracleChat  = useChatStream(CHAT_MODES.oracle.greeting,  CHAT_MODES.oracle.storageKey,  CHAT_MODES.oracle.endpoint,  provider);
  const generalChat = useChatStream(CHAT_MODES.general.greeting, CHAT_MODES.general.storageKey, CHAT_MODES.general.endpoint, provider);

  const chats = { policy: policyChat, oracle: oracleChat, general: generalChat };
  const chat = chats[activeTab];
  const mode = CHAT_MODES[activeTab];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, activeTab]);

  return (
    <div className="flex flex-col h-full p-6">
      <style>{`
        .md-msg { line-height: 1.6; }
        .md-msg p { margin: 0 0 8px; }
        .md-msg p:last-child { margin-bottom: 0; }
        .md-msg ul, .md-msg ol { margin: 4px 0; padding-left: 20px; }
        .md-msg li { margin: 2px 0; }
        .md-msg strong { font-weight: 700; }
        .md-msg em { font-style: italic; }
        .md-msg h1 { font-size: 1.05em; font-weight: 700; margin: 8px 0 4px; }
        .md-msg h2 { font-size: 1em; font-weight: 700; margin: 6px 0 3px; }
        .md-msg h3 { font-size: 0.95em; font-weight: 700; margin: 5px 0 3px; }
        .md-msg blockquote { border-left: 3px solid currentColor; margin: 6px 0; padding: 2px 10px; opacity: 0.8; font-style: italic; }
        .md-msg table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 0.9em; }
        .md-msg th, .md-msg td { padding: 6px 10px; text-align: left; border: 1px solid rgba(255,255,255,0.1); }
        .md-msg th { font-weight: 700; background: rgba(255,255,255,0.06); }
        .md-msg tr:nth-child(even) td { background: rgba(255,255,255,0.03); }
        .md-msg code { background: rgba(255,255,255,0.1); padding: 1px 5px; border-radius: 4px; font-family: monospace; font-size: 0.9em; }
      `}</style>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Bot className="text-blue-400" size={26} />
            AI Chatbot
          </h1>
          <p className="text-gray-500 text-sm mt-1">Company policy, Oracle ERP data, and general questions — all in one place</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            title="AI provider"
            className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 outline-none focus:border-blue-500 cursor-pointer"
          >
            <option value="onprem">Standard (On-Premise)</option>
            <option value="gemini">Gemini</option>
            <option value="anthropic" disabled={activeTab === "oracle"}>
              Claude{activeTab === "oracle" ? " (not available for Oracle ERP Data chat)" : ""}
            </option>
          </select>
          {provider !== "onprem" && (
            <button onClick={() => setShowApiKey(true)} title={`Pakai API key ${provider === "anthropic" ? "Claude" : "Gemini"} pribadi Anda sendiri`}
              className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 hover:border-violet-500 hover:text-violet-400 transition-colors">
              <KeyRound size={14} /> My API Key
            </button>
          )}
          <button
            onClick={() => { if (confirm("Clear this conversation's history? This cannot be undone.")) chat.clearHistory(); }}
            title="Riwayat percakapan tersimpan di browser ini dan ikut dikirim sebagai konteks di setiap pertanyaan baru — kosongkan kalau jawaban lama masih 'nyangkut' meski Knowledge Base sudah diubah."
            className="flex items-center gap-2 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-xs font-medium text-gray-300 hover:border-amber-500 hover:text-amber-400 transition-colors">
            <RotateCcw size={14} /> Clear Conversation
          </button>
        </div>
      </div>

      {showApiKey && provider !== "onprem" && <ApiKeyModal provider={provider} onClose={() => setShowApiKey(false)} />}

      {/* Mode tabs */}
      <div className="mb-4 flex gap-1 border-b border-gray-800">
        {CHAT_MODE_ORDER.map((key) => {
          const m = CHAT_MODES[key];
          const Icon = m.icon;
          const isActive = activeTab === key;
          return (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                isActive ? m.tabActive : "border-transparent text-gray-500 hover:text-gray-300"
              }`}
            >
              <Icon size={15} />
              {m.label}
            </button>
          );
        })}
      </div>

      {/* Chat container */}
      <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 flex-1 overflow-hidden">
        {/* Chat Header */}
        <div className={`flex items-center gap-3 px-5 py-4 border-b border-gray-800 bg-gradient-to-r ${mode.gradient}`}>
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
            <mode.icon size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">{mode.subtitle}</p>
            <p className="text-xs text-white/70">{mode.subtitle2}</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-white/70">
            <span className={`h-2 w-2 rounded-full ${chat.streaming ? "bg-amber-400 animate-pulse" : "bg-green-400"}`} />
            {chat.streaming
              ? (activeTab === "general" && (provider === "anthropic" || provider === "gemini") ? "Mencari di web..." : mode.thinkingLabel)
              : "Online"}
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {chat.messages.map((msg, i) => {
            const isLast = i === chat.messages.length - 1;
            const isBot = msg.role !== "user";
            return (
              <div key={i} className={`group flex gap-3 items-start ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                  msg.role === "user" ? mode.userAvatar : "bg-gray-700"
                }`}>
                  {msg.role === "user" ? <User size={14} className="text-white" /> : <Bot size={14} className="text-gray-300" />}
                </div>
                <div className={`max-w-md rounded-xl px-4 py-3 text-sm ${
                  msg.error
                    ? "bg-red-500/10 border border-red-500/30 text-red-400"
                    : msg.role === "user"
                      ? `${mode.userBubble} text-white rounded-tr-sm`
                      : "bg-gray-800 text-gray-200 rounded-tl-sm"
                }`}>
                  {msg.text
                    ? <MdBlock text={msg.text} className={msg.role === "user" ? "md-user" : "md-bot"} />
                    : (chat.streaming && isLast ? <Loader2 size={14} className="animate-spin" /> : "")}
                  {activeTab !== "policy" && msg.sources?.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-700 flex flex-wrap gap-1.5">
                      {msg.sources.map((s, j) => renderSource(activeTab, s, j))}
                    </div>
                  )}
                  {activeTab === "policy" && isBot && isLast && !chat.streaming && msg.suggestions?.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-gray-700 flex flex-wrap gap-1.5">
                      {msg.suggestions.map((s, j) => (
                        <button key={j} onClick={() => chat.sendMessage(s)}
                          className="rounded-full border border-gray-700 bg-gray-900 px-2.5 py-1 text-xs text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors">
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                {isBot && msg.text && !msg.error && (
                  <div className="opacity-0 group-hover:opacity-100 transition-opacity">
                    <CopyButton text={msg.text} />
                  </div>
                )}
              </div>
            );
          })}
          <div ref={bottomRef} />
        </div>

        {/* Suggestions */}
        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {mode.suggestions.map((s) => (
            <button
              key={s}
              onClick={() => chat.setInput(s)}
              className={`rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 transition-colors ${mode.suggestHover}`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="flex gap-3 border-t border-gray-800 p-4">
          <input
            type="text"
            value={chat.input}
            onChange={(e) => chat.setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && chat.sendMessage()}
            disabled={chat.streaming}
            placeholder="Type your question..."
            className={`flex-1 rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none transition-colors disabled:opacity-50 ${mode.focusRing}`}
          />
          <button
            onClick={() => chat.sendMessage()}
            disabled={chat.streaming || !chat.input.trim()}
            className={`flex h-10 w-10 items-center justify-center rounded-full disabled:opacity-50 transition-colors ${mode.sendBtn}`}
          >
            {chat.streaming ? <Loader2 size={16} className="text-white animate-spin" /> : <Send size={16} className="text-white" />}
          </button>
        </div>
      </div>
    </div>
  );
}
