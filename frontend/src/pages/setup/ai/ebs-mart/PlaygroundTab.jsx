import { useState } from "react";
import { FlaskConical, Play, ShieldCheck, TerminalSquare } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Badge, Button, Card, ErrorBox, ResultTable, errMsg, inputCls } from "./shared";

const GROUPS = ["ebs-management", "ebs-finance", "ebs-purchasing", "ebs-warehouse", "ebs-production", "ebs-sales"];

// Argument form per intent tool — mirrors the request models in
// backend/app/routers/ebs_tools_app.py.
const TOOLS = {
  get_ap_aging: [
    ["supplier", "text"], ["min_days_overdue", "number"], ["currency", "text"],
    ["group_by", ["supplier", "bucket", "supplier_bucket"]],
  ],
  get_ap_open_invoices: [
    ["supplier", "text"], ["invoice_num", "text"], ["min_days_overdue", "number"],
    ["due_from", "date"], ["due_to", "date"], ["currency", "text"],
  ],
  get_ap_payments: [
    ["supplier", "text"], ["invoice_num", "text"], ["payment_number", "text"],
    ["date_from", "date"], ["date_to", "date"], ["group_by", ["none", "supplier", "month"]],
  ],
  get_ap_holds: [["supplier", "text"], ["hold_code", "text"]],
  get_expiring_lots: [
    ["days", "number", 90], ["item", "text"], ["subinventory_type", ["GOOD", "REJECT", "QUARANTINE", ""]],
    ["include_expired", ["false", "true"]], ["item_category", "text"],
  ],
  get_stock_onhand: [
    ["item", "text"], ["subinventory", "text"], ["lot_number", "text"],
    ["subinventory_type", ["", "GOOD", "REJECT", "QUARANTINE"]], ["group_by", ["item", "subinventory", "lot"]],
    ["item_category", "text"],
  ],
  get_stock_movement: [
    ["item", "text"], ["date_from", "date"], ["date_to", "date"], ["transaction_type", "text"],
    ["subinventory", "text"], ["group_by", ["type", "item", "day", "month"]],
  ],
  get_po_outstanding: [
    ["supplier", "text"], ["item", "text"], ["po_number", "text"], ["late_only", ["false", "true"]],
    ["group_by", ["none", "supplier"]],
  ],
  get_po_match_status: [
    ["po_number", "text"], ["supplier", "text"], ["item", "text"], ["status", "text"],
    ["group_by", ["none", "supplier", "status"]],
  ],
  get_pr_pending: [
    ["person", "text"], ["item", "text"], ["pr_number", "text"], ["min_days_waiting", "number"],
    ["group_by", ["none", "preparer"]],
  ],
  get_inventory_value: [
    ["item", "text"], ["item_category", "text"], ["subinventory_type", ["", "GOOD", "REJECT", "QUARANTINE"]],
    ["group_by", ["category", "item", "subinventory_type"]],
  ],
  get_ar_aging: [
    ["customer", "text"], ["min_days_overdue", "number"], ["currency", "text"],
    ["group_by", ["customer", "bucket", "customer_bucket"]],
  ],
  get_ar_open_invoices: [
    ["customer", "text"], ["invoice_num", "text"], ["min_days_overdue", "number"],
    ["due_from", "date"], ["due_to", "date"], ["currency", "text"],
  ],
  get_ar_receipts: [
    ["customer", "text"], ["receipt_number", "text"], ["date_from", "date"], ["date_to", "date"],
    ["application_status", ["", "APP", "UNAPP", "ACC", "UNID"]], ["include_reversed", ["false", "true"]],
    ["group_by", ["none", "customer", "month"]],
  ],
  get_so_backlog: [
    ["customer", "text"], ["item", "text"], ["order_number", "text"],
    ["business_type", ["", "Local", "Export", "CMO"]], ["late_only", ["false", "true"]],
    ["ordered_from", "date"], ["ordered_to", "date"], ["group_by", ["none", "customer", "item", "year"]],
  ],
  get_so_shipment_status: [["order_number", "text"], ["customer", "text"], ["item", "text"], ["status", "text"]],
  get_sales_by_customer: [
    ["customer", "text"], ["item", "text"], ["item_category", "text"], ["period", "text"],
    ["business_type", ["", "Local", "Export", "CMO", "Non-SO"]],
    ["group_by", ["customer", "item", "month", "customer_item", "business_type"]],
  ],
  find_marts: [["keywords", "text"]],
  get_data_freshness: [],
};

function GroupSelect({ value, onChange }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls} title="Jalankan sebagai grup ini">
      {GROUPS.map((g) => <option key={g} value={g}>sebagai {g}</option>)}
    </select>
  );
}

