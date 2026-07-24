import { useRef, useEffect } from "react";
import { Database, Send, Bot, User, Loader2 } from "lucide-react";
import { useChatStream } from "@/hooks/useChatStream";

const SUGGESTIONS = [
  "Bagaimana performa penjualan periode 2026-06?",
  "Bandingkan budget vs aktual departemen Admin periode 2026-06",
  "Bagaimana performa produksi periode 2026-05?",
  "Ringkasan keuangan periode 2026-06",
];

function ToolBadge({ source }) {
  const argsText = Object.entries(source.arguments || {})
    .map(([k, v]) => `${k}=${v}`)
    .join(", ");
  const failed = !!source.error;
  return (
    <span
      title={failed ? source.error : `${source.row_count} row${source.row_count !== 1 ? "s" : ""} returned`}
      className={`text-[10px] rounded-full border px-2 py-0.5 ${
        failed
          ? "border-red-700/50 bg-red-500/10 text-red-400"
          : "border-gray-600 bg-gray-900 text-gray-400"
      }`}
    >
      🛠️ {source.tool}{argsText ? `(${argsText})` : ""}
    </span>
  );
}

export default function ChatOracleData() {
  const { messages, input, setInput, streaming, sendMessage } = useChatStream(
    "Hello! I'm the CKDO Data Assistant. Ask me anything about the company's sales, production, budget, or financial data (source: Oracle EBS).",
    null,
    "/api/v1/ai/chatbot/oracle-chat",
  );
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col h-full p-6">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <Database className="text-emerald-400" size={26} />
          Oracle EBS Data Chat
        </h1>
        <p className="text-gray-500 text-sm mt-1">Ask about sales, production, budget & financial data — answers come from live queries, not guesses</p>
      </div>

      <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 flex-1 overflow-hidden">
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800 bg-gradient-to-r from-emerald-600 to-emerald-800">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
            <Database size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Ask about company data</p>
            <p className="text-xs text-emerald-200">Tool-calling over Postgres EIS</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-emerald-200">
            <span className={`h-2 w-2 rounded-full ${streaming ? "bg-amber-400 animate-pulse" : "bg-green-400"}`} />
            {streaming ? "Querying..." : "Online"}
          </span>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                msg.role === "user" ? "bg-emerald-600" : "bg-gray-700"
              }`}>
                {msg.role === "user" ? <User size={14} className="text-white" /> : <Bot size={14} className="text-gray-300" />}
              </div>
              <div className={`max-w-md rounded-xl px-4 py-3 text-sm ${
                msg.error
                  ? "bg-red-500/10 border border-red-500/30 text-red-400"
                  : msg.role === "user"
                    ? "bg-emerald-600 text-white rounded-tr-sm"
                    : "bg-gray-800 text-gray-200 rounded-tl-sm"
              }`}>
                {msg.text || (streaming && i === messages.length - 1 ? <Loader2 size={14} className="animate-spin" /> : "")}
                {msg.sources?.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-gray-700 flex flex-wrap gap-1.5">
                    {msg.sources.map((s, j) => <ToolBadge key={j} source={s} />)}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 hover:border-emerald-500 hover:text-emerald-400 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>

        <div className="flex gap-3 border-t border-gray-800 p-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            disabled={streaming}
            placeholder="Type your question..."
            className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-emerald-500 transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => sendMessage()}
            disabled={streaming || !input.trim()}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {streaming ? <Loader2 size={16} className="text-white animate-spin" /> : <Send size={16} className="text-white" />}
          </button>
        </div>
      </div>
    </div>
  );
}
