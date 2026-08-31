from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class InstagramTokenDecryptionError(Exception):
    pass


def _fernet():
    key = str(getattr(settings, "INSTAGRAM_TOKEN_ENCRYPTION_KEY", "") or "").strip()
    if not key:
        raise ImproperlyConfigured(
            "INSTAGRAM_TOKEN_ENCRYPTION_KEY is required before storing Instagram tokens."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ImproperlyConfigured(
            "INSTAGRAM_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from exc


def encrypt_token(raw_token):
    token = str(raw_token or "").strip()
    if not token:
        raise ValueError("Instagram access token cannot be empty.")
    return _fernet().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_token(encrypted_token):
    ciphertext = str(encrypted_token or "").strip()
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
        raise InstagramTokenDecryptionError(
            "Stored Instagram token could not be decrypted."
        ) from exc
