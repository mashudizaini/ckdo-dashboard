"""
Configure the "EBS Analyst" model in Open WebUI (CoChat) from openwebui_kit/.

Blueprint "AI Chat Oracle EBS – Open WebUI", section 8. Idempotent: every
object is created if missing and updated if present, so re-running after a
kit change (system prompt, skill, filter) brings Open WebUI back in line with
the repo. Uses Open WebUI's own admin API — nothing is written to its
database directly.

Run inside the backend container (it has httpx and the env below):

    docker exec ckdo_backend python scripts/configure_openwebui_ebs_analyst.py \
        --dashboard-url http://dashboard-dev.ckd-otto.com --base-model claude-opus-5-5

Env: OPENWEBUI_BASE_URL, OPENWEBUI_API_KEY (an admin's key), and
EBS_TOOLS_SERVICE_KEY or EBS_CHAT_SERVICE_KEY (sent as the bearer key).

Identity: the tool server connection uses bearer auth plus two custom headers
that Open WebUI fills per request from the logged-in user's own account
({{USER_EMAIL}}, {{CHAT_ID}}). The user cannot set these, so the dashboard
can trust the forwarded email the same way it trusts the service key — and it
needs no ENABLE_FORWARD_USER_INFO_HEADERS env change or container restart.

The model is created without public access grants: only admins see it until
an Open WebUI group for ebs-* users is added (blueprint: "Akses: hanya grup
ebs-*").
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

KIT = Path(__file__).resolve().parents[1] / "app" / "services" / "ebs_mart" / "openwebui_kit"
SERVER_ID = "ebs-data-tools"
MODEL_ID = "ebs-analyst"
FILTER_ID = "ebs_context"
ACTION_ID = "ebs_export_excel"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dashboard-url", required=True, help="Base URL of the dashboard as seen from Open WebUI")
    ap.add_argument("--base-model", default="claude-opus-5-5")
    args = ap.parse_args()

    base = os.environ["OPENWEBUI_BASE_URL"].rstrip("/")
    key = os.environ["OPENWEBUI_API_KEY"]
    service_key = os.environ.get("EBS_TOOLS_SERVICE_KEY") or os.environ["EBS_CHAT_SERVICE_KEY"]
    dash = args.dashboard_url.rstrip("/")
    c = httpx.Client(base_url=f"{base}/api/v1", headers={"Authorization": f"Bearer {key}"}, timeout=60)

    def call(method, path, **kw):
        r = c.request(method, path, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else None

    def exists(path):
        return c.get(path).status_code == 200

    # 1. Tool server connection
    conn = {
        "url": f"{dash}/api/v1/ebs-tools",
        "path": "openapi.json",
        "type": "openapi",
        "auth_type": "bearer",
        "key": service_key,
        "headers": {"X-OpenWebUI-User-Email": "{{USER_EMAIL}}", "X-OpenWebUI-Chat-Id": "{{CHAT_ID}}"},
        "config": {"enable": True},
        "info": {
            "id": SERVER_ID,
            "name": "CKDO EBS Data Tools",
            "description": "Data mart Oracle EBS (AP, stok per lot): find_marts, run_sql read-only, intent tools.",
        },
    }
    current = call("GET", "/configs/tool_servers")["TOOL_SERVER_CONNECTIONS"]
    others = [s for s in current if (s.get("info") or {}).get("id") != SERVER_ID]
    call("POST", "/configs/tool_servers", json={"TOOL_SERVER_CONNECTIONS": others + [conn]})
    verify = c.post("/configs/tool_servers/verify", json=conn)
    print(f"tool server: {len(others)} other connection(s) kept; verify -> {verify.status_code}")

    # 2. Functions (filter + action)
    for fid, name, fname, desc, valves in [
        (FILTER_ID, "EBS Context", "filter_ebs_context.py",
         "Tanggal & periode EBS aktif, redaksi NPWP/rekening", None),
        (ACTION_ID, "Export Excel", "action_export_excel.py",
         "Ubah tabel jawaban EBS Analyst menjadi .xlsx",
         {"dashboard_url": dash, "service_key": service_key, "timeout": 60}),
    ]:
        body = {"id": fid, "name": name, "content": (KIT / fname).read_text(encoding="utf-8"),
                "meta": {"description": desc}}
        if exists(f"/functions/id/{fid}"):
            call("POST", f"/functions/id/{fid}/update", json=body)
        else:
            call("POST", "/functions/create", json=body)
        if not call("GET", f"/functions/id/{fid}").get("is_active"):
            call("POST", f"/functions/id/{fid}/toggle")
        if valves:
            call("POST", f"/functions/id/{fid}/valves/update", json=valves)
        print(f"function {fid}: ok")

    # 3. Skills
    skill_ids = []
    for p in sorted((KIT / "skills").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        body = {"id": p.stem, "name": p.stem, "description": title, "content": text,
                "meta": {"tags": ["ebs"]}, "is_active": True}
        if exists(f"/skills/id/{p.stem}"):
            call("POST", f"/skills/id/{p.stem}/update", json=body)
        else:
            call("POST", "/skills/create", json=body)
        skill_ids.append(p.stem)
        print(f"skill {p.stem}: ok")

    # 4. Prompts (/command templates)
    existing = {p["command"]: p for p in call("GET", "/prompts/")}
    for pr in json.loads((KIT / "prompts.json").read_text(encoding="utf-8")):
        command = pr["command"].lstrip("/")
        body = {"command": command, "name": pr["title"], "content": pr["content"], "tags": ["ebs"]}
        if command in existing:
            call("POST", f"/prompts/id/{existing[command]['id']}/update", json=body)
        else:
            call("POST", "/prompts/create", json=body)
        print(f"prompt /{command}: ok")

    # 5. Model preset
    model = {
        "id": MODEL_ID,
        "base_model_id": args.base_model,
        "name": "EBS Analyst",
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": "Analis data Oracle EBS CKDO — hutang (AP) dan stok per lot dari data mart dashboard. Setiap angka menyebut waktu data (as_of) dan SQL-nya.",
            "capabilities": {
                "file_context": False, "vision": False, "file_upload": False, "web_search": False,
                "image_generation": False, "code_interpreter": False, "terminal": False,
                "citations": True, "status_updates": True, "usage": False, "memory": False,
                "builtin_tools": True,
            },
            "toolIds": [f"server:{SERVER_ID}"],
            "skillIds": skill_ids,
            "filterIds": [FILTER_ID],
            "actionIds": [ACTION_ID],
            "tags": [{"name": "EBS"}],
            "suggestion_prompts": [
                {"content": "Aging hutang per bucket"},
                {"content": "10 supplier dengan hutang overdue terbesar"},
                {"content": "Lot bahan baku yang expired dalam 90 hari"},
                {"content": "Invoice supplier yang sedang di-hold"},
            ],
        },
        "params": {
            "system": (KIT / "system_prompt.md").read_text(encoding="utf-8"),
            "temperature": 0.1,
            "function_calling": "native",
            "max_tokens": 8000,
        },
        "access_grants": [],
        "is_active": True,
    }
    if exists(f"/models/model?id={MODEL_ID}"):
        call("POST", f"/models/model/update?id={MODEL_ID}", json=model)
    else:
        call("POST", "/models/create", json=model)
    got = call("GET", f"/models/model?id={MODEL_ID}")
    meta = got.get("meta") or {}
    print(f"model {MODEL_ID}: base={got.get('base_model_id')} tools={meta.get('toolIds')} "
          f"skills={meta.get('skillIds')} filters={meta.get('filterIds')} actions={meta.get('actionIds')} "
          f"function_calling={(got.get('params') or {}).get('function_calling')}")


if __name__ == "__main__":
    sys.exit(main())
