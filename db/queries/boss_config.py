import asyncpg


async def get_boss_config(
    pool: asyncpg.Pool, business_id: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT system_prompt_override, llm_model, temperature, timezone
            FROM boss_config
            WHERE business_id = $1
            LIMIT 1
            """,
            business_id,
        )
