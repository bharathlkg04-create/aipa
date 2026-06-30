import asyncpg


async def get_enabled_skills(
    pool: asyncpg.Pool, business_id: str
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT s.name, s.description, s.prompt_snippet
            FROM skills s
            JOIN business_skills bs ON s.id = bs.skill_id
            WHERE bs.business_id = $1
              AND bs.is_enabled = true
            """,
            business_id,
        )
