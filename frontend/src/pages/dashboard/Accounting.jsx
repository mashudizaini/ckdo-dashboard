import { useState } from "react";
import { TrendingUp, TrendingDown, DollarSign, FileText, RefreshCw, FileDown } from "lucide-react";
import CoretaxDownloader from "./CoretaxDownloader";

export default function AccountingDashboard() {
  const [activeSection, setActiveSection] = useState("revenue");

  const kpiCards = [
    { id: "revenue", icon: TrendingUp,   color: "text-green-400",  bg: "bg-green-500/10",  activeBorder: "border-green-500/40",  label: "Reporting (Revenue)", value: "—" },
    { id: "expense", icon: TrendingDown, color: "text-red-400",    bg: "bg-red-500/10",    activeBorder: "border-red-500/40",    label: "Expense Bulanan",     value: "—" },
    { id: "profit",  icon: DollarSign,   color: "text-blue-400",   bg: "bg-blue-500/10",   activeBorder: "border-blue-500/40",   label: "Net Profit",          value: "—" },
    { id: "ar",      icon: FileText,     color: "text-yellow-400",  bg: "bg-yellow-500/10",  activeBorder: "border-yellow-500/40",  label: "AR Balance",          value: "—" },
    { id: "coretax", icon: FileDown,     color: "text-purple-400",  bg: "bg-purple-500/10",  activeBorder: "border-purple-500/40",  label: "Coretax Download",    value: "—" },
  ];

  return (
    <div className="p-6 space-y-4">
      {/* Tab Buttons */}
      <div className="grid grid-cols-2 xl:grid-cols-5 gap-2">
        {kpiCards.map((c) => (
          <button
            key={c.id}
            onClick={() => setActiveSection(activeSection === c.id ? null : c.id)}
            className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-all ${
              activeSection === c.id
                ? `${c.bg} ${c.activeBorder} ring-1 ring-inset ${c.activeBorder}`
                : "bg-gray-900 border-gray-800 hover:border-gray-700 hover:bg-gray-800/60"
            }`}
          >
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${c.bg} border ${c.activeBorder}`}>
              <c.icon size={15} className={c.color} />
            </div>
            <span className={`text-sm font-medium truncate ${activeSection === c.id ? "text-white" : "text-gray-400"}`}>
              {c.label}
            </span>
          </button>
        ))}
      </div>

      {/* Section: Revenue */}
      {activeSection === "revenue" && (
        <SectionCard title="Revenue Detail"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <DataTable
            headers={["Category", "Budget", "Actual", "Variance"]}
            rows={[
              ["Product Sales",   "Rp 40.0 M", "Rp 43.2 M", { text: "+8.0%",  badge: "success" }],
              ["Service Revenue", "Rp 5.0 M",  "Rp 5.3 M",  { text: "+6.0%",  badge: "success" }],
              ["Other Income",    "Rp 2.0 M",  "Rp 1.8 M",  { text: "-10.0%", badge: "danger"  }],
            ]}
          />
        </SectionCard>
      )}

      {/* Section: Expense */}
      {activeSection === "expense" && (
        <SectionCard title="Expense Detail"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <DataTable
            headers={["Category", "Budget", "Actual", "Variance"]}
            placeholder="Klik Refresh untuk memuat data expense"
          />
        </SectionCard>
      )}

      {/* Section: Profit */}
      {activeSection === "profit" && (
        <SectionCard title="Net Profit — Trend Bulanan"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <div className="h-40 rounded-lg bg-gray-800 border border-gray-700 flex items-center justify-center mb-4">
            <span className="text-xs text-gray-600">Chart net profit trend</span>
          </div>
          <DataTable
            headers={["Bulan", "Revenue", "Expense", "Net Profit", "Margin"]}
            placeholder="Klik Refresh untuk memuat data"
          />
        </SectionCard>
      )}

      {/* Section: AR */}
      {activeSection === "ar" && (
        <SectionCard title="Accounts Receivable — Outstanding"
          action={<ActionBtn icon={RefreshCw} label="Refresh" color="bg-blue-600 hover:bg-blue-700" />}>
          <DataTable
            headers={["Customer", "Invoice No", "Invoice Date", "Due Date", "Amount", "Status"]}
            placeholder="Klik Refresh untuk memuat data AR"
          />
        </SectionCard>
      )}

      {/* Section: Coretax */}
      {activeSection === "coretax" && <CoretaxDownloader />}
    </div>
  );
}

function SectionCard({ title, action, children }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900">
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color }) {
  return (
    <button className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors ${color}`}>
      <Icon size={13} />{label}
    </button>
  );
}

const badgeClass = {
  success: "bg-green-500/20 text-green-400",
  danger:  "bg-red-500/20 text-red-400",
  warning: "bg-yellow-500/20 text-yellow-400",
  info:    "bg-blue-500/20 text-blue-400",
};

function DataTable({ headers, rows, placeholder }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-800">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-gray-800/60">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {rows?.length ? (
            rows.map((row, i) => (
              <tr key={i} className="hover:bg-gray-800/40 transition-colors">
                {row.map((cell, j) => (
                  <td key={j} className={`px-3 py-3 ${j === 0 ? "font-medium text-gray-200" : "text-gray-300"}`}>
                    {cell?.badge ? (
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass[cell.badge] || ""}`}>
                        {cell.text}
                      </span>
                    ) : cell}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={headers.length} className="px-3 py-10 text-center text-xs text-gray-600">
                {placeholder || "Tidak ada data"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
