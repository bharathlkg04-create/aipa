import asyncpg

from aipa.core.exceptions import MissingAPIKeyError


async def get_encrypted_api_key(
    pool: asyncpg.Pool, business_id: str
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT encrypted_key, provider
            FROM api_keys
            WHERE business_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            business_id,
        )
    if row is None:
        raise MissingAPIKeyError(
            f"No API key configured for business {business_id}"
        )
    return row
