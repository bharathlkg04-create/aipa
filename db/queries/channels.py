import asyncpg


async def get_channel_by_token(
    pool: asyncpg.Pool, channel_token: str, channel_type: str = "telegram"
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, business_id, channel_token, webhook_secret, is_active
            FROM channels
            WHERE channel_token = $1
              AND channel_type = $2
              AND is_active = true
            """,
            channel_token,
            channel_type,
        )


async def get_channel_by_business(
    pool: asyncpg.Pool, business_id: str, channel_type: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, business_id, channel_token, webhook_secret, is_active
            FROM channels
            WHERE business_id = $1 AND channel_type = $2
            ORDER BY created_at DESC
            LIMIT 1
            """,
            business_id,
            channel_type,
        )


async def create_channel(
    pool: asyncpg.Pool,
    business_id: str,
    channel_token: str,
    webhook_secret: str,
    channel_type: str,
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO channels (business_id, channel_token, webhook_secret, channel_type)
            VALUES ($1, $2, $3, $4)
            RETURNING id, business_id, channel_token, webhook_secret, is_active
            """,
            business_id,
            channel_token,
            webhook_secret,
            channel_type,
        )


async def list_channels(pool: asyncpg.Pool, business_id: str) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT id, channel_type, channel_token, is_active, created_at
            FROM channels
            WHERE business_id = $1
            ORDER BY created_at
            """,
            business_id,
        )


async def set_channel_active(
    pool: asyncpg.Pool, channel_id: str, is_active: bool
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE channels SET is_active = $2 WHERE id = $1",
            channel_id,
            is_active,
        )
