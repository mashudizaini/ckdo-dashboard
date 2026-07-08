import { useState, useRef, useEffect } from "react";
import { useAuthStore } from "@/store/authStore";

/**
 * Shared streaming-chat logic for the AI Chatbot — used by both the full
 * /ai/chatbot page and the floating mini ChatWidget so the SSE parsing
 * logic lives in exactly one place.
 *
 * storageKey: optional localStorage key to persist messages across sessions.
 */
export function useChatStream(initialGreeting, storageKey = null) {
  const { token } = useAuthStore();

  const [messages, setMessages] = useState(() => {
    if (storageKey) {
      try {
        const saved = JSON.parse(localStorage.getItem(storageKey));
        if (Array.isArray(saved) && saved.length > 0) return saved;
      } catch {}
    }
    return initialGreeting ? [{ role: "assistant", text: initialGreeting }] : [];
  });

  const [input, setInput]       = useState("");
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef(null);

  // Persist to localStorage after each completed response
  useEffect(() => {
    if (streaming || !storageKey) return;
    const toSave = messages.filter(m => m.text).slice(-100);
    try { localStorage.setItem(storageKey, JSON.stringify(toSave)); } catch {}
  }, [messages, streaming]); // eslint-disable-line react-hooks/exhaustive-deps

  const clearHistory = () => {
    const fresh = initialGreeting ? [{ role: "assistant", text: initialGreeting }] : [];
    setMessages(fresh);
    if (storageKey) { try { localStorage.removeItem(storageKey); } catch {} }
  };

  const sendMessage = async (textOverride) => {
    const text = (textOverride ?? input).trim();
    if (!text || streaming) return;

    const history = messages
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.text }));

    setMessages((prev) => [...prev, { role: "user", text }, { role: "assistant", text: "", sources: [] }]);
    setInput("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/v1/ai/chatbot/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: text, conversation_history: history }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer    = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6);
          if (payload === "[DONE]") continue;
          try {
            const evt = JSON.parse(payload);
            if (evt.type === "token") {
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { ...next[next.length - 1], text: next[next.length - 1].text + evt.text };
                return next;
              });
            } else if (evt.type === "sources") {
              setMessages((prev) => {
                const next = [...prev];
                next[next.length - 1] = { ...next[next.length - 1], sources: evt.sources };
                return next;
              });
            }
          } catch (_) {}
        }
      }
    } catch (e) {
      if (e.name === "AbortError") return;
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", text: `Maaf, terjadi kesalahan: ${e.message}`, error: true };
        return next;
      });
    } finally {
      setStreaming(false);
    }
  };

  return { messages, input, setInput, streaming, sendMessage, clearHistory };
}
