import asyncpg


async def get_owner_token(pool: asyncpg.Pool, business_id: str) -> str | None:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT owner_token FROM businesses WHERE id = $1", business_id
        )
