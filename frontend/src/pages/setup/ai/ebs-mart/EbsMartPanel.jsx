import { useState } from "react";
import { BookText, Bot, FlaskConical, LayoutDashboard, ScrollText, Sparkles, Warehouse } from "lucide-react";
import OverviewTab from "./OverviewTab";
import CatalogTab from "./CatalogTab";
import GoldenQueryTab from "./GoldenQueryTab";
import PlaygroundTab from "./PlaygroundTab";
import AuditTab from "./AuditTab";
import SubinventoryTab from "./SubinventoryTab";
import KitTab from "./KitTab";

// EBS Data Mart — the dashboard side of "Blueprint AI Chat Oracle EBS – Open
// WebUI": the mart the chat reads, the ETL that fills it, the catalog and
// golden queries that steer the model, the audit trail, and the Open WebUI
// configuration to paste in. Backend: app/services/ebs_mart,
// app/routers/ai_tools/ebs_mart_admin.py, app/routers/ebs_tools_app.py.
const TABS = [
  { id: "overview",   icon: LayoutDashboard, label: "Ringkasan",     Comp: OverviewTab },
  { id: "catalog",    icon: BookText,        label: "Katalog kolom", Comp: CatalogTab },
  { id: "golden",     icon: Sparkles,        label: "Golden query",  Comp: GoldenQueryTab },
  { id: "playground", icon: FlaskConical,    label: "Uji & keamanan", Comp: PlaygroundTab },
  { id: "audit",      icon: ScrollText,      label: "Audit log",     Comp: AuditTab },
  { id: "subinv",     icon: Warehouse,       label: "Subinventory",  Comp: SubinventoryTab },
  { id: "kit",        icon: Bot,             label: "Open WebUI kit", Comp: KitTab },
];

export default function EbsMartPanel() {
  const [active, setActive] = useState("overview");
  const Comp = TABS.find((t) => t.id === active).Comp;
  return (
    <div className="space-y-4">
      <div className="flex gap-1 flex-wrap border-b border-gray-800">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setActive(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              active === t.id ? "border-blue-500 text-blue-300" : "border-transparent text-gray-500 hover:text-gray-300"
            }`}>
            <t.icon size={13} /> {t.label}
          </button>
        ))}
      </div>
      <Comp />
    </div>
  );
}
