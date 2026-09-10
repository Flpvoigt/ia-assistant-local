from __future__ import annotations

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

AAD = b"oraculo-vault-v1"
SCRYPT_N = 2**14


def _key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 10:
        raise ValueError("A senha do cofre deve ter pelo menos 10 caracteres.")
    return hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, n=SCRYPT_N, r=8, p=1, dklen=32)


def encrypt_secret(passphrase: str, content: str) -> tuple[str, str, str]:
    clean = content.strip()
    if not clean or len(clean) > 20_000:
        raise ValueError("A informação deve ter entre 1 e 20.000 caracteres.")
    salt, nonce = os.urandom(16), os.urandom(12)
    ciphertext = AESGCM(_key(passphrase, salt)).encrypt(nonce, clean.encode("utf-8"), AAD)
    return tuple(base64.b64encode(value).decode("ascii") for value in (salt, nonce, ciphertext))


def decrypt_secret(passphrase: str, salt: str, nonce: str, ciphertext: str) -> str:
    try:
        raw_salt, raw_nonce, raw_ciphertext = (
            base64.b64decode(value, validate=True) for value in (salt, nonce, ciphertext)
        )
        return (
            AESGCM(_key(passphrase, raw_salt))
            .decrypt(raw_nonce, raw_ciphertext, AAD)
            .decode("utf-8")
        )
    except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Senha do cofre incorreta ou item corrompido.") from exc
