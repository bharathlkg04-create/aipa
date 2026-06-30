import asyncpg


async def get_active_kb_entries(
    pool: asyncpg.Pool, business_id: str
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT title, content
            FROM knowledge_base
            WHERE business_id = $1
              AND is_active = true
            ORDER BY created_at ASC
            """,
            business_id,
        )
