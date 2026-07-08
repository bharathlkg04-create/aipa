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
            SELECT c.id, c.business_id, c.webhook_secret, b.owner_token
            FROM channels c
            JOIN businesses b ON b.id = c.business_id
            WHERE c.channel_token = $1 AND c.channel_type = 'telegram'
            """,
            bot_token,
        )
        if existing:
            owner_token = existing["owner_token"]
            if not owner_token:
                owner_token = secrets.token_urlsafe(24)
                await conn.execute(
                    "UPDATE businesses SET owner_token = $1 WHERE id = $2",
                    owner_token,
                    existing["business_id"],
                )
            return {
                "channel_id": str(existing["id"]),
                "business_id": str(existing["business_id"]),
                "webhook_secret": existing["webhook_secret"],
                "owner_token": owner_token,
            }

        owner_token = secrets.token_urlsafe(24)
        business = await conn.fetchrow(
            "INSERT INTO businesses (name, owner_token) VALUES ($1, $2) RETURNING id",
            business_name,
            owner_token,
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
            "owner_token": owner_token,
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
    timezone: str | None = None,
) -> None:
    # timezone is COALESCEd so callers that don't send one (e.g. re-running
    # setup) keep the business's existing setting instead of clearing it
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO boss_config (business_id, llm_model, temperature, system_prompt_override, timezone)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (business_id) DO UPDATE
            SET llm_model = EXCLUDED.llm_model,
                temperature = EXCLUDED.temperature,
                system_prompt_override = EXCLUDED.system_prompt_override,
                timezone = COALESCE(EXCLUDED.timezone, boss_config.timezone)
            """,
            business_id,
            llm_model,
            temperature,
            system_prompt,
            timezone,
        )
