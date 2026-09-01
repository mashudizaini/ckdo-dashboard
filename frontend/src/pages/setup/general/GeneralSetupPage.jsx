import { useState, useEffect } from "react";
import { ScanFace, Fingerprint, Workflow, ShieldCheck, Loader2 } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import HikCentralIntegration from "@/pages/setup/general/HikCentralIntegration";
import ZKTecoIntegration from "@/pages/setup/general/ZKTecoIntegration";
import EtlAdmin from "@/pages/setup/general/EtlAdmin";
import AccessControlPanel from "@/pages/setup/general/AccessControlPanel";

// HikCentral Integration, ZKTeco Integration and ETL Admin moved here from
// Setup > IT (2026-09-01) — none of the three are actually IT-department-
// only concerns (they're other departments' data pipelines IT happens to
// administer), so access is now per-user via the new Access Control tab
// instead of blanket it_staff role membership. Which of the first 3 tabs
// render is driven by GET /access-control/my-access, not by Keycloak role —
// a user could have zero, one, or all three granted independently.
const MODULE_TABS = [
  { id: "hikcentral", icon: ScanFace,    label: "HikCentral Integration", menuKey: "general.hikcentral" },
  { id: "zkteco",     icon: Fingerprint, label: "ZKTeco Integration",     menuKey: "general.zkteco" },
  { id: "etl-admin",  icon: Workflow,    label: "ETL Admin",              menuKey: "general.etl-admin" },
];

export default function GeneralSetupPage() {
  const { token } = useAuthStore();
  const hdrs = { Authorization: `Bearer ${token}` };
  const isIT = useAuthStore.getState().hasRole("it_staff");

  const [granted, setGranted] = useState(null); // Set<menuKey> | null while loading
  const [activeId, setActiveId] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/v1/dashboard/general/access-control/my-access", { headers: hdrs });
        const data = await res.json();
        setGranted(new Set(data.granted || []));
      } catch (_) {
        setGranted(new Set());
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleModuleTabs = granted ? MODULE_TABS.filter(t => granted.has(t.menuKey)) : [];
  const tabs = [
    ...visibleModuleTabs,
    ...(isIT ? [{ id: "access-control", icon: ShieldCheck, label: "Access Control" }] : []),
  ];

  useEffect(() => {
    if (!activeId && tabs.length) setActiveId(tabs[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [granted]);

  if (granted === null) {
    return <div className="p-6 flex justify-center py-16"><Loader2 size={22} className="animate-spin text-gray-600" /></div>;
  }

  if (tabs.length === 0) {
    return (
      <div className="p-6">
        <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900 px-8 py-16 text-center">
          <ShieldCheck size={28} className="text-gray-700 mx-auto mb-3" />
          <p className="text-sm text-gray-400 mb-1">No modules available</p>
          <p className="text-xs text-gray-600">You don't have access to any modules here yet — contact IT.</p>
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
      {activeId === "hikcentral"      && <HikCentralIntegration />}
      {activeId === "zkteco"          && <ZKTecoIntegration />}
      {activeId === "etl-admin"       && <EtlAdmin />}
      {activeId === "access-control"  && <AccessControlPanel />}
    </div>
  );
}
