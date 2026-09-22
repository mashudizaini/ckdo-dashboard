import { useState } from "react";
import { Percent } from "lucide-react";
import SupplierWhtMaster from "@/pages/setup/accounting/SupplierWhtMaster";

// Replaces the generic <SetupPage team="Accounting & Tax" /> placeholder
// (2026-09-09) with real content — currently just Supplier WHT Master, but
// kept as a tab shell so future Accounting & Tax setup modules land here
// the same way General/HR's setup pages do.
const MODULE_TABS = [
  { id: "supplier-wht", icon: Percent, label: "Supplier WHT Master" },
];

export default function AccountingSetupPage() {
  const [activeId, setActiveId] = useState(MODULE_TABS[0].id);

  return (
    <div className="p-6 space-y-4">
      <div className="flex gap-2 flex-wrap">
        {MODULE_TABS.map(t => (
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
      {activeId === "supplier-wht" && <SupplierWhtMaster />}
    </div>
  );
}
