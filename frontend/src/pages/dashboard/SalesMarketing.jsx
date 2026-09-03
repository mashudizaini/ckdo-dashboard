/**
 * Sales & Marketing Dashboard
 * ─────────────────────────────────────────
 * Placeholder — nav slot reserved 2026-09-03 while the actual module list
 * (Order Management-sourced sales trend, backlog, top customers/products,
 * fulfillment rate, price realization, etc.) is being scoped. No dedicated
 * Keycloak role exists yet for this team, so it's open to any authenticated
 * user like General, until one is set up.
 */
import { useNavigate, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { BarChart3 } from "lucide-react";

const SALES_TABS = ["overview"];

function Overview() {
  return (
    <div className="rounded-xl border border-dashed border-gray-800 bg-gray-900 px-8 py-16 text-center space-y-3">
      <BarChart3 size={32} className="mx-auto text-gray-700" />
      <p className="text-sm font-semibold text-gray-300">Modul sedang dirancang</p>
      <p className="text-xs text-gray-600 max-w-md mx-auto">
        Halaman ini akan berisi modul penjualan &amp; performa pasar dari data Oracle
        Order Management (sales trend, order backlog, top customer/produk, fulfillment
        rate, price realization, dsb). Daftar modul final akan ditambahkan setelah
        disepakati.
      </p>
    </div>
  );
}

export default function SalesMarketing() {
  const navigate = useNavigate();
  const location = useLocation();
  const activeSection = SALES_TABS.find((id) => location.pathname.endsWith(id)) ?? "overview";

  useEffect(() => {
    if (location.pathname === "/dashboard/sales" || location.pathname === "/dashboard/sales/") {
      navigate("/dashboard/sales/overview", { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="p-6 space-y-4">
      {activeSection === "overview" && <Overview />}
    </div>
  );
}
