import secrets

from fastapi import HTTPException

from aipa.db.queries.businesses import get_owner_token


async def verify_owner(pool, business_id: str, token: str | None) -> None:
    """Raise 401/403 unless token matches the business's owner_token."""
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Owner-Token header (returned by /api/setup).",
        )
    stored = await get_owner_token(pool, business_id)
    if stored is None or not secrets.compare_digest(stored, token):
        raise HTTPException(status_code=403, detail="Invalid owner token")
