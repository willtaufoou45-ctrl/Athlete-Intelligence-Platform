"""Validated runtime configuration for local and hosted AIP modes."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    hosted: bool
    auth_enabled: bool
    coach_username: str | None
    coach_password_hash: str | None
    session_secret: str | None
    trusted_proxy: bool

    @classmethod
    def from_env(cls, database_override: str | None = None) -> "Config":
        database_url = database_override or os.environ.get("DATABASE_URL", "data/aip.sqlite3")
        hosted = _boolean("AIP_HOSTED", database_url.startswith(("postgres://", "postgresql://")))
        auth_enabled = _boolean("AIP_AUTH_ENABLED", hosted)
        username = os.environ.get("AIP_COACH_USERNAME")
        password_hash = os.environ.get("AIP_COACH_PASSWORD_HASH")
        secret = os.environ.get("AIP_SESSION_SECRET")
        if auth_enabled:
            missing = [name for name, value in (
                ("AIP_COACH_USERNAME", username),
                ("AIP_COACH_PASSWORD_HASH", password_hash),
                ("AIP_SESSION_SECRET", secret),
            ) if not value]
            if missing:
                raise RuntimeError("Authentication requires: " + ", ".join(missing))
            if len(secret or "") < 32:
                raise RuntimeError("AIP_SESSION_SECRET must contain at least 32 characters.")
        return cls(
            database_url=database_url,
            hosted=hosted,
            auth_enabled=auth_enabled,
            coach_username=username,
            coach_password_hash=password_hash,
            session_secret=secret,
            trusted_proxy=_boolean("AIP_TRUST_PROXY", hosted),
        )


def _boolean(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false.")
