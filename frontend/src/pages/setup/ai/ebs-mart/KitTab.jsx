import { useEffect, useState } from "react";
import { Bot, ExternalLink, FileCode2, ListChecks, MessageSquareText, Wrench } from "lucide-react";
import { ebsMartApi } from "@/api/dashboard";
import { Card, CopyButton, ErrorBox, Spinner, errMsg } from "./shared";

function CodeBlock({ title, text, lang }) {
  return (
    <div className="rounded-lg border border-gray-800">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-gray-800 bg-gray-800/40">
        <span className="text-[11px] font-mono text-gray-300">{title}{lang ? ` · ${lang}` : ""}</span>
        <CopyButton text={text} />
      </div>
      <pre className="p-3 text-[11px] text-gray-300 whitespace-pre-wrap max-h-80 overflow-auto">{text}</pre>
    </div>
  );
}

export default function KitTab() {
  const [kit, setKit] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    ebsMartApi.kit().then((r) => setKit(r.data)).catch((e) => setError(errMsg(e)));
  }, []);

  if (!kit && !error) return <Spinner />;
  if (!kit) return <ErrorBox>{error}</ErrorBox>;

  const origin = window.location.origin;
  const ts = { ...kit.tool_server, url: origin + kit.tool_server.url, docs: origin + kit.tool_server.docs };
  const steps = [
    <>Admin Panel → Settings → <b>Tools</b> (Connections) → tambah tool server OpenAPI: URL <code className="text-blue-300">{ts.url}</code>, path <code className="text-blue-300">{ts.openapi}</code>.</>,
    <>Autentikasi: <b>OAuth/Session</b> (meneruskan token Keycloak user — disarankan), atau <b>Bearer</b> dengan <code>EBS_TOOLS_SERVICE_KEY</code> + env <code>ENABLE_FORWARD_USER_INFO_HEADERS=true</code> di Open WebUI supaya email user ikut terkirim.</>,
    <>Workspace → <b>Models</b> → buat “{kit.model_settings.name}”: function calling <b>{kit.model_settings.function_calling}</b>, temperature {kit.model_settings.temperature}, context ≥ {kit.model_settings.context_length_min.toLocaleString("id-ID")}, Memory & Web Search nonaktif, akses {kit.model_settings.access}. Tempel system prompt di bawah.</>,
    <>Workspace → <b>Skills</b>: buat satu skill per blok di bawah (ebs-ap, ebs-inventory-lot) dan pasang ke model.</>,
    <>Workspace → <b>Prompts</b>: buat template / di bawah.</>,
    <>Admin → <b>Functions</b>: tambah Filter <i>EBS Context</i> dan Action <i>Export Excel</i> (isi valve service_key), aktifkan untuk model EBS Analyst saja.</>,
    <>Beri user grup <code>ebs-*</code> di tab <b>EBS Chat Access</b> (atau grup Keycloak dengan nama yang sama), lalu jalankan uji keamanan dan test set 50 pertanyaan (target ≥ 90% benar).</>,
  ];

  return (
    <div className="space-y-4">
      <Card title="Langkah pemasangan di Open WebUI (CoChat)" icon={ListChecks}
        subtitle="Blueprint bagian 8. Semua isi di halaman ini dibaca langsung dari repo dashboard, jadi selalu sama dengan yang di-deploy.">
        <ol className="p-4 space-y-2 text-xs text-gray-300 list-decimal list-inside">
          {steps.map((s, i) => <li key={i} className="leading-relaxed">{s}</li>)}
        </ol>
        <div className="px-4 pb-4 flex flex-wrap gap-2">
          <CopyButton text={ts.url} label="Salin URL tool server" />
          <a href={ts.docs} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs font-semibold text-gray-300 hover:border-gray-600">
            <ExternalLink size={13} /> Swagger tool server
          </a>
        </div>
      </Card>

      <Card title="System prompt — EBS Analyst" icon={Bot}>
        <div className="p-4"><CodeBlock title="system_prompt.md" text={kit.system_prompt} /></div>
      </Card>

      <Card title="Skills domain" icon={Wrench} subtitle="Dimuat model secara lazy saat relevan (butuh Native function calling).">
        <div className="p-4 space-y-3">
          {kit.skills.map((s) => <CodeBlock key={s.name} title={s.name} lang="markdown" text={s.content} />)}
        </div>
      </Card>

      <Card title="Prompt template (/)" icon={MessageSquareText} subtitle="Untuk user non-teknis — pertanyaan rutin tanpa perlu merangkai kalimat.">
        <div className="divide-y divide-gray-800">
          {kit.prompts.map((p) => (
            <div key={p.command} className="px-4 py-2.5 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-mono text-blue-300">{p.command} <span className="text-gray-500 font-sans">— {p.title}</span></p>
                <p className="text-[11px] text-gray-400 mt-0.5">{p.content}</p>
              </div>
              <CopyButton text={p.content} />
            </div>
          ))}
        </div>
      </Card>

      <Card title="Functions" icon={FileCode2}
        subtitle="Tools/Functions in-process menjalankan Python di server Open WebUI — izin membuatnya setara akses shell. Batasi hanya admin.">
        <div className="p-4 space-y-3">
          <CodeBlock title="Filter: EBS Context" lang="python" text={kit.filter} />
          <CodeBlock title="Action: Export Excel" lang="python" text={kit.action} />
        </div>
      </Card>
    </div>
  );
}
