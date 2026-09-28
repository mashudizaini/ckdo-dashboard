import { useState } from "react";
import { FlaskConical, Play, ShieldCheck, TerminalSquare } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Badge, Button, Card, ErrorBox, ResultTable, errMsg, inputCls } from "./shared";

const GROUPS = ["ebs-management", "ebs-finance", "ebs-purchasing", "ebs-warehouse", "ebs-production", "ebs-sales"];

// Argument form per intent tool — mirrors the request models in
// backend/app/routers/ebs_tools_app.py.
const TOOLS = {
  ap_get_aging: [
    ["supplier", "text"], ["min_days_overdue", "number"], ["currency", "text"],
    ["group_by", ["supplier", "bucket", "supplier_bucket"]],
  ],
  ap_get_open_invoices: [
    ["supplier", "text"], ["invoice_num", "text"], ["min_days_overdue", "number"],
    ["due_from", "date"], ["due_to", "date"], ["currency", "text"],
  ],
  ap_get_payments: [
    ["supplier", "text"], ["invoice_num", "text"], ["payment_number", "text"],
    ["date_from", "date"], ["date_to", "date"], ["group_by", ["none", "supplier", "month"]],
  ],
  ap_get_holds: [["supplier", "text"], ["hold_code", "text"]],
  inv_get_expiring_lots: [
    ["days", "number", 90], ["item", "text"], ["subinventory_type", ["GOOD", "REJECT", "QUARANTINE", ""]],
    ["include_expired", ["false", "true"]], ["item_category", "text"],
  ],
  inv_get_onhand: [
    ["item", "text"], ["subinventory", "text"], ["lot_number", "text"],
    ["subinventory_type", ["", "GOOD", "REJECT", "QUARANTINE"]], ["group_by", ["item", "subinventory", "lot"]],
    ["item_category", "text"],
  ],
  inv_get_movements: [
    ["item", "text"], ["date_from", "date"], ["date_to", "date"], ["transaction_type", "text"],
    ["subinventory", "text"], ["group_by", ["type", "item", "day", "month"]],
  ],
  po_get_outstanding: [
    ["supplier", "text"], ["item", "text"], ["po_number", "text"], ["late_only", ["false", "true"]],
    ["group_by", ["none", "supplier"]],
  ],
  po_get_match_status: [
    ["po_number", "text"], ["supplier", "text"], ["item", "text"], ["status", "text"],
    ["group_by", ["none", "supplier", "status"]],
  ],
  pr_get_pending: [
    ["person", "text"], ["item", "text"], ["pr_number", "text"], ["min_days_waiting", "number"],
    ["group_by", ["none", "preparer"]],
  ],
  inv_get_valuation: [
    ["item", "text"], ["item_category", "text"], ["subinventory_type", ["", "GOOD", "REJECT", "QUARANTINE"]],
    ["group_by", ["category", "item", "subinventory_type"]],
  ],
  ar_get_aging: [
    ["customer", "text"], ["min_days_overdue", "number"], ["currency", "text"],
    ["group_by", ["customer", "bucket", "customer_bucket"]],
  ],
  ar_get_open_invoices: [
    ["customer", "text"], ["invoice_num", "text"], ["min_days_overdue", "number"],
    ["due_from", "date"], ["due_to", "date"], ["currency", "text"],
  ],
  ar_get_receipts: [
    ["customer", "text"], ["receipt_number", "text"], ["date_from", "date"], ["date_to", "date"],
    ["application_status", ["", "APP", "UNAPP", "ACC", "UNID"]], ["include_reversed", ["false", "true"]],
    ["group_by", ["none", "customer", "month"]],
  ],
  so_get_backlog: [
    ["customer", "text"], ["item", "text"], ["order_number", "text"],
    ["business_type", ["", "Local", "Export", "CMO"]], ["late_only", ["false", "true"]],
    ["ordered_from", "date"], ["ordered_to", "date"], ["group_by", ["none", "customer", "item", "year"]],
  ],
  so_get_shipment_status: [["order_number", "text"], ["customer", "text"], ["item", "text"], ["status", "text"]],
  sales_get_summary: [
    ["customer", "text"], ["item", "text"], ["item_category", "text"], ["period", "text"],
    ["business_type", ["", "Local", "Export", "CMO", "Non-SO"]],
    ["group_by", ["customer", "item", "month", "customer_item", "business_type"]],
  ],
  opm_get_batch: [
    ["batch_no", "text"], ["product", "text"], ["status", ["", "Pending", "WIP", "Completed", "Closed", "Cancelled"]],
    ["date_from", "date"], ["date_to", "date"], ["late_only", ["false", "true"]],
    ["group_by", ["none", "status", "schedule", "product", "month"]],
  ],
  opm_get_yield: [
    ["product", "text"], ["batch_no", "text"], ["date_from", "date"], ["date_to", "date"], ["below_pct", "number"],
    ["group_by", ["product", "batch", "month"]],
  ],
  opm_get_material_usage: [
    ["batch_no", "text"], ["ingredient", "text"], ["lot_number", "text"], ["over_pct", "number"],
    ["group_by", ["none", "ingredient"]],
  ],
  gl_get_pl: [
    ["period", "text"], ["ytd", ["false", "true"]], ["department", "text"],
    ["compare_prior_year", ["false", "true"]], ["level", ["line", "section"]],
  ],
  gl_get_trial_balance: [
    ["period", "text"], ["account", "text"], ["department", "text"], ["statement", ["", "BS", "PL"]],
    ["group_by", ["account", "fs_line", "department"]],
  ],
  gl_get_journals: [
    ["period", "text"], ["date_from", "date"], ["date_to", "date"], ["account", "text"], ["department", "text"],
    ["source", "text"], ["category", "text"], ["text", "text"], ["subledger_txn", "text"], ["min_amount", "number"],
    ["group_by", ["none", "source", "account"]],
  ],
  gl_get_period_status: [["period", "text"], ["application", ["", "GL", "AP", "AR", "PO", "INV", "OPM", "FA"]]],
  gl_get_subledger_gap: [["period", "text"], ["application", "text"], ["group_by", ["summary", "detail"]]],
  po_get_uninvoiced_receipts: [["as_of_period", "text"], ["supplier", "text"], ["group_by", ["supplier", "po"]]],
  so_get_shipped_not_invoiced: [["date_from", "date"], ["customer", "text"]],
  ar_get_unapplied_receipts: [["customer", "text"]],
  ar_get_autoinvoice_errors: [["date_from", "date"], ["so_number", "text"], ["group_by", ["none", "error"]]],
  opm_get_open_batches: [["status", ["", "Pending", "WIP", "Completed"]], ["days_open", "number"]],
  ce_get_unreconciled: [["bank_account_name", "text"], ["date_to", "date"], ["side", ["", "BANK", "SYSTEM"]],
    ["group_by", ["summary", "detail"]]],
  fa_get_assets: [["category", "text"], ["location", "text"], ["asset", "text"],
    ["status", ["", "Aktif", "CIP", "Retired", "Fully reserved"]], ["group_by", ["category", "location", "status", "asset"]]],
  fa_get_depreciation: [["period", "text"], ["category", "text"], ["group_by", ["category", "asset"]]],
  lookup_master: [["text", "text"], ["type", ["", "item", "supplier", "customer", "account", "department"]]],
  po_get_document: [["po_number", "text"]],
  po_get_pending_approval: [["min_days", "number"], ["doc_type", ["", "PO", "PR"]], ["approver", "text"]],
  ap_get_invoice: [["invoice_num", "text"], ["supplier", "text"]],
  ap_get_due_forecast: [["weeks_ahead", "number"], ["supplier", "text"]],
  ap_get_withholding: [["period", "text"], ["tax_code", "text"], ["supplier", "text"], ["group_by", ["tax", "supplier", "invoice"]]],
  so_get_order: [["order_number", "text"]],
  so_get_holds: [["hold_name", "text"], ["customer", "text"]],
  ar_get_customer_balance: [["customer", "text"]],
  inv_get_stock_card: [["item", "text"], ["period", "text"], ["subinventory", "text"]],
  inv_get_slow_moving: [["days_no_movement", "number"], ["subinventory_type", ["GOOD", "", "REJECT", "QUARANTINE"]]],
  opm_get_item_cost: [["item", "text"], ["period", "text"]],
  gl_get_account_movement: [["account", "text"], ["period_from", "text"], ["period_to", "text"], ["department", "text"]],
  gl_get_budget_vs_actual: [["period", "text"], ["ytd", ["false", "true"]], ["department", "text"], ["account", "text"],
    ["budget_name", "text"], ["include_revenue", ["false", "true"]], ["group_by", ["department", "account", "section", "month"]]],
  it_get_interface_errors: [["interface", ["", "AP", "AR", "GL", "INV", "RCV"]], ["status", ["", "ERROR", "PENDING"]],
    ["days", "number"], ["group_by", ["summary", "detail"]]],
  find_marts: [["keywords", "text"]],
  get_data_freshness: [["domain", "text"]],
  // System Administration — dijalankan sebagai email Anda sendiri; hanya
  // email di SYSADMIN_ALLOWLIST yang lolos, grup yang dipilih tidak berpengaruh.
  sa_get_user: [["user", "text"]],
  sa_get_user_resps: [["user", "text"], ["include_inactive", ["false", "true"]]],
  sa_who_has_resp: [["responsibility", "text"], ["include_inactive", ["false", "true"]]],
  sa_who_has_function: [["function", "text"], ["include_seeded", ["false", "true"]]],
  sa_get_resp_functions: [["responsibility", "text"], ["function", "text"], ["function_type", "text"]],
  sa_get_resp_programs: [["responsibility", "text"], ["program", "text"]],
  sa_get_dormant_users: [["days", "number"], ["exclude_seeded", ["true", "false"]]],
  sa_get_terminated_active_users: [],
  sa_get_sod_violations: [["rule_name", "text"], ["user", "text"], ["include_seeded", ["false", "true"]]],
  sa_get_profile_value: [["profile", "text"], ["level", "text"], ["value_owner", "text"]],
  sa_get_login_history: [["user", "text"], ["days", "number"]],
  sa_get_manager_status: [["only_problems", ["false", "true"]]],
  sa_get_pending_approvals: [["approver", "text"], ["days", "number"], ["item_type", "text"],
    ["include_fyi", ["false", "true"]], ["include_errors", ["false", "true"]], ["group_by", ["none", "recipient", "item_type"]]],
  sa_check_patch: [["patch_number", "text"]],
  sa_get_form_personalizations: [["form", "text"]],
  it_get_concurrent_requests: [["hours", "number"], ["status", "text"], ["phase", "text"], ["program", "text"],
    ["user", "text"], ["group_by", ["none", "program", "status"]]],
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

  const [tool, setTool] = useState("ap_get_aging");
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
      setSqlResult(await ebsMartApi.runSql(sql, sqlGroup));
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
      setToolResult(await ebsMartApi.callTool(tool, clean, toolGroup));
    } catch (e) {
      setToolErr(`${e?.response?.status || ""} ${errMsg(e)}`);
    } finally {
      setToolBusy(false);
    }
  };

  const runSec = async () => {
    setSecBusy(true); setSecErr(null);
    try {
      setSec(await ebsMartApi.securityTest());
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
