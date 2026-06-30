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

    # Anthropic
    anthropic_api_key: str = ""

    # Voyage AI (embeddings for RAG chatbot)
    voyage_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
