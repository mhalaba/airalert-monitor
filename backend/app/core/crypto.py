"""Szyfrowanie tokenow powiadomien (AES-256-GCM).

Klucz pochodny z sekretu serwera (AIRALERT_ADMIN_API_TOKEN jako seed lokalnie;
produkcja: dedykowany klucz z menedzera sekretow). Format: nonce(12) || ciphertext.
"""
from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _derive_key(secret: str) -> bytes:
    return hashlib.sha256(("push-token-key:" + secret).encode()).digest()


def encrypt_token(token: str, secret: str) -> bytes:
    aes = AESGCM(_derive_key(secret))
    nonce = os.urandom(12)
    return nonce + aes.encrypt(nonce, token.encode(), None)


def decrypt_token(blob: bytes, secret: str) -> str:
    aes = AESGCM(_derive_key(secret))
    nonce, ct = blob[:12], blob[12:]
    return aes.decrypt(nonce, ct, None).decode()
