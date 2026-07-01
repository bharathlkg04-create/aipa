import secrets

import asyncpg


async def get_or_create_business_and_channel(
    pool: asyncpg.Pool,
    bot_token: str,
    business_name: str,
) -> dict:
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id, business_id, webhook_secret
            FROM channels
            WHERE channel_token = $1 AND channel_type = 'telegram'
            """,
            bot_token,
        )
        if existing:
            return {
                "channel_id": str(existing["id"]),
                "business_id": str(existing["business_id"]),
                "webhook_secret": existing["webhook_secret"],
            }

        business = await conn.fetchrow(
            "INSERT INTO businesses (name) VALUES ($1) RETURNING id",
            business_name,
        )
        business_id = str(business["id"])
        webhook_secret = secrets.token_hex(32)

        channel = await conn.fetchrow(
            """
            INSERT INTO channels (business_id, channel_token, webhook_secret, channel_type, is_active)
            VALUES ($1, $2, $3, 'telegram', true)
            RETURNING id
            """,
            business_id,
            bot_token,
            webhook_secret,
        )
        return {
            "channel_id": str(channel["id"]),
            "business_id": business_id,
            "webhook_secret": webhook_secret,
        }


async def save_api_key(
    pool: asyncpg.Pool,
    business_id: str,
    encrypted_key: str,
    provider: str,
) -> None:
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM api_keys WHERE business_id = $1",
                business_id,
            )
            await conn.execute(
                "INSERT INTO api_keys (business_id, encrypted_key, provider) VALUES ($1, $2, $3)",
                business_id,
                encrypted_key,
                provider,
            )


async def save_boss_config(
    pool: asyncpg.Pool,
    business_id: str,
    llm_model: str,
    temperature: float,
    system_prompt: str | None,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO boss_config (business_id, llm_model, temperature, system_prompt_override)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (business_id) DO UPDATE
            SET llm_model = EXCLUDED.llm_model,
                temperature = EXCLUDED.temperature,
                system_prompt_override = EXCLUDED.system_prompt_override
            """,
            business_id,
            llm_model,
            temperature,
            system_prompt,
        )
