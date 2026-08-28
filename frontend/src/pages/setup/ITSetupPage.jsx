import { useState } from "react";
import { ScanFace, Fingerprint, Workflow } from "lucide-react";
import HikCentralIntegration from "@/pages/setup/it/HikCentralIntegration";
import ZKTecoIntegration from "@/pages/setup/it/ZKTecoIntegration";
import EtlAdmin from "@/pages/setup/it/EtlAdmin";

// HikCentral Integration and ETL Admin — moved here from Dashboard > IT
// (2026-08-19 user request). Both components moved as-is; this page just
// adds a small tab switcher between the two, since Setup > IT is a single
// flat nav entry (unlike Dashboard's per-module sidebar tree). ZKTeco
// Integration (Plant terminals) added 2026-08-28 alongside them.
const TABS = [
  { id: "hikcentral", icon: ScanFace,    label: "HikCentral Integration" },
  { id: "zkteco",     icon: Fingerprint, label: "ZKTeco Integration" },
  { id: "etl-admin",  icon: Workflow,    label: "ETL Admin" },
];

export default function ITSetupPage() {
  const [activeId, setActiveId] = useState("hikcentral");

  return (
    <div className="p-6 space-y-4">
      <div className="flex gap-2">
        {TABS.map(t => (
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
      {activeId === "hikcentral" && <HikCentralIntegration />}
      {activeId === "zkteco"     && <ZKTecoIntegration />}
      {activeId === "etl-admin"  && <EtlAdmin />}
    </div>
  );
}
