"""
Configure the "EBS Analyst" model in Open WebUI (CoChat) from openwebui_kit/.

Blueprint "AI Chat Oracle EBS – Open WebUI", section 8. Idempotent: every
object is created if missing and updated if present, so re-running after a
kit change (system prompt, skill, filter) brings Open WebUI back in line with
the repo. Uses Open WebUI's own admin API — nothing is written to its
database directly.

Run inside the backend container (it has httpx and the env below):

    docker exec ckdo_backend python scripts/configure_openwebui_ebs_analyst.py \
        --dashboard-url http://dashboard-dev.ckd-otto.com

Every EBS model is published in two variants (see VARIANTS): the original id
on Claude Sonnet 5 and "<id>-haiku" on Claude Haiku 4.5, so users can pick the
cheaper one for routine questions. Names and descriptions are in English.

Env: OPENWEBUI_BASE_URL, OPENWEBUI_API_KEY (an admin's key), and
EBS_TOOLS_SERVICE_KEY or EBS_CHAT_SERVICE_KEY (sent as the bearer key).

Identity: the tool server connection uses bearer auth plus two custom headers
that Open WebUI fills per request from the logged-in user's own account
({{USER_EMAIL}}, {{CHAT_ID}}). The user cannot set these, so the dashboard
can trust the forwarded email the same way it trusts the service key — and it
needs no ENABLE_FORWARD_USER_INFO_HEADERS env change or container restart.

EBS Analyst, the EBS Data Tools server and the shared skills and prompts are
granted to the Open WebUI group ebs-users, synced to everyone holding any
ebs-* group in Setup > AI > EBS Chat Access (blueprint: "Akses: hanya grup
ebs-*"). One shared assistant serves every domain because the fence is not
the model: ebs_mart/access.py resolves the caller's own ebs_groups on each
request and DOMAIN_BY_GROUP decides which marts answer. A purchasing user
asking about AP aging is refused by the dashboard — they do not need a
separate model, and withholding the model would only have hidden their own
purchasing data from them too.

Until 2026-10-01 these four carried no grants at all, so only administrators
could reach them. That was invisible for months because ui.default_user_role
held "admin" in the Open WebUI database, making every account an admin.

System Administration (blueprint v2 4.7 / library v2 2.4, 3.2b, 13b) is set
up in the same run, fenced to the Open WebUI group ebs-sysadmin whose members
are synced to SYSADMIN_ALLOWLIST (added if they have a CoChat account,
removed if they are no longer listed): the "CKDO EBS System Administration
Tools" server, the EBS Support model, the ebs-sysadmin skill and the SA
prompts are all granted to that group only. The dashboard checks the same
allowlist on every call, so this is the first of three fences, not the only.

EBS Finance Controller (library v2 2.3, 12-13) is granted to the Open WebUI
group ebs-finance — members synced from Setup > AI > EBS Chat Access (emails
holding ebs-finance or ebs-management) — and to ebs-sysadmin (IT runs the
closing checks too). The shared skills and the EBS Data Tools server get the
same two grants so those users can load them; the dashboard still checks each
caller's ebs-* groups on every tool call.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.ebs_mart.constants import SYSADMIN_ALLOWLIST  # noqa: E402

KIT = Path(__file__).resolve().parents[1] / "app" / "services" / "ebs_mart" / "openwebui_kit"
SA_KIT = KIT / "sysadmin"
FIN_KIT = KIT / "finance"
SERVER_ID = "ebs-data-tools"
SA_SERVER_ID = "ebs-sysadmin-tools"
SA_GROUP = "ebs-sysadmin"
SUPPORT_MODEL_ID = "ebs-support"
FIN_GROUP = "ebs-finance"
FIN_MODEL_ID = "ebs-finance-controller"
# Everyone holding ANY ebs-* group. A superset of ebs-sysadmin and
# ebs-finance, so it is the one grant EBS Analyst and the EBS Data Tools
# server need.
USER_GROUP = "ebs-users"


def finance_emails() -> set[str]:
    """Emails granted ebs-finance or ebs-management in Setup > AI > EBS Chat
    Access (ebs_chat_scope.ebs_groups)."""
    from app.services.ebs_chat_service import _get_pg
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT lower(email) FROM ebs_chat_scope
                        WHERE ebs_groups ?| array['ebs-finance', 'ebs-management']""")
        return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()
