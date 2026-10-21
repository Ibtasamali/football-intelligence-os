"""Authentication, tenant isolation, rate limiting and audit logging.

Demo mode (no API_KEYS / AUTH_JWT_ISSUER configured) lets every request through as tenant "demo".
In Azure, Entra ID issues JWTs; API Management or Container Apps auth validates the signature and
forwards claims. Here we accept either a static API key (service-to-service) or a bearer token whose
issuer/audience match configuration.
"""
from __future__ import annotations

import base64
import json
import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request, status

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger("security")


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant_id: str
    roles: tuple[str, ...] = ()


def _decode_jwt_claims(token: str) -> dict:
    """Decode claims. Signature validation happens at the Azure edge (APIM / Container Apps auth)."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token") from exc


async def get_principal(request: Request) -> Principal:
    settings = get_settings()
    api_key = request.headers.get("x-api-key")
    auth = request.headers.get("authorization", "")
    tenant_header = request.headers.get("x-tenant-id", "demo")

    if not settings.api_key_set and not settings.auth_jwt_issuer:
        return Principal(subject="demo-user", tenant_id=tenant_header or "demo", roles=("fan", "analyst"))

    if api_key and api_key in settings.api_key_set:
        return Principal(subject="service", tenant_id=tenant_header, roles=("service", "analyst"))

    if auth.lower().startswith("bearer ") and settings.auth_jwt_issuer:
        claims = _decode_jwt_claims(auth[7:])
        if claims.get("iss") != settings.auth_jwt_issuer or claims.get("aud") != settings.auth_jwt_audience:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid issuer or audience")
        if claims.get("exp", 0) < time.time():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
        return Principal(subject=claims.get("oid") or claims.get("sub", "unknown"),
                         tenant_id=claims.get("tid", tenant_header), roles=tuple(claims.get("roles", ["fan"])))

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")


def require_role(role: str):
    async def checker(principal: Principal = Depends(get_principal)) -> Principal:
        if role not in principal.roles and "service" not in principal.roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Role '{role}' required")
        return principal

    return checker


class RateLimiter:
    """Token bucket per client. In production this sits in Azure API Management; kept in-process here."""

    def __init__(self, per_minute: int) -> None:
        self.capacity = per_minute
        self.refill = per_minute / 60.0
        self.buckets: dict[str, tuple[float, float]] = defaultdict(lambda: (float(per_minute), time.monotonic()))

    def allow(self, key: str) -> bool:
        tokens, last = self.buckets[key]
        now = time.monotonic()
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens < 1:
            self.buckets[key] = (tokens, now)
            return False
        self.buckets[key] = (tokens - 1, now)
        return True


def audit(action: str, principal: Principal, **fields) -> None:
    log.info("audit", action=action, subject=principal.subject, tenant=principal.tenant_id, **fields)
