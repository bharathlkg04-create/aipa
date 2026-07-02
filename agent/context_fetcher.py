import asyncio

import asyncpg
from cryptography.fernet import Fernet

from aipa.agent.embeddings import embed_text, embedding_to_pgvector
from aipa.agent.schemas import AgentContext
from aipa.config import get_settings
from aipa.core.encryption import decrypt_api_key
from aipa.db.queries.api_keys import get_encrypted_api_key
from aipa.db.queries.boss_config import get_boss_config
from aipa.db.queries.knowledge_base import get_active_kb_entries
from aipa.db.queries.messages import get_last_n_messages
from aipa.db.queries.skills import get_enabled_skills, get_relevant_skills


async def _fetch_skills_for_message(
    pool: asyncpg.Pool, business_id: str, user_text: str
) -> list[asyncpg.Record]:
    """Pick the skills to inject: vector retrieval when an embedding key is
    configured, otherwise pinned + newest enabled skills, capped either way."""
    max_skills = get_settings().MAX_SKILLS_IN_PROMPT

    embedding = await embed_text(user_text)
    if embedding is None:
        return await get_enabled_skills(pool, business_id, limit=max_skills)

    return await get_relevant_skills(
        pool, business_id, embedding_to_pgvector(embedding), limit=max_skills
    )


async def fetch_agent_context(
    pool: asyncpg.Pool,
    business_id: str,
    conversation_id: str,
    fernet: Fernet,
    user_text: str = "",
) -> AgentContext:
    kb, skills, recent_msgs, config, api_key_row = await asyncio.gather(
        get_active_kb_entries(pool, business_id),
        _fetch_skills_for_message(pool, business_id, user_text),
        get_last_n_messages(pool, conversation_id, limit=10),
        get_boss_config(pool, business_id),
        get_encrypted_api_key(pool, business_id),
    )

    return AgentContext(
        knowledge_base=list(kb),
        skills=list(skills),
        recent_messages=list(recent_msgs),
        boss_config=dict(config) if config else None,
        decrypted_api_key=decrypt_api_key(fernet, api_key_row["encrypted_key"]),
    )
