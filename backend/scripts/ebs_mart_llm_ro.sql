-- EBS Data Mart — dedicated read-only role for the EBS Data Tools server
-- (blueprint section 7: "Role PostgreSQL llm_ro hanya punya SELECT di schema
-- mart dan meta. Tidak ada akses ke raw dan core.")
--
-- Run ONCE per environment, as postgres, on the main dashboard database
-- ckdo_dashboard (container ckdo_postgres on both hosts — schema eis and the
-- mart live there; the old eis_dashboard database is retired):
--
--   docker exec -i ckdo_postgres psql -U postgres -d ckdo_dashboard < ebs_mart_llm_ro.sql
--
-- Then set in the .env:
--
--   EIS_LLM_RO_URL=postgresql://llm_ro:<password>@postgres:5432/ckdo_dashboard
--
-- and restart backend. Until then the tool server uses chat_readonly, which
-- the backend grants the same mart access at startup — it works, but that
-- role also reads eis.*, so the "llm_ro only sees mart" guarantee holds only
-- once this script has run. Setup > AI > EBS Data Mart > Keamanan shows which
-- role is in use.
--
-- Grants on mart.* / meta.* themselves are (re)applied by the backend on
-- every startup (app/services/ebs_mart/schema.py grant_readers), because the
-- mart views are dropped and recreated whenever their definition changes and
-- would otherwise lose their grants.

CREATE ROLE llm_ro LOGIN PASSWORD 'CHANGE_ME'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
    CONNECTION LIMIT 20;

-- Belt and braces on top of the tool server's own SET LOCAL.
ALTER ROLE llm_ro SET statement_timeout = '15s';
ALTER ROLE llm_ro SET default_transaction_read_only = on;
ALTER ROLE llm_ro SET idle_in_transaction_session_timeout = '30s';

-- Only what follows: no eis, no core, no table in public (tables are not
-- readable without an explicit grant).
GRANT CONNECT ON DATABASE ckdo_dashboard TO llm_ro;
GRANT USAGE ON SCHEMA mart, meta TO llm_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA mart TO llm_ro;
GRANT SELECT ON meta.column_catalog, meta.golden_query, meta.etl_run_log TO llm_ro;

-- Verify (all three must be: t, f, f)
SELECT has_table_privilege('llm_ro', 'mart.ap_open_invoice', 'SELECT')  AS mart_select,
       has_schema_privilege('llm_ro', 'core', 'USAGE')                  AS core_usage,
       has_schema_privilege('llm_ro', 'eis', 'USAGE')                   AS eis_usage;
