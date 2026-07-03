import { useState, useCallback } from "react";
import {
  FileText, DollarSign, FileDown, RefreshCw,
  BarChart2, Package, Download, Search, Loader2, Layers,
} from "lucide-react";
import CoretaxDownloader from "./CoretaxDownloader";
import APAutoInvoice from "./APAutoInvoice";
import { accountingApi } from "@/api/dashboard";

const NEU = {
  bg:          "#e8edf5",
  shadowOut:   "6px 6px 14px #c5cad8, -6px -6px 14px #ffffff",
  shadowOutSm: "4px 4px 10px #c5cad8, -4px -4px 10px #ffffff",
  shadowIn:    "inset 3px 3px 8px #c5cad8, inset -3px -3px 8px #ffffff",
};

const TABS = [
  { id: "ap-invoice", icon: FileText,   label: "AP Autoinvoice",    color: "#2563eb" },
  { id: "cogs",       icon: BarChart2,  label: "COGS Report",       color: "#10b981" },
  { id: "profit",     icon: DollarSign, label: "Net Profit",        color: "#3b82f6" },
  { id: "ar",         icon: FileText,   label: "AR Balance",        color: "#f59e0b" },
  { id: "coretax",    icon: FileDown,   label: "Coretax Download",  color: "#8b5cf6" },
];

