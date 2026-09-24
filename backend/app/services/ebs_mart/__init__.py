"""
EBS Data Mart — the semantic layer described in "Blueprint AI Chat Oracle EBS –
Open WebUI" (sumber/, 2026-09-24).

Data flows one way: Oracle EBS -> core.* (cleaned, joined, org-filtered) ->
mart.* (business views, business column names) -> Dashboard and the EBS Data
Tools server that Open WebUI calls. Chat never touches Oracle, and the model
never sees core.* or eis.*: run_sql only accepts SELECTs over mart.*.

  constants.py   — EBS environment constants, mart registry, group -> domain map
  schema.py      — DDL for meta/core/mart, seeded catalog and golden queries
  sql_guard.py   — sqlglot validation for run_sql (one SELECT, mart.* only)
  access.py      — who may read which mart (Keycloak groups + ebs_chat_scope)
  query.py       — guarded execution: read-only, timeout, row cap, as_of, audit
  tools.py       — intent tools (get_ap_aging, get_expiring_lots, ...)
  openwebui_kit/ — system prompt, skills, prompts, filter and action for the
                   "EBS Analyst" model preset in Open WebUI

The ETL jobs live in app/tasks/ebs_mart_tasks.py, the OpenAPI tool server in
app/routers/ebs_tools_app.py, and the admin API in
app/routers/ai_tools/ebs_mart_admin.py.

Why raw.* from the blueprint is not a schema here: the extracts already select
only the needed columns and apply org_id/cancel filters in Oracle (as the
blueprint's own section 6.1 extract does), so a 1:1 raw copy would be a third
copy of the same rows with no reader. core.* is where the ETL lands.
"""
