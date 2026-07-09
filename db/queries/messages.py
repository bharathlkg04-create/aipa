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


async def list_messages(
    pool: asyncpg.Pool,
    conversation_id: str,
    limit: int = 200,
    offset: int = 0,
) -> list[asyncpg.Record]:
    """Full history of one conversation, oldest first (for the chat view)."""
    async with pool.acquire() as conn:
        return list(
            await conn.fetch(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                LIMIT $2 OFFSET $3
                """,
                conversation_id,
                limit,
                offset,
            )
        )


async def list_recent_activity(
    pool: asyncpg.Pool,
    business_id: str,
    limit: int = 100,
) -> list[asyncpg.Record]:
    """Newest messages across all of a business's conversations — the
    activity log: who wrote what, on which channel, and when."""
    async with pool.acquire() as conn:
        return list(
            await conn.fetch(
                """
                SELECT
                    m.id,
                    m.role,
                    left(m.content, 160) AS preview,
                    m.created_at,
                    c.id AS conversation_id,
                    c.customer_id,
                    c.customer_name,
                    ch.channel_type
                FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                JOIN channels ch ON ch.id = c.channel_id
                WHERE c.business_id = $1
                ORDER BY m.created_at DESC
                LIMIT $2
                """,
                business_id,
                limit,
            )
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
