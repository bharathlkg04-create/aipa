"""Clerk session-token verification (https://clerk.com).

The dashboard sends `Authorization: Bearer <session JWT>` on API calls.
Tokens are RS256-signed by the Clerk instance whose domain is embedded in
CLERK_PUBLISHABLE_KEY; we verify them against the instance's public JWKS
(cached) and return the Clerk user id (the `sub` claim). Verification
needs no Clerk secret key.
"""

import base64
import time

import httpx
import jwt
import structlog
from fastapi import HTTPException

from aipa.config import get_settings

logger = structlog.get_logger(__name__)

_JWKS_TTL_S = 3600.0
_jwks_cache: dict = {"fetched_at": 0.0, "keys": {}}


def clerk_enabled() -> bool:
    return bool(get_settings().CLERK_PUBLISHABLE_KEY)


def frontend_api() -> str:
    """Instance domain (e.g. rested-squid-44.clerk.accounts.dev), decoded
    from the publishable key: pk_test_<base64(domain + '$')>."""
    pk = get_settings().CLERK_PUBLISHABLE_KEY
    encoded = pk.split("_", 2)[-1]
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.b64decode(padded).decode().rstrip("$")


async def _signing_key(kid: str):
    stale = time.monotonic() - _jwks_cache["fetched_at"] > _JWKS_TTL_S
    if kid not in _jwks_cache["keys"] or stale:
        url = f"https://{frontend_api()}/.well-known/jwks.json"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("clerk_jwks_fetch_failed", error=type(exc).__name__)
            raise HTTPException(
                status_code=503, detail="Could not reach the sign-in service"
            )
        _jwks_cache["keys"] = {k["kid"]: k for k in resp.json().get("keys", [])}
        _jwks_cache["fetched_at"] = time.monotonic()

    key = _jwks_cache["keys"].get(kid)
    if key is None:
        raise HTTPException(status_code=401, detail="Unknown session-token signing key")
    return jwt.PyJWK(key).key


async def verify_clerk_token(authorization: str | None) -> str:
    """Return the Clerk user id from a `Bearer <JWT>` header, or raise 401."""
    if not clerk_enabled():
        raise HTTPException(
            status_code=401, detail="Clerk sign-in is not configured on this server"
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()

    try:
        kid = jwt.get_unverified_header(token).get("kid", "")
        key = await _signing_key(kid)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=f"https://{frontend_api()}",
            options={"require": ["exp", "iat", "sub"]},
            leeway=10,
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401, detail=f"Invalid session token ({type(exc).__name__})"
        )
    return claims["sub"]
