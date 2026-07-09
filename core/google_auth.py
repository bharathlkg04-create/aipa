"""Google Sign-In ID-token verification (Google Identity Services).

The dashboard renders the official "Sign in with Google" button, which
yields a one-time ID token (a JWT). We verify it against Google's public
JWKS and the configured OAuth client id, then exchange it server-side for
the business's own session — the Google token itself is never stored.
Verification needs no client secret.
"""

import time

import httpx
import jwt
import structlog
from fastapi import HTTPException

from aipa.config import get_settings

logger = structlog.get_logger(__name__)

_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_GOOGLE_ISSUERS = ("https://accounts.google.com", "accounts.google.com")

_JWKS_TTL_S = 3600.0
_jwks_cache: dict = {"fetched_at": 0.0, "keys": {}}


def google_enabled() -> bool:
    return bool(get_settings().GOOGLE_CLIENT_ID)


async def _signing_key(kid: str):
    stale = time.monotonic() - _jwks_cache["fetched_at"] > _JWKS_TTL_S
    if kid not in _jwks_cache["keys"] or stale:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(_GOOGLE_JWKS_URL)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("google_jwks_fetch_failed", error=type(exc).__name__)
            raise HTTPException(
                status_code=503, detail="Could not reach Google to verify sign-in"
            )
        _jwks_cache["keys"] = {k["kid"]: k for k in resp.json().get("keys", [])}
        _jwks_cache["fetched_at"] = time.monotonic()

    key = _jwks_cache["keys"].get(kid)
    if key is None:
        raise HTTPException(status_code=401, detail="Unknown Google signing key")
    return jwt.PyJWK(key).key


async def verify_google_credential(credential: str) -> dict:
    """Verify a Google ID token and return its claims
    (at least `sub`, usually also `email` and `name`). Raises 401."""
    if not google_enabled():
        raise HTTPException(
            status_code=401, detail="Google sign-in is not configured on this server"
        )
    try:
        kid = jwt.get_unverified_header(credential).get("kid", "")
        key = await _signing_key(kid)
        claims = jwt.decode(
            credential,
            key,
            algorithms=["RS256"],
            audience=get_settings().GOOGLE_CLIENT_ID,
            options={"require": ["exp", "iat", "sub"]},
            leeway=10,
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401, detail=f"Invalid Google sign-in token ({type(exc).__name__})"
        )
    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise HTTPException(status_code=401, detail="Invalid Google token issuer")
    return claims


async def verify_google_bearer(authorization: str | None) -> str:
    """Return the Google user id (`sub`) from an `Authorization: Bearer
    <ID token>` header, or raise 401. Used by one-shot calls made right
    after sign-in (setup, business linking)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    claims = await verify_google_credential(authorization.split(" ", 1)[1].strip())
    return claims["sub"]