export default function PlaygroundTab() {
  const [sql, setSql] = useState("SELECT aging_bucket, COUNT(*) AS jml_invoice, SUM(amount_remaining_idr) AS total_idr\nFROM mart.ap_open_invoice\nGROUP BY aging_bucket, aging_bucket_order\nORDER BY aging_bucket_order");
  const [sqlGroup, setSqlGroup] = useState("ebs-management");
  const [sqlResult, setSqlResult] = useState(null);
  const [sqlErr, setSqlErr] = useState(null);
  const [sqlBusy, setSqlBusy] = useState(false);

  const [tool, setTool] = useState("get_ap_aging");
  const [args, setArgs] = useState({});
  const [toolGroup, setToolGroup] = useState("ebs-management");
  const [toolResult, setToolResult] = useState(null);
  const [toolErr, setToolErr] = useState(null);
  const [toolBusy, setToolBusy] = useState(false);

  const [sec, setSec] = useState(null);
  const [secBusy, setSecBusy] = useState(false);
  const [secErr, setSecErr] = useState(null);

  const runSql = async () => {
    setSqlBusy(true); setSqlErr(null); setSqlResult(null);
    try {
      setSqlResult((await ebsMartApi.runSql(sql, sqlGroup)).data);
    } catch (e) {
      setSqlErr(`${e?.response?.status || ""} ${errMsg(e)}`);
    } finally {
      setSqlBusy(false);
    }
  };

  const runTool = async () => {
    setToolBusy(true); setToolErr(null); setToolResult(null);
    // Text inputs left empty are omitted (tool default applies); a select set
    // to "(semua)" is sent as null, which is how a tool is told "no filter".
    const selects = new Set(TOOLS[tool].filter(([, t]) => Array.isArray(t)).map(([n]) => n));
    const clean = Object.fromEntries(Object.entries(args)
      .filter(([k, v]) => v !== "" || selects.has(k))
      .map(([k, v]) => [k, v === "" ? null : v === "true" ? true : v === "false" ? false : v]));
    try {
      setToolResult((await ebsMartApi.callTool(tool, clean, toolGroup)).data);
    } catch (e) {
      setToolErr(`${e?.response?.status || ""} ${errMsg(e)}`);
    } finally {
      setToolBusy(false);
    }
  };

  const runSec = async () => {
    setSecBusy(true); setSecErr(null);
    try {
      setSec((await ebsMartApi.securityTest()).data);
    } catch (e) {
      setSecErr(errMsg(e));
    } finally {
      setSecBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <Card title="Uji intent tool" icon={FlaskConical}
        subtitle="Panggil tool persis seperti Open WebUI memanggilnya, sebagai grup tertentu — untuk memastikan jawaban dan penolakan akses sebelum dipakai user.">
        <div className="p-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            <select value={tool} onChange={(e) => { setTool(e.target.value); setArgs({}); setToolResult(null); }} className={inputCls}>
              {Object.keys(TOOLS).map((t) => <option key={t}>{t}</option>)}
            </select>
            <GroupSelect value={toolGroup} onChange={setToolGroup} />
            <Button icon={Play} loading={toolBusy} onClick={runTool}>Jalankan</Button>
          </div>
          {TOOLS[tool].length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
              {TOOLS[tool].map(([name, type, def]) => (
                <label key={name} className="text-[10px] text-gray-500 space-y-1">
                  <span className="font-mono">{name}</span>
                  {Array.isArray(type) ? (
                    <select value={args[name] ?? type[0]} onChange={(e) => setArgs({ ...args, [name]: e.target.value })} className={`${inputCls} w-full`}>
                      {type.map((o) => <option key={o} value={o}>{o || "(semua)"}</option>)}
                    </select>
                  ) : (
                    <input type={type} placeholder={def != null ? String(def) : ""} value={args[name] ?? ""}
                      onChange={(e) => setArgs({ ...args, [name]: e.target.value })} className={`${inputCls} w-full`} />
                  )}
                </label>
              ))}
            </div>
          )}
          <ErrorBox>{toolErr}</ErrorBox>
          <ResultTable result={toolResult} />
        </div>
      </Card>

      <Card title="SQL playground (run_sql)" icon={TerminalSquare}
        subtitle="Guardrail yang sama dengan yang dipakai model: satu SELECT, hanya mart.*, read-only, timeout 15 detik, maksimal 500 baris. Tercatat di audit log.">
        <div className="p-4 space-y-3">
          <textarea rows={6} value={sql} onChange={(e) => setSql(e.target.value)} className={`${inputCls} w-full font-mono`} spellCheck={false} />
          <div className="flex gap-2">
            <GroupSelect value={sqlGroup} onChange={setSqlGroup} />
            <Button icon={Play} loading={sqlBusy} onClick={runSql}>Jalankan</Button>
          </div>
          <ErrorBox>{sqlErr}</ErrorBox>
          <ResultTable result={sqlResult} />
        </div>
      </Card>

      <Card title="Uji keamanan tool server" icon={ShieldCheck}
        subtitle="Checklist blueprint bagian 11: DML/DDL, multi-statement, tabel di luar mart, fungsi berbahaya, 403 lintas domain, timeout, audit. Target: 100% lulus."
        actions={<Button icon={Play} loading={secBusy} onClick={runSec}>Jalankan uji</Button>}>
        <div className="p-4 space-y-2">
          <ErrorBox>{secErr}</ErrorBox>
          {sec && (
            <>
              <p className="text-xs text-gray-300">
                <b className={sec.results.some((r) => r.passed === false) ? "text-red-400" : "text-emerald-400"}>
                  {sec.passed}/{sec.total} lulus
                </b>
              </p>
              <div className="divide-y divide-gray-800 rounded-lg border border-gray-800">
                {sec.results.map((r) => (
                  <div key={r.test} className="px-3 py-1.5 flex items-start gap-3 text-[11px]">
                    <Badge tone={r.passed === true ? "OK" : r.passed === false ? "FAILED" : "SKIPPED"}>
                      {r.passed === true ? "LULUS" : r.passed === false ? "GAGAL" : "N/A"}
                    </Badge>
                    <span className="text-gray-200 w-64 shrink-0">{r.test}</span>
                    <span className="text-gray-500">{String(r.detail)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
