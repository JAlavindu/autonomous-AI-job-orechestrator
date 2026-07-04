from __future__ import annotations

import os
from typing import Protocol

import httpx

from src.core.logging_config import get_logger

logger = get_logger(__name__)


class SecretsProvider(Protocol):
    def get(self, name: str, *, default: str | None = None, required: bool = False) -> str | None: ...


class EnvSecretsProvider:
    def get(self, name: str, *, default: str | None = None, required: bool = False) -> str | None:
        value = os.environ.get(name, default)
        if required and not value:
            raise RuntimeError(f"Missing required secret env var: {name}")
        return value


class VaultSecretsProvider:
    """Reads KV v2 secret at {mount}/data/{path}; keys are flat string fields."""

    def __init__(self, addr: str, token: str, mount: str, path: str):
        self.addr = addr.rstrip("/")
        self.token = token
        self.mount = mount.strip("/")
        self.path = path.strip("/")
        self._cache: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        url = f"{self.addr}/v1/{self.mount}/data/{self.path}"
        resp = httpx.get(url, headers={"X-Vault-Token": self.token}, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()["data"]["data"]
        if not isinstance(data, dict):
            raise RuntimeError("Vault secret payload must be a JSON object")
        self._cache = {str(k): str(v) for k, v in data.items()}
        return self._cache

    def get(self, name: str, *, default: str | None = None, required: bool = False) -> str | None:
        value = self._load().get(name, default)
        if required and not value:
            raise RuntimeError(f"Missing required Vault secret key: {name}")
        return value


def build_secrets_provider(
    backend: str,
    *,
    vault_addr: str = "",
    vault_token: str = "",
    vault_mount: str = "secret",
    vault_path: str = "orchestrator",
) -> SecretsProvider:
    if backend == "vault":
        if not vault_addr or not vault_token:
            raise RuntimeError("VAULT_ADDR and VAULT_TOKEN required when SECRETS_BACKEND=vault")
        return VaultSecretsProvider(vault_addr, vault_token, vault_mount, vault_path)
    return EnvSecretsProvider()


def hydrate_settings_from_secrets(settings) -> None:
    """Overlay sensitive settings from secrets backend when env left at defaults."""
    provider = build_secrets_provider(
        settings.SECRETS_BACKEND,
        vault_addr=settings.VAULT_ADDR,
        vault_token=settings.VAULT_TOKEN,
        vault_mount=settings.VAULT_MOUNT,
        vault_path=settings.VAULT_PATH,
    )

    if settings.API_KEY_PEPPER == "change-me-in-production":
        settings.API_KEY_PEPPER = provider.get("API_KEY_PEPPER", required=False) or settings.API_KEY_PEPPER

    if settings.JWT_SECRET_KEY == "dev-only-change-me":
        settings.JWT_SECRET_KEY = provider.get("JWT_SECRET_KEY", required=False) or settings.JWT_SECRET_KEY

    bootstrap = provider.get("AUTH_BOOTSTRAP_OPERATOR_KEY", default="")
    if bootstrap and not settings.AUTH_BOOTSTRAP_OPERATOR_KEY:
        settings.AUTH_BOOTSTRAP_OPERATOR_KEY = bootstrap