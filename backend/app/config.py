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

    # Oracle EBS
    oracle_host: str = "172.21.2.201"
    oracle_port: int = 1521
    oracle_service: str = "PROD"
    oracle_user: str = "apps"
    oracle_password: str
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
    ollama_chat_model: str = "qwen2.5:14b-instruct"
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

    # Field-level encryption for secrets stored at rest in Postgres —
    # currently only per-user Gemini API keys (see crypto.py). Distinct from
    # any auth secret; generate once per environment with
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
    field_encryption_key: str = ""

    # EIS (Postgres, ETL'd from Oracle EBS). Only reachable where EIS is
    # deployed (currently dev, 172.21.2.209:5433).
    # Read-only — used by the Oracle EBS tool-calling chat (defense in depth:
    # even a compromised prompt/argument can't write, since the DB role can't).
    eis_database_url: str = "postgresql://chat_readonly:CkdoChat_R0!2026@172.21.2.209:5433/eis_dashboard"
    # Full read-write — used by the integrated EIS Dashboard tab and its ETL
    # (same credentials the standalone eis-dashboard-v2 app used). Plain
    # scheme like `database_url` above — the +asyncpg driver is added at the
    # point of use (see eis_database.py), same convention as app/database.py.
    eis_database_url_rw: str = "postgresql://eis_user:eis_secret@172.21.2.209:5433/eis_dashboard"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
