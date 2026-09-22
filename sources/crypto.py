from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet

    key = settings.TOKEN_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            'TOKEN_ENCRYPTION_KEY is not set in .env. Generate one with: '
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    _fernet = Fernet(key.encode())
    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        raise ValueError('Stored token could not be decrypted (wrong or rotated TOKEN_ENCRYPTION_KEY?).')