export default function AccountingDashboard() {
  const [active, setActive] = useState("ap-invoice");

  return (
    <div className="p-6 space-y-4">
      {/* Navigation Cards */}
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
      {active === "cogs"       && <COGSReport />}

      {active === "profit" && (
        <SectionCard title="Net Profit — Monthly Trend"
          action={<ActionBtn icon={RefreshCw} label="Refresh" onClick={() => {}} />}>
          <DataTable
            headers={["Month", "Revenue", "Expense", "Net Profit", "Margin"]}
            placeholder="Click Refresh to load data"
          />
        </SectionCard>
      )}

      {active === "ar" && (
        <SectionCard title="Accounts Receivable — Outstanding"
          action={<ActionBtn icon={RefreshCw} label="Refresh" onClick={() => {}} />}>
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

/* ─── COGS Report ─────────────────────────────────────────────────────────── */

const COGS_SUBTABS = [
  { id: "material-trx",  icon: Package, label: "Material Transaction"  },
  { id: "item-cost-cmp", icon: Layers,  label: "Item Cost Component"   },
];

function COGSReport() {
  const [subTab, setSubTab] = useState("material-trx");

  return (
    <div>
      {/* Sub-tab bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 16, borderBottom: "2px solid rgba(0,0,0,0.06)", paddingBottom: 0 }}>
        {COGS_SUBTABS.map(t => {
          const active = subTab === t.id;
          return (
            <button key={t.id} onClick={() => setSubTab(t.id)}
              style={{
                display: "flex", alignItems: "center", gap: 6,
                padding: "9px 18px", border: "none", cursor: "pointer",
                background: "transparent",
                borderBottom: active ? "2px solid #10b981" : "2px solid transparent",
                marginBottom: -2,
                color: active ? "#10b981" : "#64748b",
                fontSize: 13, fontWeight: active ? 700 : 500,
                transition: "all 0.15s",
              }}
            >
              <t.icon size={14} />
              {t.label}
            </button>
          );
        })}
      </div>

      {subTab === "material-trx"  && <MaterialTransactionPanel />}
      {subTab === "item-cost-cmp" && <ItemCostComponentPanel />}
    </div>
  );
}

/* ─── Item Cost Component Panel ──────────────────────────────────────────── */

const MONTHS_SHORT = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];

function monthInputToOPM(monthStr) {
  // "2025-01" → "JAN-2025"
  const [y, m] = (monthStr || "").split("-");
  if (!y || !m) return "";
  return `${MONTHS_SHORT[parseInt(m, 10) - 1]}-${y}`;
}

function currentMonthInput() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

const ICC_HEADERS = [
  { key: "segment1",           label: "Item",            mono: true,  minW: 110 },
  { key: "description",        label: "Description",     mono: false, minW: 200 },
  { key: "item_type",          label: "Item Type",       mono: false, minW: 80  },
  { key: "cost_type",          label: "Cost Type",       mono: false, minW: 100 },
  { key: "cost_cmpntcls_code", label: "Component Class", mono: true,  minW: 140 },
  { key: "cost_analysis_code", label: "Analysis Code",   mono: true,  minW: 110 },
  { key: "cmpnt_cost",         label: "Comp. Cost",      mono: true,  minW: 110 },
  { key: "total_cost",         label: "Total Cost",      mono: true,  minW: 110 },
  { key: "period_code",        label: "Period",          mono: true,  minW: 90  },
];

function exportICCCSV(rows, period) {
  if (!rows?.length) return;
  const hdrs = ICC_HEADERS.map(h => h.label);
  const lines = [
    "﻿" + hdrs.join(","),
    ...rows.map(r =>
      ICC_HEADERS.map(h => {
        const v = String(r[h.key] ?? "").replace(/"/g, '""');
        return `"${v}"`;
      }).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `item_cost_component_${period}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function ItemCostComponentPanel() {
  const [monthInput, setMonthInput] = useState(currentMonthInput());
  const [data,       setData]       = useState(null);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);

  const period = monthInputToOPM(monthInput);

  const loadData = useCallback(async () => {
    if (!period) return;
    setLoading(true);
    setError(null);
    try {
      const res = await accountingApi.getItemCostComponents(period);
      if (res.success) {
        setData(res);
      } else {
        setError(res.error || "Failed to load data");
        setData(null);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [period]);

  // Build per-item row grouping for alternating bg
  const itemColors = {};
  let colorIdx = 0;
  (data?.data || []).forEach(r => {
    if (!(r.segment1 in itemColors)) {
      itemColors[r.segment1] = colorIdx++ % 2 === 0 ? "#f0f3f9" : "#e8edf5";
    }
  });

  const INPUT = {
    padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12,
    background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b", outline: "none",
  };

  return (
    <SectionCard
      title="Item Cost Component"
      subtitle={`Oracle OPM · CM_CMPT_DTL · Org 121 · Cost Type 1000 (Actual)${period ? ` · ${period}` : ""}`}
      action={
        data?.data?.length > 0 && (
          <ActionBtn icon={Download} label="Export CSV" color="#10b981" onClick={() => exportICCCSV(data.data, period)} />
        )
      }
    >
      {/* Filter bar */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 12, marginBottom: 18 }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Period</p>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="month"
              value={monthInput}
              onChange={e => setMonthInput(e.target.value)}
              style={{ ...INPUT, width: 160 }}
            />
            <span style={{ fontSize: 13, fontWeight: 700, color: "#10b981", fontFamily: "monospace", minWidth: 90 }}>{period || "—"}</span>
          </div>
        </div>
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#10b981" onClick={loadData} disabled={loading || !period} />
      </div>

      {/* Error */}
      {error && (
        <div style={{ marginBottom: 14, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626" }}>
          {error}
        </div>
      )}

      {/* Row count */}
      {data && (
        <div style={{ marginBottom: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#10b981" }}>{data.count.toLocaleString()} rows</span>
          <span style={{ fontSize: 10.5, color: "#94a3b8", marginLeft: 8 }}>
            {Object.keys(itemColors).length} items · period {data.period}
          </span>
        </div>
      )}

      {/* Table */}
      <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: ICC_HEADERS.reduce((s, h) => s + h.minW, 0) }}>
            <thead>
              <tr style={{ background: "linear-gradient(135deg,#dfe5ed,#d8dee8)" }}>
                <th style={TH}>#</th>
                {ICC_HEADERS.map(h => <th key={h.key} style={{ ...TH, minWidth: h.minW }}>{h.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {!data ? (
                <tr>
                  <td colSpan={ICC_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    Select a period and click Load to query Oracle OPM cost data
                  </td>
                </tr>
              ) : data.data.length === 0 ? (
                <tr>
                  <td colSpan={ICC_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    No cost data found for period {data.period}
                  </td>
                </tr>
              ) : (
                data.data.map((row, i) => {
                  const isNum = ["cmpnt_cost", "total_cost"].includes;
                  const rowBg = itemColors[row.segment1] ?? "#f0f3f9";
                  return (
                    <tr key={i}
                      style={{ background: rowBg, transition: "background 0.1s" }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(16,185,129,0.07)"}
                      onMouseLeave={e => e.currentTarget.style.background = rowBg}
                    >
                      <td style={{ ...TD, color: "#94a3b8", fontFamily: "monospace", fontSize: 10 }}>{i + 1}</td>
                      {ICC_HEADERS.map(h => {
                        const v = row[h.key];
                        const numericCol = h.key === "cmpnt_cost" || h.key === "total_cost";
                        return (
                          <td key={h.key} style={{ ...TD, fontFamily: h.mono ? "monospace" : undefined, textAlign: numericCol ? "right" : "left", minWidth: h.minW }}>
                            {numericCol ? fmtNum(v) : (v ?? "-")}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </SectionCard>
  );
}

/* ─── Material Transaction Panel ─────────────────────────────────────────── */

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoStr(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}

const MTX_HEADERS = [
  { key: "trx_date",       label: "Date",           mono: false },
  { key: "trx_time",       label: "Time",           mono: true  },
  { key: "organization_code", label: "Org",         mono: false },
  { key: "item_number",    label: "Item",           mono: true  },
  { key: "item_description", label: "Description",  mono: false },
  { key: "trx_type",       label: "Type",           mono: false },
  { key: "quantity",       label: "Qty",            mono: true  },
  { key: "uom",            label: "UOM",            mono: true  },
  { key: "primary_qty",    label: "Prim Qty",       mono: true  },
  { key: "primary_uom",    label: "Prim UOM",       mono: true  },
  { key: "unit_cost",      label: "Unit Cost",      mono: true  },
  { key: "trx_value",      label: "Value",          mono: true  },
  { key: "subinventory",   label: "Subinventory",   mono: false },
  { key: "transfer_subinv", label: "Transfer Sub",  mono: false },
  { key: "lot_number",     label: "Lot",            mono: true  },
  { key: "reference",      label: "Reference",      mono: false },
  { key: "source_code",    label: "Source",         mono: false },
];

function fmtNum(v) {
  if (v === null || v === undefined || v === "-") return "-";
  const n = Number(v);
  if (isNaN(n)) return v;
  return n.toLocaleString("id-ID", { minimumFractionDigits: 0, maximumFractionDigits: 4 });
}

function exportCSV(rows) {
  if (!rows?.length) return;
  const headers = MTX_HEADERS.map(h => h.label);
  const lines = [
    "﻿" + headers.join(","),   // UTF-8 BOM for Excel
    ...rows.map(r =>
      MTX_HEADERS.map(h => {
        const v = r[h.key] ?? "";
        const s = String(v).replace(/"/g, '""');
        return `"${s}"`;
      }).join(",")
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `material_transactions_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function MaterialTransactionPanel() {
  const [dateFrom,    setDateFrom]    = useState(daysAgoStr(7));
  const [dateTo,      setDateTo]      = useState(todayStr());
  const [orgCode,     setOrgCode]     = useState("");
  const [itemNumber,  setItemNumber]  = useState("");
  const [trxType,     setTrxType]     = useState("");
  const [limit,       setLimit]       = useState(1000);
  const [data,        setData]        = useState(null);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = { date_from: dateFrom, date_to: dateTo, limit };
      if (orgCode.trim())    params.org_code    = orgCode.trim();
      if (itemNumber.trim()) params.item_number = itemNumber.trim();
      if (trxType.trim())    params.trx_type    = trxType.trim();
      const res = await accountingApi.getMaterialTransactions(params);
      if (res.success) {
        setData(res);
      } else {
        setError(res.error || "Failed to load data");
        setData(null);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, orgCode, itemNumber, trxType, limit]);

  const INPUT = {
    padding: "7px 11px", borderRadius: 9, border: "none", fontSize: 12,
    background: NEU.bg, boxShadow: NEU.shadowIn, color: "#1e293b",
    outline: "none", width: "100%",
  };

  return (
    <SectionCard
      title="Material Transactions"
      subtitle="Oracle EBS · MTL_MATERIAL_TRANSACTIONS"
      action={
        data?.data?.length > 0 && (
          <ActionBtn icon={Download} label="Export CSV" color="#10b981" onClick={() => exportCSV(data.data)} />
        )
      }
    >
      {/* Filter Bar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr 1fr auto auto", gap: 10, marginBottom: 18, alignItems: "end" }}>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Date From</p>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Date To</p>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Organization</p>
          <input placeholder="e.g. CKD" value={orgCode} onChange={e => setOrgCode(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Item Number</p>
          <input placeholder="partial search" value={itemNumber} onChange={e => setItemNumber(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Transaction Type</p>
          <input placeholder="partial search" value={trxType} onChange={e => setTrxType(e.target.value)} style={INPUT} />
        </div>
        <div>
          <p style={{ fontSize: 10, fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 5 }}>Max Rows</p>
          <select value={limit} onChange={e => setLimit(Number(e.target.value))} style={{ ...INPUT, width: 90 }}>
            {[500, 1000, 2000, 5000].map(n => <option key={n} value={n}>{n.toLocaleString()}</option>)}
          </select>
        </div>
        <ActionBtn icon={loading ? Loader2 : Search} label={loading ? "Loading…" : "Load"} color="#10b981" onClick={loadData} disabled={loading} />
      </div>

      {/* Error */}
      {error && (
        <div style={{ marginBottom: 16, padding: "10px 14px", borderRadius: 10, background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", fontSize: 12, color: "#dc2626" }}>
          {error}
        </div>
      )}

      {/* Row count */}
      {data && (
        <div style={{ marginBottom: 10, display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#10b981" }}>{data.count.toLocaleString()} rows</span>
          {data.count === data.limit && (
            <span style={{ fontSize: 10.5, color: "#f59e0b" }}>⚠ Limit reached — increase Max Rows or narrow date range</span>
          )}
        </div>
      )}

      {/* Table */}
      <div style={{ borderRadius: 14, overflow: "hidden", boxShadow: NEU.shadowIn }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 1600 }}>
            <thead>
              <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
                <th style={TH}>#</th>
                {MTX_HEADERS.map(h => <th key={h.key} style={TH}>{h.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {!data ? (
                <tr>
                  <td colSpan={MTX_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    Set the date range and click Load to query Oracle EBS material transactions
                  </td>
                </tr>
              ) : data.data.length === 0 ? (
                <tr>
                  <td colSpan={MTX_HEADERS.length + 1} style={{ padding: "40px 14px", textAlign: "center", fontSize: 12, color: "#94a3b8" }}>
                    No transactions found for the selected period
                  </td>
                </tr>
              ) : (
                data.data.map((row, i) => (
                  <tr key={row.transaction_id ?? i}
                    style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5", transition: "background 0.1s" }}
                    onMouseEnter={e => e.currentTarget.style.background = "rgba(16,185,129,0.05)"}
                    onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#f0f3f9" : "#e8edf5"}
                  >
                    <td style={{ ...TD, color: "#94a3b8", fontFamily: "monospace", fontSize: 10 }}>{i + 1}</td>
                    {MTX_HEADERS.map(h => {
                      const v = row[h.key];
                      const isNum = ["quantity", "primary_qty", "unit_cost", "trx_value"].includes(h.key);
                      return (
                        <td key={h.key} style={{ ...TD, fontFamily: h.mono ? "monospace" : undefined, textAlign: isNum ? "right" : "left", whiteSpace: h.key === "item_description" || h.key === "trx_type" ? "normal" : "nowrap" }}>
                          {isNum ? fmtNum(v) : (v ?? "-")}
                        </td>
                      );
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </SectionCard>
  );
}

/* ─── Shared components ───────────────────────────────────────────────────── */

const TH = {
  padding: "10px 12px", textAlign: "left", fontSize: 10, fontWeight: 700,
  color: "#374151", textTransform: "uppercase", letterSpacing: "0.06em",
  borderBottom: "2px solid rgba(0,0,0,0.06)", whiteSpace: "nowrap",
};
const TD = {
  padding: "8px 12px", fontSize: 12, color: "#334155",
};

function SectionCard({ title, subtitle, action, children }) {
  return (
    <div style={{ borderRadius: 20, background: NEU.bg, boxShadow: NEU.shadowOut }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "16px 20px", borderBottom: "1px solid rgba(0,0,0,0.06)",
      }}>
        <div>
          <h3 style={{ fontSize: 15, fontWeight: 700, color: "#1e293b", margin: 0 }}>{title}</h3>
          {subtitle && <p style={{ fontSize: 11, color: "#94a3b8", margin: "2px 0 0" }}>{subtitle}</p>}
        </div>
        {action}
      </div>
      <div style={{ padding: 20 }}>{children}</div>
    </div>
  );
}

function ActionBtn({ icon: Icon, label, color = "#2563eb", onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "flex", alignItems: "center", gap: 6,
        padding: "8px 16px", borderRadius: 10, border: "none",
        background: disabled ? "#94a3b8" : color,
        color: "#fff", fontSize: 12, fontWeight: 700,
        cursor: disabled ? "not-allowed" : "pointer",
        boxShadow: disabled ? "none" : NEU.shadowOutSm,
        whiteSpace: "nowrap",
      }}
    >
      <Icon size={13} className={disabled ? "animate-spin" : ""} />{label}
    </button>
  );
}

function DataTable({ headers, rows, placeholder }) {
  return (
    <div style={{ borderRadius: 16, overflow: "hidden", boxShadow: NEU.shadowIn }}>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ background: "linear-gradient(135deg, #dfe5ed, #d8dee8)" }}>
            {headers.map((h) => (
              <th key={h} style={TH}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows?.length ? (
            rows.map((row, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? "#f0f3f9" : "#e8edf5" }}>
                {row.map((cell, j) => (
                  <td key={j} style={{ ...TD, fontWeight: j === 0 ? 700 : 500 }}>{cell}</td>
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
