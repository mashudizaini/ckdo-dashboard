import { MessageSquare, Database } from "lucide-react";

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
      "How did sales perform in period 2026-06?",
      "Compare budget vs actual for the Admin department in period 2026-06",
      "How did production perform in period 2026-05?",
      "Financial summary for period 2026-06",
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
};

export const CHAT_MODE_ORDER = ["policy", "oracle"];
