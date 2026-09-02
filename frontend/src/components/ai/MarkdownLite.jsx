import { useMemo } from "react";

/**
 * Lightweight markdown renderer shared by both AI Chatbot surfaces (the
 * full /ai/chatbot page and the floating ChatWidget) — handles the subset
 * of markdown the chat system prompts actually ask models to use (bold,
 * italic, inline code, headings, lists, tables, blockquotes). Originally
 * written for ChatWidget only; extracted here so Chatbot.jsx renders
 * identically instead of showing raw asterisks/hashes from the same model
 * output. No external dependency (react-markdown etc.) needed for this
 * subset, and avoids adding a new package to the deploy image.
 */
export function mdToHtml(raw) {
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

export function MdBlock({ text, className = "" }) {
  const html = useMemo(() => mdToHtml(text), [text]);
  return <div className={`md-msg ${className}`} dangerouslySetInnerHTML={{ __html: html }} />;
}