def ebs_user_emails() -> set[str]:
    """Emails granted any ebs-* group in Setup > AI > EBS Chat Access.

    Separate from finance_emails() because the fence is not the same: which
    marts a caller may read is decided per request from their own ebs_groups
    (ebs_mart/access.py -> DOMAIN_BY_GROUP), so one shared assistant is safe
    for all of them. A purchasing user asking about AP aging gets refused by
    the dashboard, not by being unable to see the model.
    """
    from app.services.ebs_chat_service import _get_pg
    conn = _get_pg()
    try:
        cur = conn.cursor()
        cur.execute("""SELECT lower(email) FROM ebs_chat_scope
                        WHERE jsonb_array_length(COALESCE(ebs_groups, '[]'::jsonb)) > 0""")
        return {r[0] for r in cur.fetchall()}
    finally:
        conn.close()


MODEL_ID = "ebs-analyst"
FILTER_ID = "ebs_context"
ACTION_ID = "ebs_export_excel"

# (id suffix, base model, label, description tail). The first variant keeps
# the original model id so existing chats stay attached to it.
VARIANTS = [
    ("", "claude-sonnet-5", "Sonnet 5",
     " Runs on Claude Sonnet 5: stronger reasoning for multi-step analysis."),
    ("-haiku", "claude-haiku-4-5-20251001", "Haiku 4.5",
     " Runs on Claude Haiku 4.5: faster and about half the cost; good for routine questions."),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dashboard-url", required=True, help="Base URL of the dashboard as seen from Open WebUI")
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

    # 0. Groups: members synced from the dashboard (allowlist / EBS Chat Access)
    users = call("GET", "/users/all")
    users = users.get("users", users) if isinstance(users, dict) else users
    by_email = {(u.get("email") or "").lower(): u["id"] for u in users}

    def sync_group(name, description, emails):
        group = next((g for g in call("GET", "/groups/") if g["name"] == name), None)
        if not group:
            group = call("POST", "/groups/create", json={"name": name, "description": description})
        gid = group["id"]
        want = {by_email[e] for e in emails if e in by_email}
        have = {u["id"] for u in call("POST", f"/groups/id/{gid}/users")}
        if want - have:
            call("POST", f"/groups/id/{gid}/users/add", json={"user_ids": sorted(want - have)})
        if have - want:
            call("POST", f"/groups/id/{gid}/users/remove", json={"user_ids": sorted(have - want)})
        missing = sorted(e for e in emails if e not in by_email)
        print(f"group {name}: {len(want)} member(s)" + (f"; belum punya akun CoChat: {missing}" if missing else ""))
        return [{"principal_type": "group", "principal_id": gid, "permission": "read"}]

    sa_grants = sync_group(SA_GROUP, "Tim IT allowlist System Administration EBS (mashudi, utomo, itsupport). "
                           "Anggota disinkronkan oleh configure_openwebui_ebs_analyst.py dari SYSADMIN_ALLOWLIST.",
                           SYSADMIN_ALLOWLIST)
    fin_grants = sync_group(FIN_GROUP, "Finance & Accounting — model EBS Finance Controller. Anggota disinkronkan "
                            "dari Setup > AI > EBS Chat Access (grup ebs-finance / ebs-management).",
                            finance_emails())
    user_grants = sync_group(USER_GROUP, "Semua pemegang grup ebs-* — model EBS Analyst dan server EBS Data Tools. "
                             "Anggota disinkronkan dari Setup > AI > EBS Chat Access (grup ebs-* apa pun). Mart yang "
                             "benar-benar terbaca tetap ditentukan per pemanggil oleh DOMAIN_BY_GROUP.",
                             ebs_user_emails())

    # 1. Tool server connections
    conn = {
        "url": f"{dash}/api/v1/ebs-tools",
        "path": "openapi.json",
        "type": "openapi",
        "auth_type": "bearer",
        "key": service_key,
        "headers": {"X-OpenWebUI-User-Email": "{{USER_EMAIL}}", "X-OpenWebUI-Chat-Id": "{{CHAT_ID}}"},
        # Granted to ebs-users, which already contains every ebs-sysadmin and
        # ebs-finance member; the other two are listed as well so a failed
        # ebs-users sync cannot take the server away from Support and Finance.
        # The dashboard checks each caller's ebs-* groups on every call
        # regardless, so this grant decides visibility, not data.
        "config": {"enable": True, "access_grants": user_grants + sa_grants + fin_grants},
        "info": {
            "id": SERVER_ID,
            "name": "CKDO EBS Data Tools",
            "description": "Data mart Oracle EBS (AP, stok per lot): find_marts, run_sql read-only, intent tools.",
        },
    }
    sa_conn = {
        "url": f"{dash}/api/v1/ebs-sa-tools",
        "path": "openapi.json",
        "type": "openapi",
        "auth_type": "bearer",
        "key": service_key,
        "headers": {"X-OpenWebUI-User-Email": "{{USER_EMAIL}}", "X-OpenWebUI-Chat-Id": "{{CHAT_ID}}"},
        "config": {"enable": True, "access_grants": sa_grants},
        "info": {
            "id": SA_SERVER_ID,
            "name": "CKDO EBS System Administration Tools",
            "description": "User, responsibility, akses fungsi, SoD, profile, login, concurrent, workflow, patch "
                           "(hanya tim IT allowlist).",
        },
    }
    current = call("GET", "/configs/tool_servers")["TOOL_SERVER_CONNECTIONS"]
    others = [s for s in current if (s.get("info") or {}).get("id") not in (SERVER_ID, SA_SERVER_ID)]
    call("POST", "/configs/tool_servers", json={"TOOL_SERVER_CONNECTIONS": others + [conn, sa_conn]})
    verify = c.post("/configs/tool_servers/verify", json=conn)
    sa_verify = c.post("/configs/tool_servers/verify", json=sa_conn)
    print(f"tool server: {len(others)} other connection(s) kept; verify -> {verify.status_code}, "
          f"{SA_SERVER_ID} -> {sa_verify.status_code}")

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
        # The shared skills belong with the shared model: without a grant the
        # skill silently does not load for an ebs-users member, and EBS Analyst
        # answers from the system prompt alone.
        body = {"id": p.stem, "name": p.stem, "description": title, "content": text,
                "meta": {"tags": ["ebs"]}, "is_active": True,
                "access_grants": user_grants + sa_grants + fin_grants}
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
        # access_grants was missing here, which left the shared /commands
        # reachable by admins only — invisible while every account was admin.
        body = {"command": command, "name": pr["title"], "content": pr["content"], "tags": ["ebs"],
                "access_grants": user_grants + sa_grants + fin_grants}
        if command in existing:
            call("POST", f"/prompts/id/{existing[command]['id']}/update", json=body)
        else:
            call("POST", "/prompts/create", json=body)
        print(f"prompt /{command}: ok")

    def upsert_variants(spec):
        """Create/update one model per VARIANTS entry from a base spec."""
        for suffix, base_model, label, tail in VARIANTS:
            m = json.loads(json.dumps(spec))
            m["id"] = spec["id"] + suffix
            m["base_model_id"] = base_model
            m["name"] = f"{spec['name']} ({label})"
            m["meta"]["description"] = spec["meta"]["description"] + tail
            if exists(f"/models/model?id={m['id']}"):
                call("POST", f"/models/model/update?id={m['id']}", json=m)
            else:
                call("POST", "/models/create", json=m)
            got = call("GET", f"/models/model?id={m['id']}")
            meta = got.get("meta") or {}
            grants = [(g.get("principal_type"), g.get("permission")) for g in (got.get("access_grants") or [])]
            print(f"model {m['id']} '{got.get('name')}': base={got.get('base_model_id')} tools={meta.get('toolIds')} "
                  f"skills={len(meta.get('skillIds') or [])} grants={grants}")

    # 5. Model preset
    model = {
        "id": MODEL_ID,
        "name": "EBS Analyst",
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": "Oracle EBS data analyst for CKDO: payables, receivables, GL, purchasing, sales, "
                           "inventory by lot and production, read from the dashboard's data mart. Every figure "
                           "states its data time (as_of) and the SQL behind it.",
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
            # No temperature: the blueprint asks for 0–0.2, but Claude Sonnet 5
            # (like Opus 5.5) rejects the parameter outright and every chat
            # fails with HTTP 400; one params block serves both variants.
            "function_calling": "native",
            "max_tokens": 8000,
        },
        # Was [] — admins only, which went unnoticed while every CoChat account
        # was an administrator. Data access is decided per caller from their own
        # ebs_groups, so the model itself is safe to share.
        "access_grants": user_grants,
        "is_active": True,
    }
    upsert_variants(model)

    # 6a. Finance: skills and prompts for EBS Finance Controller (and Support)
    fin_skill_ids = []
    for p in sorted((FIN_KIT / "skills").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        body = {"id": p.stem, "name": p.stem, "description": title, "content": text,
                "meta": {"tags": ["ebs", "finance"]}, "is_active": True, "access_grants": sa_grants + fin_grants}
        if exists(f"/skills/id/{p.stem}"):
            call("POST", f"/skills/id/{p.stem}/update", json=body)
        else:
            call("POST", "/skills/create", json=body)
        fin_skill_ids.append(p.stem)
        print(f"skill {p.stem} (finance): ok")
    existing = {p["command"]: p for p in call("GET", "/prompts/")}
    for pr in json.loads((FIN_KIT / "prompts.json").read_text(encoding="utf-8")):
        command = pr["command"].lstrip("/")
        body = {"command": command, "name": pr["title"], "content": pr["content"], "tags": ["ebs", "finance"],
                "access_grants": sa_grants + fin_grants}
        if command in existing:
            call("POST", f"/prompts/id/{existing[command]['id']}/update", json=body)
        else:
            call("POST", "/prompts/create", json=body)
        print(f"prompt /{command} (finance): ok")

    # 6. System Administration: skill, prompts, EBS Support model — all
    #    granted to the ebs-sysadmin group only.
    sa_skill_ids = []
    for p in sorted((SA_KIT / "skills").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip()
        body = {"id": p.stem, "name": p.stem, "description": title, "content": text,
                "meta": {"tags": ["ebs", "sysadmin"]}, "is_active": True, "access_grants": sa_grants}
        if exists(f"/skills/id/{p.stem}"):
            call("POST", f"/skills/id/{p.stem}/update", json=body)
        else:
            call("POST", "/skills/create", json=body)
        sa_skill_ids.append(p.stem)
        print(f"skill {p.stem} (ebs-sysadmin only): ok")

    existing = {p["command"]: p for p in call("GET", "/prompts/")}
    for pr in json.loads((SA_KIT / "prompts.json").read_text(encoding="utf-8")):
        command = pr["command"].lstrip("/")
        body = {"command": command, "name": pr["title"], "content": pr["content"], "tags": ["ebs", "sysadmin"],
                "access_grants": sa_grants}
        if command in existing:
            call("POST", f"/prompts/id/{existing[command]['id']}/update", json=body)
        else:
            call("POST", "/prompts/create", json=body)
        print(f"prompt /{command} (ebs-sysadmin only): ok")

    support = {
        "id": SUPPORT_MODEL_ID,
        "name": "EBS Support",
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": "EBS diagnostics for the IT team: users, responsibilities, function access, SoD, "
                           "profiles, logins, concurrent requests and managers, stuck approvals and patches, plus "
                           "every EBS data mart. IT allowlist only.",
            "capabilities": {**model["meta"]["capabilities"]},
            "toolIds": [f"server:{SERVER_ID}", f"server:{SA_SERVER_ID}"],
            "skillIds": skill_ids + fin_skill_ids + sa_skill_ids,
            "filterIds": [FILTER_ID],
            "actionIds": [ACTION_ID],
            "tags": [{"name": "EBS"}, {"name": "IT"}],
            "suggestion_prompts": [
                {"content": "Concurrent request yang error 24 jam terakhir"},
                {"content": "Status concurrent manager"},
                {"content": "User EBS yang tidak login 90 hari"},
                {"content": "Pelanggaran segregation of duties"},
            ],
        },
        "params": {
            "system": (SA_KIT / "system_prompt_support.md").read_text(encoding="utf-8"),
            "function_calling": "native",
            "max_tokens": 8000,
        },
        "access_grants": sa_grants,
        "is_active": True,
    }
    upsert_variants(support)

    # 7. EBS Finance Controller (library v2 2.3): Finance skills only.
    fc_skills = [s_ for s_ in ["ebs-core", "ebs-ap", "ebs-ar", "ebs-gl-reporting", "ebs-po", "ebs-om",
                               "ebs-inventory-lot", "ebs-opm"] if s_ in skill_ids] + fin_skill_ids
    fc = {
        "id": FIN_MODEL_ID,
        "name": "EBS Finance Controller",
        "meta": {
            "profile_image_url": "/static/favicon.png",
            "description": "Finance & Accounting assistant: month-end close, subledger vs GL differences, bank "
                           "reconciliation, fixed assets, P&L, trial balance, AP/AR. Every figure states its data "
                           "time and the SQL behind it.",
            "capabilities": {**model["meta"]["capabilities"]},
            "toolIds": [f"server:{SERVER_ID}"],
            "skillIds": fc_skills,
            "filterIds": [FILTER_ID],
            "actionIds": [ACTION_ID],
            "tags": [{"name": "EBS"}, {"name": "Finance"}],
            "suggestion_prompts": [
                {"content": "Apa yang masih menghalangi closing bulan lalu?"},
                {"content": "Selisih subledger vs GL bulan lalu"},
                {"content": "Item bank yang belum rekon"},
                {"content": "Penyusutan aset tetap bulan lalu per kategori"},
            ],
        },
        "params": {
            "system": (FIN_KIT / "system_prompt_finance.md").read_text(encoding="utf-8"),
            "function_calling": "native",
            "max_tokens": 8000,
        },
        "access_grants": sa_grants + fin_grants,
        "is_active": True,
    }
    upsert_variants(fc)


if __name__ == "__main__":
    sys.exit(main())
