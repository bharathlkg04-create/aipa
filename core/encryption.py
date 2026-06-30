from cryptography.fernet import Fernet, InvalidToken

from aipa.core.exceptions import EncryptionError


def encrypt_api_key(fernet: Fernet, plain_key: str) -> str:
    return fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(fernet: Fernet, encrypted_key: str) -> str:
    try:
        return fernet.decrypt(encrypted_key.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionError(
            "Failed to decrypt API key — FERNET_KEY may have been rotated "
            "or the stored ciphertext is corrupted."
        ) from exc
