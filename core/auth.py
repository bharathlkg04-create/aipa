import secrets

from fastapi import HTTPException

from aipa.db.queries.businesses import get_owner_token


async def verify_owner(
    pool, business_id: str, token: str | None, authorization: str | None = None
) -> None:
    """Raise 401/403 unless the caller proves ownership of the business via
    the X-Owner-Token issued at setup. Google sign-in exchanges the Google
    ID token for this same owner session (POST /api/auth/google), so every
    authenticated request carries it; the `authorization` parameter is kept
    only so existing call sites don't break."""
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Sign in required (X-Owner-Token header).",
        )
    stored = await get_owner_token(pool, business_id)
    if stored is None or not secrets.compare_digest(stored, token):
        raise HTTPException(status_code=403, detail="Invalid owner token")
