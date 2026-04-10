from cryptography.fernet import Fernet

from src.config import settings


def _get_encryption_key() -> str:
    """Resolve encryption key: GIT_TOKEN_ENCRYPTION_KEY or legacy GITHUB_TOKEN_ENCRYPTION_KEY."""
    key = settings.GIT_TOKEN_ENCRYPTION_KEY or settings.GITHUB_TOKEN_ENCRYPTION_KEY
    if not key:
        raise ValueError("Encryption key not configured")
    return key


def encrypt_token(plain_token: str) -> str:
    """Encrypt a git provider token using Fernet symmetric encryption."""
    f = Fernet(_get_encryption_key().encode())
    return f.encrypt(plain_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a git provider token using Fernet symmetric encryption."""
    f = Fernet(_get_encryption_key().encode())
    return f.decrypt(encrypted_token.encode()).decode()
