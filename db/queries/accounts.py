import asyncpg


async def create_account(
    pool: asyncpg.Pool,
    full_name: str,
    email: str,
    password_hash: str,
    account_token: str,
) -> str | None:
    """Create an account; returns its id, or None when the email is taken."""
    async with pool.acquire() as conn:
        try:
            return str(
                await conn.fetchval(
                    """
                    INSERT INTO accounts (full_name, email, password_hash, account_token)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                    """,
                    full_name,
                    email,
                    password_hash,
                    account_token,
                )
            )
        except asyncpg.UniqueViolationError:
            return None


async def get_account_by_email(pool: asyncpg.Pool, email: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, full_name, email, password_hash, account_token
            FROM accounts WHERE lower(email) = lower($1)
            """,
            email,
        )


async def get_account_by_token(pool: asyncpg.Pool, token: str) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, full_name, email, account_token
            FROM accounts WHERE account_token = $1
            """,
            token,
        )


async def get_business_by_account(
    pool: asyncpg.Pool, account_id: str
) -> asyncpg.Record | None:
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id, name, owner_token FROM businesses WHERE account_id = $1",
            account_id,
        )


async def link_account(pool: asyncpg.Pool, business_id: str, account_id: str) -> str:
    """Bind an account to a business. Returns 'ok', 'business_taken' or
    'user_taken' — same contract as link_google_user."""
    async with pool.acquire() as conn:
        current = await conn.fetchval(
            "SELECT account_id FROM businesses WHERE id = $1", business_id
        )
        if current is not None and str(current) == account_id:
            return "ok"
        if current is not None:
            return "business_taken"
        try:
            await conn.execute(
                "UPDATE businesses SET account_id = $2 WHERE id = $1",
                business_id,
                account_id,
            )
        except asyncpg.UniqueViolationError:
            return "user_taken"
        return "ok"
