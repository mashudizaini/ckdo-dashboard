from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "CKDO Dashboard"
    environment: str = "development"
    debug: bool = True

    # PostgreSQL
    database_url: str

    # Redis
    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    # Keycloak
    keycloak_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_client_secret: str

    # Keycloak Admin API — separate confidential service-account client
    # (ckdo-dashboard-admin), NOT keycloak_client_id above (that one is the
    # frontend's public login client, has no secret, no admin privileges).
    # Used by keycloak_admin_service.py for Setup > Access Center's
    # Dashboard-role panel (list/assign/revoke realm roles). Empty by
    # default — that panel 503s with a clear message until configured,
    # same pattern as ebs_chat_service_key below.
    keycloak_admin_client_id: str = ""
    keycloak_admin_client_secret: str = ""

    # Oracle EBS — Production and Development, selectable at runtime via the
    # environment toggle in the sidebar (see database.py's
    # get_oracle_environment()/set_oracle_environment() and the
    # oracle_env_setting table). A single shared flag, not per-user — the
    # backend's Oracle connection is one shared resource, so switching
    # applies to every user's next Oracle-backed request.
    oracle_prod_host: str = "172.21.2.201"
    oracle_prod_port: int = 1521
    oracle_prod_service: str = "PROD"
    oracle_prod_user: str = "apps"
    oracle_prod_password: str = "apps"

    oracle_dev_host: str = "172.21.2.197"
    oracle_dev_port: int = 1525
    oracle_dev_service: str = "DEV"
    oracle_dev_user: str = "apps"
    oracle_dev_password: str = "apps"

    oracle_instant_client: str = "/opt/oracle/instantclient"

    # Talenta HR API
    talenta_api_key: str = ""
    talenta_api_url: str = "https://api.talenta.co"

    # Hikvision ISAPI — attendance event poller talking directly to the
    # office's Hikvision DS-K1T342MFWX face-recognition terminal (digest
    # auth), not through a HikCentral aggregation server. base_url is the
    # terminal's own address (e.g. "http://192.168.1.20"), reachable over the
    # office LAN/VPN from this server. app_key/app_secret hold the device's
    # ISAPI username/password (field names kept from this integration's
    # earlier HikCentral-OpenAPI design to avoid a schema migration).
    hikcentral_base_url: str = ""
    hikcentral_app_key: str = ""
    hikcentral_app_secret: str = ""

    # Anthropic — kept as the opt-in "Premium" provider for CV Screening / JD
    # Generator / AP Invoice OCR / Meeting Notes MOM generation. Each of these
    # defaults to the on-premise Ollama engine below ("Standard") and only
    # calls Anthropic when the caller explicitly asks for provider="anthropic".
    anthropic_api_key: str = ""

    # Ollama — local AI server (VM "ai-engine", 172.21.2.27). Chat completion
    # + RAG embeddings for the AI Chatbot, and the default ("Standard") text
    # provider for CV Screening / JD Generator.
    ollama_api_url: str = "http://172.21.2.27:11434"
    # qwen3:30b (MoE, "30B-A3B") over qwen2.5:14b-instruct — deeper reasoning
    # for large/complex documents (e.g. the 211-chunk company regulation),
    # chosen deliberately despite a measured ~3x slower response (15s vs 5.3s
    # warm, identical 16-chunk RAG prompt) since it doesn't fully fit ai-
    # engine's 16GB VRAM (18GB model -> 59%/41% GPU/CPU split, confirmed via
    # `ollama ps`). Model storage was migrated ai-engine-side from the 72GB
    # root disk (was 78% full) to /mnt/ollama-data (984GB, was unused) to
    # make room — see ai-engine's /etc/systemd/system/ollama.service.d/
    # override.conf (OLLAMA_MODELS). The context_k=16 cap in ai_service.py's
    # stream_chat (see retrieve_context's docstring) was validated against
    # qwen2.5:14b-instruct's hallucination threshold specifically — not
    # re-validated for this model, kept as the known-safe starting point.
    ollama_chat_model: str = "qwen3:30b"
    ollama_tool_model: str = "qwen2.5:7b-instruct"  # Oracle EBS tool-calling chat — smaller/faster is fine for tool selection
    # Vision-capable model for AP Invoice OCR's default ("Standard") provider
    # — qwen2.5:14b-instruct is text-only, so document/image extraction needs
    # a separate VL model (validated: 100% accurate field extraction on a
    # test invoice in ~6s).
    ollama_vision_model: str = "qwen2.5vl:7b"
    # Dedicated on-prem model for Meeting Notes' MOM generation — kept
    # separate from ollama_chat_model (shared by the AI Chatbot/CV
    # Screening/JD Generator) so tuning this one can't silently change
    # those other features. qwen3:14b chosen over qwen2.5:14b-instruct
    # after an empirical A/B (comparable quality/reliability once
    # schema-constrained, newer model generation) — same ~9-10GB VRAM
    # footprint, confirmed to fit alongside the always-resident Whisper
    # model on the ai-engine GPU's 16GB budget.
    ollama_mom_model: str = "qwen3:14b"

    # Whisper transcription — GPU service on the same "ai-engine" VM
    # (172.21.2.27:9500, faster-whisper large-v3, systemd unit whisper-server.service).
    # Replaces running faster-whisper in-process on the backend's CPU for
    # Meeting Notes — ~17x realtime on this box's RTX 5060 Ti vs. potentially
    # slower-than-realtime on CPU, which matters for 1-2 hour meeting audio.
    whisper_api_url: str = "http://172.21.2.27:9500"

    # Speaker diarization + voice-embedding — separate pure-inference
    # microservice on the same "ai-engine" VM (172.21.2.27:9600), colocated
    # with Whisper for GPU access. See ai-engine-services/diarization/
    # for the service source + deployment instructions. Only turns audio
    # into segments/embeddings — enrollment storage and name-matching live
    # in this backend (see speaker_id_service.py).
    diarization_api_url: str = "http://172.21.2.27:9600"

    # Gemini API (Google AI Studio) — third chat provider, opt-in alongside
    # "onprem" (Ollama) for the AI Chatbot's 3 modes (Company Policy / Oracle
    # ERP / General). Company already has paid Gemini access via Google
    # Workspace. Use the "-latest" alias, not a pinned version — dated model
    # IDs get deprecated for new API keys/projects (e.g. gemini-2.5-flash
    # returns 404 "no longer available to new users").
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"

    # DeepSeek API — opt-in provider for Meeting Notes MOM generation
    # (alongside onprem/anthropic/gemini). OpenAI-compatible chat-completions
    # endpoint, called via raw httpx like gemini_service.py rather than
    # adding the `openai` SDK as a new dependency for one endpoint.
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    # OpenAI (ChatGPT) — opt-in provider for Meeting Notes MOM generation.
    # OpenAI-compatible chat-completions endpoint, same raw-httpx approach
    # as DeepSeek (no `openai` SDK dependency). These are shared/fallback
    # keys — each user can also save their own via the per-user API key
    # mechanism (user_api_key_service.py), which takes priority when set.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Kimi (Moonshot AI) — opt-in provider for Meeting Notes MOM generation.
    # OpenAI-compatible chat-completions endpoint (api.moonshot.ai is the
    # international/global base; api.moonshot.cn is the China-region one —
    # switch kimi_api_base if the company's account is China-registered).
    # "kimi-latest" auto-routes to Moonshot's current flagship model instead
    # of a version-pinned name that can go stale.
    kimi_api_key: str = ""
    kimi_model: str = "kimi-latest"
    kimi_api_base: str = "https://api.moonshot.ai/v1"

    # Open WebUI ("CoChat", linked from the Sidebar) — pushes this app's own
    # RAG Knowledge Base (company_documents, managed under Setup > AI >
    # Knowledge Base) into CoChat's separate "Company Rules" Knowledge
    # collection via its native sync API, so CoChat's own chat can also
    # answer from these same documents. See openwebui_sync_service.py.
    # Knowledge ID belongs to a collection owned by a dedicated
    # "dashboard-integration" CoChat account, not a personal admin login.
    openwebui_base_url: str = ""
    openwebui_api_key: str = ""
    openwebui_knowledge_id: str = ""

    # Field-level encryption for secrets stored at rest in Postgres —
    # currently only per-user Gemini API keys (see crypto.py). Distinct from
    # any auth secret; generate once per environment with
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    # Model untuk langkah PERTAMA percakapan EBS Chat: memilih tool mana yang
    # dipakai dan dengan argumen apa. Langkah itu tidak menulis jawaban untuk
    # user, jadi tidak perlu model sekuat penulis jawabannya — dan ia dipanggil
    # di setiap pertanyaan, jadi selisih latensinya terasa langsung.
    #
    # Sengaja jadi setelan, bukan konstanta: pemilihan tool adalah bagian yang
    # paling rentan kalau modelnya kurang mampu (salah tool, argumen tidak
    # lengkap), dan kalau itu terjadi harus bisa dikembalikan lewat .env tanpa
    # menunggu deploy. Isi dengan model yang sama seperti penulis jawaban untuk
    # mengembalikan perilaku lama.
    anthropic_tool_planning_model: str = "claude-haiku-4-5-20251001"

    field_encryption_key: str = ""

    # EIS (schema `eis`, ETL'd from Oracle EBS). Lives in the main dashboard
    # Postgres — database ckdo_dashboard, the same one as DATABASE_URL — on
    # both dev and prod; the standalone eis_dashboard database
    # (eis_postgres, 172.21.2.209:5433) is retired. These are still separate
    # URLs because each is a different role with different rights, not a
    # different database. Defaults match the compose service name; .env on
    # every host sets the real credentials.
    # Read-only — used by the Oracle EBS tool-calling chat (defense in depth:
    # even a compromised prompt/argument can't write, since the DB role can't).
    eis_database_url: str = "postgresql://chat_readonly:CkdoChat_R0!2026@postgres:5432/ckdo_dashboard"
    # Full read-write — used by the integrated EIS Dashboard tab and its ETL
    # (same credentials the standalone eis-dashboard-v2 app used). Plain
    # scheme like `database_url` above — the +asyncpg driver is added at the
    # point of use (see eis_database.py), same convention as app/database.py.
    eis_database_url_rw: str = "postgresql://eis_user:eis_secret@postgres:5432/ckdo_dashboard"

    # EBS Chat — CoChat (Open WebUI) <-> Oracle EBS integration (Track B).
    # Separate, RLS-scoped role on the same database as above:
    # department-restricted callers get filtered rows enforced by Postgres
    # itself (RLS policies on eis.dim_employee/fact_employee/fact_budget),
    # not by trusting the LLM. See app/services/ebs_chat_service.py.
    eis_ebs_chat_reader_url: str = "postgresql://ebs_chat_reader:N4YRkQnQmw7k3wm2nqShxFVutiY8fdav@postgres:5432/ckdo_dashboard"
    # Shared secret CoChat's own Tool code sends as the X-Service-Key header
    # on POST /api/v1/ai/ebs-chat/query — this is a service-to-service call
    # (Open WebUI has its own separate login, not a Keycloak session), so
    # there's no Dashboard JWT to validate instead.
    ebs_chat_service_key: str = ""

    # EBS Data Tools server (/api/v1/ebs-tools, see app/routers/ebs_tools_app.py)
    # — the blueprint's OpenAPI tool server that Open WebUI calls directly.
    # Key for the static-bearer / X-Service-Key path; empty falls back to
    # ebs_chat_service_key so an existing CoChat valve key keeps working.
    # Callers who forward their Keycloak token need no key at all.
    ebs_tools_service_key: str = ""
    # Dedicated SELECT-only role on mart.*/meta.* (backend/scripts/sql/
    # ebs_mart_llm_ro.sql). Empty = use eis_database_url (chat_readonly),
    # which schema.py grants the same mart access.
    eis_llm_ro_url: str = ""

    # AP Autoinvoice — Google Drive polling. Path is inside the container
    # (backend/credentials/ on the host, bind-mounted to /app like the rest
    # of backend/ — see .gitignore, this file is deployed straight to the
    # server, never through git, same as .env itself). Shared Drive ID
    # comes from its URL (drive.google.com/drive/folders/<this>) once
    # opened as a Shared Drive, not a regular folder.
    gdrive_service_account_json: str = "/app/credentials/sso-dashboard-490501-ab13df3c569e.json"
    gdrive_shared_drive_id: str = "0AIVSTEWPWT8uUk9PVA"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
