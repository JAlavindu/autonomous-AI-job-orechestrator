from __future__ import annotations

import hashlib
import secrets


def generate_api_key(prefix: str = "ork") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str, pepper: str) -> str:
    payload = f"{pepper}:{raw_key}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def key_prefix(raw_key: str) -> str:
    return raw_key[:12]