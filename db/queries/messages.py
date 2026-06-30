import asyncpg


async def save_message(
    pool: asyncpg.Pool,
    conversation_id: str,
    role: str,
    content: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content)
            VALUES ($1, $2, $3)
            """,
            conversation_id,
            role,
            content,
        )


async def get_last_n_messages(
    pool: asyncpg.Pool,
    conversation_id: str,
    limit: int = 10,
) -> list[asyncpg.Record]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            conversation_id,
            limit,
        )
    return list(reversed(rows))
