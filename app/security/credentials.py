"""Encryption helpers for cluster secrets stored in the application database."""
import logging

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

PREFIX = "enc:v1:"


class CredentialCipher:
    def __init__(self, key):
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except (TypeError, ValueError) as exc:
            raise ValueError("CLUSTER_CREDENTIALS_KEY must be a valid Fernet key") from exc

    def encrypt(self, value):
        if not value:
            return value
        if value.startswith(PREFIX):
            return value
        return PREFIX + self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value):
        if not value or not value.startswith(PREFIX):
            # Supports databases created before encrypted storage was added.
            return value
        try:
            return self._fernet.decrypt(value[len(PREFIX):].encode()).decode()
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt cluster credential; check CLUSTER_CREDENTIALS_KEY") from exc
