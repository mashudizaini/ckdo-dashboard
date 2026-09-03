import { useState } from "react";
import { BookOpen, FileStack, SlidersHorizontal } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import KnowledgeBaseManager from "@/pages/setup/ai/KnowledgeBaseManager";
import DocumentConverter from "@/pages/ai-tools/DocumentConverter";
import ModelAccessPanel from "@/pages/setup/ai/ModelAccessPanel";

// Knowledge Base moved here from a button inside the AI Chatbot page, and
// Document Converter from its own AI Tools nav entry (2026-09-03) — both
// are content-management concerns admins/staff configure, not something
// every chatbot reader needs to see a button for. Knowledge Base keeps its
// existing role gate (same roles that could already manage it); Document
// Converter keeps its previous no-role-gate (any authenticated user) since
// moving it here isn't meant to newly restrict who can use it.
//
// Model Access (2026-09-03) is a usage/cost control lever (which chat
// providers users may pick at all) — gated tighter, IT/admin only, matching
// the backend's PUT /provider-status/{provider} role gate.
const TABS = [
  { id: "knowledge-base",     icon: BookOpen,           label: "Knowledge Base",     visible: (r) => r.canManageKB },
  { id: "document-converter", icon: FileStack,          label: "Document Converter", visible: () => true },
  { id: "model-access",       icon: SlidersHorizontal,  label: "Model Access",       visible: (r) => r.isITorAdmin },
];

export default function AiSetupPage() {
  const { hasAnyRole } = useAuthStore();
  const roles = {
    canManageKB: hasAnyRole("it_staff", "hr_staff", "accounting_staff", "pac_staff", "purchasing_staff", "admin"),
    isITorAdmin: hasAnyRole("it_staff", "admin"),
  };
  const tabs = TABS.filter(t => t.visible(roles));

  const [activeId, setActiveId] = useState(tabs[0]?.id);

  if (tabs.length === 0) {
    return (
      <div className="p-6">
        <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900 px-8 py-16 text-center">
          <p className="text-sm text-gray-400">You don't have access to any modules here.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex gap-2 flex-wrap">
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveId(t.id)}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold transition-colors ${
              activeId === t.id
                ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                : "border-gray-800 bg-gray-900 text-gray-400 hover:border-gray-700"
            }`}>
            <t.icon size={14} /> {t.label}
          </button>
        ))}
      </div>
      {activeId === "knowledge-base"     && <KnowledgeBaseManager />}
      {activeId === "document-converter" && <DocumentConverter />}
      {activeId === "model-access"       && <ModelAccessPanel />}
    </div>
  );
}
