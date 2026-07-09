import asyncpg


async def get_or_create_conversation(
    pool: asyncpg.Pool,
    business_id: str,
    channel_id: str,
    customer_id: str,
    customer_name: str | None = None,
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
            conversation_id = str(row["id"])
        else:
            conversation_id = str(
                await conn.fetchval(
                    """
                    INSERT INTO conversations (business_id, channel_id, customer_id)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    business_id,
                    channel_id,
                    customer_id,
                )
            )

        # Best-effort: remember the customer's display name for the inbox UI.
        # Tolerates deployments where the migration adding customer_name
        # hasn't run yet — message processing must never break over this.
        if customer_name:
            try:
                await conn.execute(
                    "UPDATE conversations SET customer_name = $2 WHERE id = $1",
                    conversation_id,
                    customer_name,
                )
            except asyncpg.PostgresError:
                pass

        return conversation_id


async def list_conversations(
    pool: asyncpg.Pool,
    business_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[asyncpg.Record]:
    """Conversations for the inbox: one row per customer thread with the
    channel type, message count, and a preview of the latest message."""
    async with pool.acquire() as conn:
        return list(
            await conn.fetch(
                """
                SELECT
                    c.id,
                    c.customer_id,
                    c.customer_name,
                    c.started_at,
                    ch.channel_type,
                    m.message_count,
                    m.last_message_at,
                    m.last_message_role,
                    m.last_message_preview
                FROM conversations c
                JOIN channels ch ON ch.id = c.channel_id
                LEFT JOIN LATERAL (
                    SELECT
                        count(*) AS message_count,
                        max(created_at) AS last_message_at,
                        (array_agg(role ORDER BY created_at DESC))[1] AS last_message_role,
                        left((array_agg(content ORDER BY created_at DESC))[1], 120)
                            AS last_message_preview
                    FROM messages
                    WHERE conversation_id = c.id
                ) m ON true
                WHERE c.business_id = $1
                ORDER BY m.last_message_at DESC NULLS LAST, c.started_at DESC
                LIMIT $2 OFFSET $3
                """,
                business_id,
                limit,
                offset,
            )
        )


async def get_conversation_for_business(
    pool: asyncpg.Pool, business_id: str, conversation_id: str
) -> asyncpg.Record | None:
    """The conversation only if it belongs to this business (tenant guard)."""
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT c.id, c.customer_id, c.customer_name, ch.channel_type
            FROM conversations c
            JOIN channels ch ON ch.id = c.channel_id
            WHERE c.id = $2 AND c.business_id = $1
            """,
            business_id,
            conversation_id,
        )
