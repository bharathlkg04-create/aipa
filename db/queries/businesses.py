import asyncpg


async def get_owner_token(pool: asyncpg.Pool, business_id: str) -> str | None:
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT owner_token FROM businesses WHERE id = $1", business_id
        )


async def get_business(pool: asyncpg.Pool, business_id: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, name, created_at FROM businesses WHERE id = $1", business_id
        )


async def get_business_by_clerk_user(
    pool: asyncpg.Pool, clerk_user_id: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, name FROM businesses WHERE clerk_user_id = $1", clerk_user_id
        )


async def link_clerk_user(
    pool: asyncpg.Pool, business_id: str, clerk_user_id: str
) -> str:
    """Bind a Clerk user to a business. Returns 'ok', 'business_taken'
    (business already linked to another user) or 'user_taken' (user already
    linked to another business)."""
    async with pool.acquire() as conn:
        current = await conn.fetchval(
            "SELECT clerk_user_id FROM businesses WHERE id = $1", business_id
        )
        if current == clerk_user_id:
            return "ok"
        if current is not None:
            return "business_taken"
        try:
            await conn.execute(
                "UPDATE businesses SET clerk_user_id = $2 WHERE id = $1",
                business_id,
                clerk_user_id,
            )
        except asyncpg.UniqueViolationError:
            return "user_taken"
        return "ok"
