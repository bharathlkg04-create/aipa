import asyncpg


async def get_enabled_skills(
    pool: asyncpg.Pool, business_id: str, limit: int | None = None
) -> list[asyncpg.Record]:
    """Enabled skills without vector ranking: pinned first, then newest."""
    query = """
        SELECT s.name, s.description, s.prompt_snippet
        FROM skills s
        JOIN business_skills bs ON s.id = bs.skill_id
        WHERE bs.business_id = $1
          AND bs.is_enabled = true
        ORDER BY bs.is_pinned DESC, s.created_at DESC
        """
    async with pool.acquire() as conn:
        if limit is None:
            return await conn.fetch(query, business_id)
        return await conn.fetch(query + " LIMIT $2", business_id, limit)


async def get_relevant_skills(
    pool: asyncpg.Pool,
    business_id: str,
    query_embedding: str,
    limit: int,
) -> list[asyncpg.Record]:
    """Pinned skills plus the top-k enabled skills nearest to the message."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            WITH pinned AS (
                SELECT s.name, s.description, s.prompt_snippet, 0 AS sort_rank
                FROM skills s
                JOIN business_skills bs ON s.id = bs.skill_id
                WHERE bs.business_id = $1
                  AND bs.is_enabled = true
                  AND bs.is_pinned = true
            ),
            ranked AS (
                SELECT s.name, s.description, s.prompt_snippet, 1 AS sort_rank
                FROM skills s
                JOIN business_skills bs ON s.id = bs.skill_id
                WHERE bs.business_id = $1
                  AND bs.is_enabled = true
                  AND bs.is_pinned = false
                  AND s.embedding IS NOT NULL
                ORDER BY s.embedding <=> $2::vector
                LIMIT $3
            )
            SELECT name, description, prompt_snippet FROM pinned
            UNION ALL
            SELECT name, description, prompt_snippet FROM ranked
            ORDER BY sort_rank
            """,
            business_id,
            query_embedding,
            limit,
        )


async def list_skills(
    pool: asyncpg.Pool,
    business_id: str | None,
    category: str | None,
    industry: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> list[asyncpg.Record]:
    """Browse the skill catalog with the business's enabled/pinned state."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT s.id, s.name, s.description, s.category, s.industry,
                   COALESCE(bs.is_enabled, false) AS is_enabled,
                   COALESCE(bs.is_pinned, false)  AS is_pinned
            FROM skills s
            LEFT JOIN business_skills bs
                   ON s.id = bs.skill_id AND bs.business_id = $1
            WHERE ($2::text IS NULL OR s.category = $2)
              AND ($3::text IS NULL OR s.industry IN ($3, 'generic'))
              AND ($4::text IS NULL
                   OR s.name ILIKE '%' || $4 || '%'
                   OR s.description ILIKE '%' || $4 || '%')
            ORDER BY COALESCE(bs.is_enabled, false) DESC,
                     s.industry = 'generic' DESC,
                     s.name
            LIMIT $5 OFFSET $6
            """,
            business_id,
            category,
            industry,
            search,
            limit,
            offset,
        )


async def get_skills_meta(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        industries = await conn.fetch(
            "SELECT industry, COUNT(*) AS n FROM skills GROUP BY industry ORDER BY industry"
        )
        categories = await conn.fetch(
            "SELECT category, COUNT(*) AS n FROM skills GROUP BY category ORDER BY category"
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM skills")
    return {
        "total": total,
        "industries": [dict(r) for r in industries],
        "categories": [dict(r) for r in categories],
    }


async def set_skill_enabled(
    pool: asyncpg.Pool,
    business_id: str,
    skill_id: str,
    is_enabled: bool,
    is_pinned: bool | None = None,
) -> bool:
    """Upsert the toggle row. Returns False when the skill doesn't exist."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM skills WHERE id = $1", skill_id)
        if not exists:
            return False
        await conn.execute(
            """
            INSERT INTO business_skills (skill_id, business_id, is_enabled, is_pinned)
            VALUES ($1, $2, $3, COALESCE($4, false))
            ON CONFLICT (skill_id, business_id)
            DO UPDATE SET is_enabled = $3,
                          is_pinned  = COALESCE($4, business_skills.is_pinned)
            """,
            skill_id,
            business_id,
            is_enabled,
            is_pinned,
        )
    return True


async def enable_industry_pack(
    pool: asyncpg.Pool, business_id: str, industry: str, pack_size: int = 8
) -> int:
    """Enable a starter pack for an industry; returns skills enabled."""
    async with pool.acquire() as conn:
        result = await conn.fetch(
            """
            INSERT INTO business_skills (skill_id, business_id, is_enabled)
            SELECT s.id, $1, true
            FROM skills s
            WHERE s.industry = $2
            ORDER BY s.is_verified DESC, s.created_at
            LIMIT $3
            ON CONFLICT (skill_id, business_id)
            DO UPDATE SET is_enabled = true
            RETURNING skill_id
            """,
            business_id,
            industry,
            pack_size,
        )
    return len(result)


async def count_enabled_skills(pool: asyncpg.Pool, business_id: str) -> int:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """
            SELECT COUNT(*) FROM business_skills
            WHERE business_id = $1 AND is_enabled = true
            """,
            business_id,
        )
