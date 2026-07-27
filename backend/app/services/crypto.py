"""
Field-level encryption for secrets stored at rest (currently: per-user AI
provider API keys — see user_api_key_service.py). Fernet (symmetric,
authenticated) keyed by FIELD_ENCRYPTION_KEY in the environment — a value
distinct from any auth/JWT secret, generated once per environment with
`Fernet.generate_key()` and never committed to the repo.
"""
from cryptography.fernet import Fernet, InvalidToken
from app.config import get_settings

settings = get_settings()

_fernet = Fernet(settings.field_encryption_key.encode()) if settings.field_encryption_key else None


def encrypt(value: str) -> str:
    if not _fernet:
        raise RuntimeError("FIELD_ENCRYPTION_KEY belum diset di environment")
    return _fernet.encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    if not _fernet:
        raise RuntimeError("FIELD_ENCRYPTION_KEY belum diset di environment")
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken:
        raise ValueError("Data terenkripsi tidak valid atau FIELD_ENCRYPTION_KEY sudah berubah")
