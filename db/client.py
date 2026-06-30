import asyncpg

from aipa.config import get_settings


async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(
        dsn=settings.SUPABASE_DB_URL,
        min_size=5,
        max_size=20,
        command_timeout=30,
        ssl="require",
        # Needed if using Supabase transaction-mode pooler (port 6543).
        # Safe to leave on even with direct connections.
        statement_cache_size=0,
    )
