import asyncpg


async def get_or_create_conversation(
    pool: asyncpg.Pool,
    business_id: str,
    channel_id: str,
    customer_id: str,
) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM conversations
            WHERE business_id = $1
              AND channel_id = $2
              AND customer_id = $3
            ORDER BY started_at DESC
            LIMIT 1
            """,
            business_id,
            channel_id,
            customer_id,
        )
        if row:
            return str(row["id"])

        new_id = await conn.fetchval(
            """
            INSERT INTO conversations (business_id, channel_id, customer_id)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            business_id,
            channel_id,
            customer_id,
        )
        return str(new_id)
