import { useState } from "react";
import { FileText, TrendingDown, DollarSign, FileDown, RefreshCw } from "lucide-react";
import CoretaxDownloader from "./CoretaxDownloader";
import APAutoInvoice from "./APAutoInvoice";

const NEU = {
  bg: "#e8edf5",
  shadowOut: "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn: "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
};

const TABS = [
  { id: "ap-invoice", icon: FileText,     label: "AP Autoinvoice",    color: "#2563eb" },
  { id: "expense",    icon: TrendingDown,  label: "Monthly Expense",  color: "#ef4444" },
  { id: "profit",     icon: DollarSign,    label: "Net Profit",       color: "#3b82f6" },
  { id: "ar",         icon: FileText,      label: "AR Balance",       color: "#f59e0b" },
  { id: "coretax",    icon: FileDown,      label: "Coretax Download", color: "#8b5cf6" },
];

export default function AccountingDashboard() {
  const [active, setActive] = useState("ap-invoice");

  return (
    <div className="p-6 space-y-4">
      {/* Navigation Cards — convex neumorphic */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        {TABS.map((tab) => {
          const isActive = active === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActive(tab.id)}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "14px 16px", borderRadius: 16, border: "none",
                background: NEU.bg, cursor: "pointer",
                boxShadow: isActive ? NEU.shadowIn : NEU.shadowOut,
                transform: isActive ? "scale(0.98)" : "scale(1)",
                transition: "all 0.2s ease",
              }}
            >
              <div style={{
                width: 36, height: 36, borderRadius: 10,
                background: isActive ? tab.color : NEU.bg,
                boxShadow: isActive ? "none" : NEU.shadowOutSm,
                display: "flex", alignItems: "center", justifyContent: "center",
                transition: "all 0.2s ease",
              }}>
                <tab.icon size={16} style={{ color: isActive ? "#fff" : tab.color }} />
              </div>
              <span style={{
                fontSize: 13, fontWeight: 700, letterSpacing: "0.01em",
                color: isActive ? tab.color : "#475569",
                transition: "color 0.2s ease",
              }}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Content */}
      {active === "ap-invoice" && <APAutoInvoice />}

      {active === "expense" && (
        <SectionCard title="Expense Detail"
          action={<ActionBtn icon={RefreshCw} label="Refresh" />}>
          <DataTable
            headers={["Category", "Budget", "Actual", "Variance"]}
            placeholder="Click Refresh to load expense data"
          />
        </SectionCard>
      )}

      {active === "profit" && (
        <SectionCard title="Net Profit — Monthly Trend"
          action={<ActionBtn icon={RefreshCw} label="Refresh" />}>
          <div style={{
            height: 160, borderRadius: 14, marginBottom: 16,
            background: NEU.bg, boxShadow: NEU.shadowIn,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <span style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>Chart net profit trend</span>
          </div>
          <DataTable
            headers={["Month", "Revenue", "Expense", "Net Profit", "Margin"]}
            placeholder="Click Refresh to load data"
          />
        </SectionCard>
      )}

      {active === "ar" && (
        <SectionCard title="Accounts Receivable — Outstanding"
          action={<ActionBtn icon={RefreshCw} label="Refresh" />}>
          <DataTable
            headers={["Customer", "Invoice No", "Invoice Date", "Due Date", "Amount", "Status"]}
            placeholder="Click Refresh to load AR data"
          />
        </SectionCard>
      )}

      {active === "coretax" && <CoretaxDownloader />}
    </div>
  );
}

function SectionCard({ title, action, children }) {
  return (
    <div style={{ borderRadius: 20, background: NEU.bg, boxShadow: NEU.shadowOut }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)",
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", margin: 0 }}>{title}</h3>
        {action}
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label }) {
  return (
    <button style={{
      display: "flex", alignItems: "center", gap: 6,
      padding: "8px 16px", borderRadius: 10, border: "none",
      background: "#2563eb", color: "#fff", fontSize: 12, fontWeight: 700,
      cursor: "pointer", boxShadow: NEU.shadowOutSm,
    }}>
      <Icon size={13} />{label}
    </button>
  );
}

const badgeClass = {
  success: { bg: "#d1fae5", color: "#059669" },
  danger:  { bg: "#fee2e2", color: "#dc2626" },
  warning: { bg: "#fef3c7", color: "#d97706" },
};

function DataTable({ headers, rows, placeholder }) {
  return (
    <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
            {headers.map((h) => (
              <th key={h} style={{
                padding: "12px 14px", textAlign: "left", fontSize: 11, fontWeight: 700,
                color: "#374151", textTransform: "uppercase", letterSpacing: "0.06em",
                borderBottom: "2px solid rgba(0,0,0,0.06)", whiteSpace: "nowrap",
              }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows?.length ? (
            rows.map((row, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                {row.map((cell, j) => (
                  <td key={j} style={{
                    padding: "10px 14px", fontSize: 13, color: j === 0 ? "#1e293b" : "#475569",
                    fontWeight: j === 0 ? 700 : 500,
                  }}>
                    {cell?.badge ? (
                      <span style={{
                        padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                        background: badgeClass[cell.badge]?.bg, color: badgeClass[cell.badge]?.color,
                      }}>
                        {cell.text}
                      </span>
                    ) : cell}
                  </td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={headers.length} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                {placeholder || "No data"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
