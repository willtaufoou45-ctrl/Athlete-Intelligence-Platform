"""Small single-coach authentication and CSRF boundary for hosted V1."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from http.cookies import SimpleCookie


COOKIE_NAME = "aip_session"
SESSION_SECONDS = 12 * 60 * 60


def password_hash(password: str, *, salt: bytes | None = None) -> str:
    """Return a portable scrypt hash suitable for an environment secret."""
    if len(password) < 12:
        raise ValueError("Coach password must contain at least 12 characters.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + _b64(salt) + "$" + _b64(digest)


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32
        )
        return hmac.compare_digest(digest, _unb64(expected))
    except (ValueError, TypeError):
        return False


def issue_session(username: str, secret: str, *, now: int | None = None) -> tuple[str, str]:
    now = int(time.time()) if now is None else now
    csrf = secrets.token_urlsafe(24)
    payload = _b64(json.dumps(
        {"sub": username, "iat": now, "exp": now + SESSION_SECONDS, "csrf": csrf},
        separators=(",", ":"), sort_keys=True,
    ).encode())
    signature = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}", csrf


def read_session(environ: dict, secret: str, *, now: int | None = None) -> dict | None:
    cookie = SimpleCookie()
    try:
        cookie.load(environ.get("HTTP_COOKIE", ""))
        token = cookie[COOKIE_NAME].value
        payload, signature = token.split(".", 1)
        expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        value = json.loads(_unb64(payload))
        now = int(time.time()) if now is None else now
        if value.get("exp", 0) < now or not value.get("sub") or not value.get("csrf"):
            return None
        return value
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def session_cookie(token: str, *, secure: bool) -> str:
    flags = [f"{COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={SESSION_SECONDS}"]
    if secure:
        flags.append("Secure")
    return "; ".join(flags)


def expired_cookie(*, secure: bool) -> str:
    flags = [f"{COOKIE_NAME}=", "Path=/", "HttpOnly", "SameSite=Lax", "Max-Age=0"]
    if secure:
        flags.append("Secure")
    return "; ".join(flags)


def csrf_valid(environ: dict, session: dict, submitted: str | None) -> bool:
    return bool(submitted and hmac.compare_digest(str(session.get("csrf", "")), submitted))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
