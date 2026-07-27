import { MessageSquare, Database, MessageCircle } from "lucide-react";

/**
 * Shared AI Chatbot mode config — single source of truth for both the full
 * /ai/chatbot page and the floating ChatWidget, so the two surfaces always
 * agree on which endpoint/localStorage key/greeting belongs to which mode
 * (and therefore share the same conversation history per mode).
 */
export const CHAT_MODES = {
  policy: {
    key: "policy",
    label: "Company Policy",
    shortLabel: "Policy",
    icon: MessageSquare,
    subtitle: "Ask me anything",
    subtitle2: "AI-powered insights, grounded in company documents",
    greeting: "Hello! I'm the CKDO Dashboard AI Assistant. Ask me anything about company data.",
    endpoint: "/api/v1/ai/chatbot/chat",
    storageKey: "ckdo_chat_policy",
    suggestions: [
      "What's the total revenue this month?",
      "Current production batch status?",
      "Employee attendance summary?",
      "How many POs are pending approval?",
    ],
    thinkingLabel: "Thinking...",
    gradient: "from-blue-600 to-blue-800",
    tabActive: "border-blue-500 text-blue-400",
    userBubble: "bg-blue-600",
    userAvatar: "bg-blue-600",
    sendBtn: "bg-blue-600 hover:bg-blue-700",
    focusRing: "focus:border-blue-500",
    suggestHover: "hover:border-blue-500 hover:text-blue-400",
  },
  oracle: {
    key: "oracle",
    label: "Oracle ERP",
    shortLabel: "Oracle",
    icon: Database,
    subtitle: "Ask about company data",
    subtitle2: "Tool-calling over Postgres EIS — live queries, not guesses",
    greeting: "Hello! I'm the CKDO Data Assistant. Ask me anything about the company's sales, production, budget, or financial data (source: Oracle EBS).",
    endpoint: "/api/v1/ai/chatbot/oracle-chat",
    storageKey: "ckdo_chat_oracle",
    suggestions: [
      "Bagaimana performa penjualan periode 2026-06?",
      "Bandingkan budget vs aktual departemen Admin periode 2026-06",
      "Bagaimana performa produksi periode 2026-05?",
      "Ringkasan keuangan periode 2026-06",
    ],
    thinkingLabel: "Querying...",
    gradient: "from-emerald-600 to-emerald-800",
    tabActive: "border-emerald-500 text-emerald-400",
    userBubble: "bg-emerald-600",
    userAvatar: "bg-emerald-600",
    sendBtn: "bg-emerald-600 hover:bg-emerald-700",
    focusRing: "focus:border-emerald-500",
    suggestHover: "hover:border-emerald-500 hover:text-emerald-400",
  },
  general: {
    key: "general",
    label: "General",
    shortLabel: "General",
    icon: MessageCircle,
    subtitle: "Ask me anything",
    subtitle2: "General-purpose assistant — no company documents or ERP data",
    greeting: "Hello! Ask me anything — general questions, writing help, quick lookups, and more.",
    endpoint: "/api/v1/ai/chatbot/general-chat",
    storageKey: "ckdo_chat_general",
    suggestions: [
      "Terjemahkan 'follow up' ke Bahasa Indonesia formal",
      "Ringkas paragraf berikut jadi 3 poin",
      "Bantu draft email follow-up ke vendor",
      "Apa itu inflasi?",
    ],
    thinkingLabel: "Thinking...",
    gradient: "from-violet-600 to-violet-800",
    tabActive: "border-violet-500 text-violet-400",
    userBubble: "bg-violet-600",
    userAvatar: "bg-violet-600",
    sendBtn: "bg-violet-600 hover:bg-violet-700",
    focusRing: "focus:border-violet-500",
    suggestHover: "hover:border-violet-500 hover:text-violet-400",
  },
};

export const CHAT_MODE_ORDER = ["policy", "oracle", "general"];
