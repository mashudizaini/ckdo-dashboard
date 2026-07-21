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

    # Anthropic — still used by CV Screening / JD Generator / AP Invoice OCR /
    # Meeting Notes. The AI Chatbot itself has moved to the local Ollama server.
    anthropic_api_key: str = ""

    # Ollama — local AI server (VM "ai-engine", 172.21.2.27), used by the AI Chatbot
    # (chat completion + RAG embeddings, replacing Anthropic + Voyage AI)
    ollama_api_url: str = "http://172.21.2.27:11434"
    ollama_chat_model: str = "qwen2.5:14b-instruct"
    ollama_tool_model: str = "qwen2.5:7b-instruct"  # Oracle EBS tool-calling chat — smaller/faster is fine for tool selection

    # EIS (Postgres, ETL'd from Oracle EBS) — read-only user, used by the Oracle
    # EBS tool-calling chat. Only reachable where EIS is deployed (currently dev).
    eis_database_url: str = "postgresql://chat_readonly:CkdoChat_R0!2026@172.21.2.209:5433/eis_dashboard"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
