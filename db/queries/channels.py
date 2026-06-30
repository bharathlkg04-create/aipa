import asyncpg


async def get_channel_by_token(
    pool: asyncpg.Pool, channel_token: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, business_id, channel_token, webhook_secret, is_active
            FROM channels
            WHERE channel_token = $1
              AND channel_type = 'telegram'
              AND is_active = true
            """,
            channel_token,
        )
