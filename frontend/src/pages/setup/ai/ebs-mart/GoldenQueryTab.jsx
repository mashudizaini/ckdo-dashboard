import { useEffect, useState } from "react";
import { BadgeCheck, Play, Plus, Save, Sparkles, Trash2, X } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Badge, Button, Card, ErrorBox, ResultTable, Spinner, errMsg, fmtDate, inputCls } from "./shared";

const EMPTY = { id: null, domain: "AP", question_id: "", sql_text: "" };

export default function GoldenQueryTab() {
  const [rows, setRows] = useState(null);
  const [form, setForm] = useState(null);
  const [result, setResult] = useState(null);
  const [runningId, setRunningId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const load = async () => {
    try {
      const r = await ebsMartApi.goldenList();
      setRows(r);
    } catch (e) {
      setError(errMsg(e));
    }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = { domain: form.domain, question_id: form.question_id, sql_text: form.sql_text };
      if (form.id) await ebsMartApi.goldenUpdate(form.id, body);
      else await ebsMartApi.goldenAdd(body);
      setForm(null);
      await load();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  const run = async (g) => {
    setRunningId(g.id);
    setError(null);
    setResult(null);
    try {
      const r = await ebsMartApi.runSql(g.sql_text, "ebs-management");
      setResult({ id: g.id, data: r });
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setRunningId(null);
    }
  };

  const verify = async (g) => {
    await ebsMartApi.goldenVerify(g.id);
    load();
  };

  const remove = async (g) => {
    if (!window.confirm(`Delete golden query "${g.question_id}"?`)) return;
    await ebsMartApi.goldenDelete(g.id);
    load();
  };

  if (!rows && !error) return <Spinner />;
  const verified = (rows || []).filter((r) => r.verified_at).length;

  return (
    <div className="space-y-4">
      <Card title="Golden queries (meta.golden_query)" icon={Sparkles}
        subtitle={`Tested question–SQL pairs; find_marts returns them to the model as examples. ${verified}/${rows?.length || 0} verified. Phase 1 target: 20–30 queries, matched against standard EBS reports.`}
        actions={<Button icon={Plus} onClick={() => setForm(EMPTY)}>Add</Button>}>
        <div className="p-4 space-y-3">
          <ErrorBox>{error}</ErrorBox>
          {form && (
            <div className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-3 space-y-2">
              <div className="flex gap-2">
                <select value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} className={inputCls}>
                  {["AP", "AR", "INV", "PO", "OM", "OPM", "GL"].map((d) => <option key={d}>{d}</option>)}
                </select>
                <input placeholder="Example question (in Indonesian, as users ask)" value={form.question_id}
                  onChange={(e) => setForm({ ...form, question_id: e.target.value })} className={`${inputCls} flex-1`} />
              </div>
              <textarea rows={5} placeholder="SELECT ... FROM mart...." value={form.sql_text}
                onChange={(e) => setForm({ ...form, sql_text: e.target.value })} className={`${inputCls} w-full font-mono`} />
              <p className="text-[11px] text-gray-500">The SQL is checked by the same guardrail as run_sql before saving. Changing the SQL clears the verified status.</p>
              <div className="flex gap-2">
                <Button icon={Save} loading={busy} onClick={save} disabled={!form.question_id || !form.sql_text}>Save</Button>
                <Button variant="ghost" icon={X} onClick={() => setForm(null)}>Cancel</Button>
              </div>
            </div>
          )}
          <div className="divide-y divide-gray-800 rounded-lg border border-gray-800">
            {(rows || []).map((g) => (
              <div key={g.id} className="px-3 py-2.5 space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge tone="SKIPPED">{g.domain}</Badge>
                      <p className="text-xs text-gray-200">{g.question_id}</p>
                    </div>
                    <p className="text-[11px] text-gray-500 mt-1">
                      {g.verified_at ? <span className="text-emerald-400">Verified {g.verified_by} · {g.verified_at}</span> : "Not verified"}
                      {" · "}created by {g.created_by} {fmtDate(g.created_at)}
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button variant="ghost" icon={Play} loading={runningId === g.id} onClick={() => run(g)}>Run</Button>
                    <Button variant="ghost" icon={BadgeCheck} onClick={() => verify(g)}
                      title="Mark as matched against the standard EBS report">Verify</Button>
                    <Button variant="ghost" onClick={() => setForm({ ...g })}>Edit</Button>
                    <Button variant="danger" icon={Trash2} onClick={() => remove(g)} />
                  </div>
                </div>
                <pre className="text-[11px] bg-gray-950 rounded p-2 text-gray-400 whitespace-pre-wrap">{g.sql_text}</pre>
                {result?.id === g.id && <ResultTable result={result.data} />}
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
