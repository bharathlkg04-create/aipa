import asyncpg

from aipa.config import get_settings


async def create_pool() -> asyncpg.Pool:
    settings = get_settings()
    return await asyncpg.create_pool(
        dsn=settings.SUPABASE_DB_URL,
        min_size=1,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,
    )
