import secrets

from fastapi import HTTPException

from aipa.core.clerk import clerk_enabled, verify_clerk_token
from aipa.db.queries.businesses import get_business_by_clerk_user, get_owner_token


async def verify_owner(
    pool, business_id: str, token: str | None, authorization: str | None = None
) -> None:
    """Raise 401/403 unless the caller proves ownership of the business —
    either a Clerk session token whose user is linked to it, or the legacy
    X-Owner-Token returned by /api/setup."""
    if authorization and clerk_enabled():
        clerk_user_id = await verify_clerk_token(authorization)
        linked = await get_business_by_clerk_user(pool, clerk_user_id)
        if linked is not None and str(linked["id"]) == business_id:
            return
        raise HTTPException(
            status_code=403, detail="Your account is not linked to this business"
        )

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Sign in required (Clerk session or X-Owner-Token header).",
        )
    stored = await get_owner_token(pool, business_id)
    if stored is None or not secrets.compare_digest(stored, token):
        raise HTTPException(status_code=403, detail="Invalid owner token")
