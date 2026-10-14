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
    ebsMartApi.kit().then((r) => setKit(r)).catch((e) => setError(errMsg(e)));
  }, []);

  if (!kit && !error) return <Spinner />;
  if (!kit) return <ErrorBox>{error}</ErrorBox>;

  const origin = window.location.origin;
  const ts = { ...kit.tool_server, url: origin + kit.tool_server.url, docs: origin + kit.tool_server.docs };
  const steps = [
    <>Admin Panel → Settings → <b>Tools</b> (Connections) → add an OpenAPI tool server: URL <code className="text-blue-300">{ts.url}</code>, path <code className="text-blue-300">{ts.openapi}</code>.</>,
    <>Authentication: <b>OAuth/Session</b> (forwards the user's Keycloak token — recommended), or <b>Bearer</b> with <code>EBS_TOOLS_SERVICE_KEY</code> + env <code>ENABLE_FORWARD_USER_INFO_HEADERS=true</code> in Open WebUI so the user's email is sent along.</>,
    <>Workspace → <b>Models</b> → create “{kit.model_settings.name}”: function calling <b>{kit.model_settings.function_calling}</b>, temperature {kit.model_settings.temperature}, context ≥ {kit.model_settings.context_length_min.toLocaleString("en-US")}, Memory & Web Search off, access {kit.model_settings.access}. Paste the system prompt below.</>,
    <>Workspace → <b>Skills</b>: create one skill per block below (ebs-ap, ebs-inventory-lot) and attach them to the model.</>,
    <>Workspace → <b>Prompts</b>: create the / templates below.</>,
    <>Admin → <b>Functions</b>: add the <i>EBS Context</i> Filter and the <i>Export Excel</i> Action (fill in the service_key valve), enabled for the EBS Analyst model only.</>,
    <>Give users an <code>ebs-*</code> group in the <b>EBS Chat Access</b> tab (or a Keycloak group with the same name), then run the security test and the 50-question test set (target ≥ 90% correct).</>,
  ];

  return (
    <div className="space-y-4">
      <Card title="Setup steps in Open WebUI (CoChat)" icon={ListChecks}
        subtitle="Blueprint section 8. Everything on this page is read straight from the dashboard repo, so it always matches what is deployed.">
        <ol className="p-4 space-y-2 text-xs text-gray-300 list-decimal list-inside">
          {steps.map((s, i) => <li key={i} className="leading-relaxed">{s}</li>)}
        </ol>
        <div className="px-4 pb-4 flex flex-wrap gap-2">
          <CopyButton text={ts.url} label="Copy tool server URL" />
          <a href={ts.docs} target="_blank" rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs font-semibold text-gray-300 hover:border-gray-600">
            <ExternalLink size={13} /> Swagger tool server
          </a>
        </div>
      </Card>

      <Card title="System prompt — EBS Analyst" icon={Bot}>
        <div className="p-4"><CodeBlock title="system_prompt.md" text={kit.system_prompt} /></div>
      </Card>

      <Card title="Skills domain" icon={Wrench} subtitle="Loaded lazily by the model when relevant (needs Native function calling).">
        <div className="p-4 space-y-3">
          {kit.skills.map((s) => <CodeBlock key={s.name} title={s.name} lang="markdown" text={s.content} />)}
        </div>
      </Card>

      <Card title="Prompt template (/)" icon={MessageSquareText} subtitle="For non-technical users — routine questions without having to phrase them.">
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
        subtitle="In-process Tools/Functions run Python on the Open WebUI server — permission to create them equals shell access. Restrict to admins.">
        <div className="p-4 space-y-3">
          <CodeBlock title="Filter: EBS Context" lang="python" text={kit.filter} />
          <CodeBlock title="Action: Export Excel" lang="python" text={kit.action} />
        </div>
      </Card>
    </div>
  );
}
