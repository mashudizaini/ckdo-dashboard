import { useState, useRef, useEffect } from "react";
import { MessageSquare, Send, Bot, User } from "lucide-react";

const SUGGESTIONS = [
  "What's the total revenue this month?",
  "Current production batch status?",
  "Employee attendance summary?",
  "How many POs are pending approval?",
];

export default function Chatbot() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hello! I'm the CKDO Dashboard AI Assistant. Ask me anything about company data.",
    },
  ]);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text) return;
    setMessages((prev) => [
      ...prev,
      { role: "user", text },
      { role: "assistant", text: "AI feature is under development. Please check back later." },
    ]);
    setInput("");
  };

  return (
    <div className="flex flex-col h-full p-6">
      {/* Header */}
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <MessageSquare className="text-blue-400" size={26} />
          AI Chatbot
        </h1>
        <p className="text-gray-500 text-sm mt-1">AI Assistant powered by Claude — Ask anything about company data</p>
      </div>

      {/* Chat container */}
      <div className="flex flex-col rounded-xl border border-gray-800 bg-gray-900 flex-1 overflow-hidden">
        {/* Chat Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-gray-800 bg-gradient-to-r from-blue-600 to-blue-800">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-white/20">
            <Bot size={18} className="text-white" />
          </div>
          <div>
            <p className="text-sm font-semibold text-white">Ask me anything</p>
            <p className="text-xs text-blue-200">AI-powered insights</p>
          </div>
          <span className="ml-auto flex items-center gap-1.5 text-xs text-blue-200">
            <span className="h-2 w-2 rounded-full bg-green-400 animate-pulse" />
            Online
          </span>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
              <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                msg.role === "user" ? "bg-blue-600" : "bg-gray-700"
              }`}>
                {msg.role === "user" ? <User size={14} className="text-white" /> : <Bot size={14} className="text-gray-300" />}
              </div>
              <div className={`max-w-md rounded-xl px-4 py-3 text-sm ${
                msg.role === "user"
                  ? "bg-blue-600 text-white rounded-tr-sm"
                  : "bg-gray-800 text-gray-200 rounded-tl-sm"
              }`}>
                {msg.text}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Suggestions */}
        <div className="px-5 pb-3 flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-400 hover:border-blue-500 hover:text-blue-400 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>

        {/* Input */}
        <div className="flex gap-3 border-t border-gray-800 p-4">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Type your question..."
            className="flex-1 rounded-lg border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors"
          />
          <button
            onClick={handleSend}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 transition-colors"
          >
            <Send size={16} className="text-white" />
          </button>
        </div>
      </div>
    </div>
  );
}
