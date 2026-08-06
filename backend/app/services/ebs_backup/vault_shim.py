"""
Thin adapter so code ported from the standalone ebs-backup-dashboard app
(which called a local `vault.encrypt`/`vault.decrypt` backed by its own
Fernet MASTER_KEY) can be copied here almost unchanged. This app already has
field-level Fernet encryption at rest (app/services/crypto.py, keyed by
FIELD_ENCRYPTION_KEY) for per-user API keys — reusing it here means SSH
credentials for EBS backup servers are encrypted with the same key/mechanism
as everything else in this app, instead of introducing a second secret to
manage.
"""
from app.services import crypto


class _VaultShim:
    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ""
        return crypto.encrypt(plaintext)

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        return crypto.decrypt(ciphertext)


vault = _VaultShim()
